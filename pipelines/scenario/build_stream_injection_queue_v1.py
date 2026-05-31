#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from datetime import timedelta
from typing import Any, Dict, List

import pymysql


INTENSITY_MAP = {
    "mild": {"missing_rate": 0.03, "duplicate_rate": 0.02, "delay_ms": 1500, "shuffle_window": 5},
    "medium": {"missing_rate": 0.08, "duplicate_rate": 0.05, "delay_ms": 5000, "shuffle_window": 10},
    "high": {"missing_rate": 0.15, "duplicate_rate": 0.10, "delay_ms": 15000, "shuffle_window": 20},
}


def connect_mysql(args):
    return pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.db,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def ensure_queue_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stream_injection_event_queue (
            queue_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            profile_id VARCHAR(64) NOT NULL,
            dt DATE NOT NULL,
            ts DATETIME NOT NULL,
            raw_event_id BIGINT UNSIGNED NULL,
            event_name VARCHAR(100) NULL,
            service_domain VARCHAR(50) NULL,
            funnel_stage VARCHAR(50) NULL,
            is_conversion TINYINT(1) NOT NULL DEFAULT 0,
            uid VARCHAR(128) NULL,
            pcid VARCHAR(128) NULL,
            sid VARCHAR(128) NULL,
            status INT NULL,
            latency_ms INT NULL,
            source_type VARCHAR(50) NULL,
            path VARCHAR(255) NULL,
            evt VARCHAR(50) NULL,
            anomaly_tag VARCHAR(100) NULL,
            scenario_name VARCHAR(100) NULL,
            scenario_intensity VARCHAR(20) NULL,
            dup_group_id VARCHAR(64) NULL,
            ordering_group_id VARCHAR(64) NULL,
            queue_sequence BIGINT NULL,
            payload_json LONGTEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (queue_id),
            KEY idx_profile_dt (profile_id, dt),
            KEY idx_profile_ts (profile_id, ts),
            KEY idx_service_domain (service_domain),
            KEY idx_raw_event_id (raw_event_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def parse_scenario(scenario_name: str, intensity: str) -> Dict[str, Any]:
    base = INTENSITY_MAP.get(intensity, INTENSITY_MAP["medium"])
    cfg = {
        "scenario_name": scenario_name,
        "intensity": intensity,
        "mode": "baseline",
        "target_service_domain": None,
        "missing_rate": 0.0,
        "duplicate_rate": 0.0,
        "delay_ms": 0,
        "shuffle_window": 0,
    }
    if scenario_name == "baseline":
        return cfg
    if scenario_name.startswith("partial_missing_"):
        cfg["mode"] = "partial_missing"
        cfg["target_service_domain"] = scenario_name.replace("partial_missing_", "", 1)
        cfg["missing_rate"] = base["missing_rate"]
    elif scenario_name.startswith("duplicate_"):
        cfg["mode"] = "duplicate"
        cfg["target_service_domain"] = scenario_name.replace("duplicate_", "", 1)
        cfg["duplicate_rate"] = base["duplicate_rate"]
    elif scenario_name.startswith("delay_"):
        cfg["mode"] = "delay"
        cfg["target_service_domain"] = scenario_name.replace("delay_", "", 1)
        cfg["delay_ms"] = base["delay_ms"]
    elif scenario_name.startswith("ordering_"):
        cfg["mode"] = "ordering"
        cfg["target_service_domain"] = scenario_name.replace("ordering_", "", 1)
        cfg["shuffle_window"] = base["shuffle_window"]
    elif scenario_name.startswith("mixed_"):
        cfg["mode"] = "mixed"
        cfg["target_service_domain"] = scenario_name.replace("mixed_", "", 1)
        cfg["missing_rate"] = base["missing_rate"]
        cfg["duplicate_rate"] = base["duplicate_rate"]
        cfg["delay_ms"] = base["delay_ms"]
        cfg["shuffle_window"] = base["shuffle_window"]
    return cfg


def fetch_scenario(cur, profile_id: str, dt: str) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT scenario_name, parameters_json
        FROM scenario_experiment_run
        WHERE profile_id=%s AND dt_from=%s AND dt_to=%s
        ORDER BY scenario_name
        LIMIT 1
        """,
        (profile_id, dt, dt),
    )
    row = cur.fetchone()
    if not row:
        return parse_scenario("baseline", "medium")
    params = json.loads(row.get("parameters_json") or "{}")
    return parse_scenario(row["scenario_name"], params.get("intensity", "medium"))


def fetch_events(cur, dt: str) -> List[Dict[str, Any]]:
    cur.execute(
        """
        SELECT
            raw_event_id,
            dt,
            ts,
            COALESCE(evt, page_type, path, 'unknown') AS event_name,
            service_domain,
            funnel_stage,
            is_conversion,
            uid,
            pcid,
            sid,
            status,
            latency_ms,
            source_type,
            path,
            evt,
            NULL AS anomaly_tag
        FROM event_log_raw
        WHERE dt=%s
        ORDER BY ts, raw_event_id
        """,
        (dt,),
    )
    return cur.fetchall()


def apply_missing(rows: List[Dict[str, Any]], cfg: Dict[str, Any], rng: random.Random) -> List[Dict[str, Any]]:
    target = cfg["target_service_domain"]
    miss = cfg["missing_rate"]
    out = []
    for r in rows:
        if r.get("service_domain") == target and rng.random() < miss:
            continue
        out.append(dict(r))
    return out


def apply_duplicate(rows: List[Dict[str, Any]], cfg: Dict[str, Any], rng: random.Random) -> List[Dict[str, Any]]:
    target = cfg["target_service_domain"]
    dup = cfg["duplicate_rate"]
    out = []
    dup_idx = 0
    for r in rows:
        out.append(dict(r))
        if r.get("service_domain") == target and rng.random() < dup:
            rr = dict(r)
            rr["anomaly_tag"] = "duplicate"
            rr["_dup_group_id"] = f"dup_{target}_{dup_idx}"
            out.append(rr)
            dup_idx += 1
    return out


def apply_delay(rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    target = cfg["target_service_domain"]
    delay_ms = int(cfg["delay_ms"])
    out = []
    for r in rows:
        rr = dict(r)
        if rr.get("service_domain") == target:
            rr["latency_ms"] = int(rr.get("latency_ms") or 0) + delay_ms
            rr["anomaly_tag"] = "delay"
            if rr.get("ts") is not None:
                rr["ts"] = rr["ts"] + timedelta(milliseconds=delay_ms)
        out.append(rr)
    return out


def apply_ordering(rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    target = cfg["target_service_domain"]
    window = max(2, int(cfg["shuffle_window"]))
    target_rows = [dict(r) for r in rows if r.get("service_domain") == target]
    other_rows = [dict(r) for r in rows if r.get("service_domain") != target]

    if not target_rows:
        return rows

    shuffled: List[Dict[str, Any]] = []
    for i in range(0, len(target_rows), window):
        block = target_rows[i:i+window]
        if len(block) > 1:
            block = list(reversed(block))
            for x in block:
                x["anomaly_tag"] = "ordering"
        shuffled.extend(block)

    merged = other_rows + shuffled
    merged.sort(key=lambda x: (x["ts"], x["raw_event_id"]))
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", default="")
    ap.add_argument("--db", required=True)
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--clear-range", action="store_true")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    conn = connect_mysql(args)

    try:
        with conn.cursor() as cur:
            ensure_queue_table(cur)

            if args.clear_range:
                cur.execute(
                    "DELETE FROM stream_injection_event_queue WHERE profile_id=%s AND dt BETWEEN %s AND %s",
                    (args.profile_id, args.dt_from, args.dt_to),
                )

            cur.execute(
                """
                SELECT DISTINCT dt
                FROM event_log_raw
                WHERE dt BETWEEN %s AND %s
                ORDER BY dt
                """,
                (args.dt_from, args.dt_to),
            )
            dts = [r["dt"] for r in cur.fetchall()]
            inserted = 0

            for dt in dts:
                cfg = fetch_scenario(cur, args.profile_id, str(dt))
                rows = fetch_events(cur, str(dt))
                mode = cfg["mode"]

                work = rows
                if mode == "partial_missing":
                    work = apply_missing(work, cfg, rng)
                elif mode == "duplicate":
                    work = apply_duplicate(work, cfg, rng)
                elif mode == "delay":
                    work = apply_delay(work, cfg)
                elif mode == "ordering":
                    work = apply_ordering(work, cfg)
                elif mode == "mixed":
                    work = apply_missing(work, cfg, rng)
                    work = apply_duplicate(work, cfg, rng)
                    work = apply_delay(work, cfg)
                    work = apply_ordering(work, cfg)

                sql = """
                    INSERT INTO stream_injection_event_queue
                    (
                        profile_id, dt, ts, raw_event_id, event_name, service_domain, funnel_stage, is_conversion,
                        uid, pcid, sid, status, latency_ms, source_type, path, evt, anomaly_tag,
                        scenario_name, scenario_intensity, dup_group_id, ordering_group_id, queue_sequence, payload_json
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """

                seq = 0
                for row in work:
                    seq += 1
                    payload = dict(row)
                    cur.execute(sql, (
                        args.profile_id,
                        row["dt"],
                        row["ts"],
                        row["raw_event_id"],
                        row.get("event_name"),
                        row.get("service_domain"),
                        row.get("funnel_stage"),
                        int(row.get("is_conversion") or 0),
                        row.get("uid"),
                        row.get("pcid"),
                        row.get("sid"),
                        row.get("status"),
                        row.get("latency_ms"),
                        row.get("source_type"),
                        row.get("path"),
                        row.get("evt"),
                        row.get("anomaly_tag"),
                        cfg["scenario_name"],
                        cfg["intensity"],
                        row.get("_dup_group_id"),
                        f"ord_{cfg['target_service_domain']}" if row.get("anomaly_tag") == "ordering" else None,
                        seq,
                        json.dumps(payload, default=str, ensure_ascii=False),
                    ))
                    inserted += 1

        conn.commit()
        print(f"[build_stream_injection_queue_v1] done inserted={inserted}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
