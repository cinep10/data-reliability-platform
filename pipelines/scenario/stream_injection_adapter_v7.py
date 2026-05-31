#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from datetime import datetime, timedelta, date
from typing import Any, Dict, List

import pymysql


INTENSITY_MAP = {
    "mild": {
        "missing_ratio": 0.03,
        "duplicate_ratio": 0.08,
        "delay_ms": 500,
        "ordering_window": 5,
        "conversion_multiplier": 0.90,
        "volume_multiplier": 1.25,
    },
    "medium": {
        "missing_ratio": 0.08,
        "duplicate_ratio": 0.25,
        "delay_ms": 2000,
        "ordering_window": 10,
        "conversion_multiplier": 0.75,
        "volume_multiplier": 1.60,
    },
    "high": {
        "missing_ratio": 0.18,
        "duplicate_ratio": 0.55,
        "delay_ms": 5000,
        "ordering_window": 20,
        "conversion_multiplier": 0.55,
        "volume_multiplier": 2.20,
    },
}

ALL_DOMAINS = ["account", "auth", "branch", "card", "customer", "loan", "main", "other", "transfer"]


def connect_mysql(args):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def daterange(dt_from: str, dt_to: str):
    cur = datetime.strptime(dt_from, "%Y-%m-%d").date()
    end = datetime.strptime(dt_to, "%Y-%m-%d").date()
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def ensure_tables(cur):
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scenario_adapter_result_log (
          adapter_result_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          profile_id VARCHAR(64) NOT NULL,
          dt DATE NOT NULL,
          hh TINYINT(4) NULL,
          scenario_name VARCHAR(100) NOT NULL,
          adapter_name VARCHAR(50) NOT NULL,
          result_metric VARCHAR(100) NOT NULL,
          result_value DECIMAL(20,6) NULL,
          result_status VARCHAR(20) NOT NULL DEFAULT 'ok',
          detail TEXT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (adapter_result_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def fetch_run(cur, profile_id: str, dt: date) -> Dict[str, Any]:
    cur.execute("""
        SELECT
            profile_id,
            scenario_name,
            scenario_type,
            COALESCE(JSON_UNQUOTE(JSON_EXTRACT(parameters_json, '$.intensity')), 'medium') AS intensity,
            parameters_json
        FROM scenario_experiment_run
        WHERE profile_id=%s
          AND dt_from <= %s
          AND dt_to >= %s
        ORDER BY scenario_run_id DESC
        LIMIT 1
    """, (profile_id, dt, dt))
    row = cur.fetchone()
    if not row:
        return {"profile_id": profile_id, "scenario_name": "baseline", "intensity": "medium", "parameters_json": "{}"}
    return row


def fetch_events(cur, profile_id: str, dt: date) -> List[Dict[str, Any]]:
    cur.execute("""
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
            evt
        FROM event_log_raw
        WHERE profile_id=%s
          AND dt=%s
        ORDER BY ts, raw_event_id
    """, (profile_id, dt))
    return cur.fetchall()


def scenario_config(row: Dict[str, Any]) -> Dict[str, Any]:
    name = (row.get("scenario_name") or "baseline").lower()
    intensity = (row.get("intensity") or "medium").lower()
    base = dict(INTENSITY_MAP.get(intensity, INTENSITY_MAP["medium"]))

    cfg = {
        "scenario_name": row.get("scenario_name") or "baseline",
        "intensity": intensity,
        "mode": "baseline",
        "target_domains": ALL_DOMAINS[:],
        "missing_ratio": 0.0,
        "duplicate_ratio": 0.0,
        "delay_ms": 0,
        "ordering_window": 0,
        "conversion_multiplier": 1.0,
        "volume_multiplier": 1.0,
        "anomaly_tag": None,
    }

    for d in ALL_DOMAINS:
        if name.endswith("_" + d) or name == d:
            cfg["target_domains"] = [d]
            break

    if name == "baseline":
        return cfg

    if name == "weather_drop":
        cfg.update({
            "mode": "weather_drop",
            "missing_ratio": min(base["missing_ratio"] * 0.5, 0.10),
            "delay_ms": base["delay_ms"],
            "conversion_multiplier": base["conversion_multiplier"],
            "volume_multiplier": 1.0,
            "anomaly_tag": "weather_drop",
        })
        return cfg

    if name == "partial_missing" or name.startswith("partial_missing"):
        cfg.update({
            "mode": "partial_missing",
            "missing_ratio": base["missing_ratio"],
            "anomaly_tag": "partial_missing",
        })
        return cfg

    if name == "campaign_spike":
        cfg.update({
            "mode": "campaign_spike",
            "duplicate_ratio": base["duplicate_ratio"],
            "volume_multiplier": base["volume_multiplier"],
            "conversion_multiplier": 1.10,
            "anomaly_tag": "campaign_spike",
        })
        return cfg

    if "duplicate" in name:
        cfg.update({"mode": "duplicate", "duplicate_ratio": base["duplicate_ratio"], "anomaly_tag": "duplicate"})
    elif "delay" in name:
        cfg.update({"mode": "delay", "delay_ms": base["delay_ms"], "anomaly_tag": "delay"})
    elif "ordering" in name:
        cfg.update({"mode": "ordering", "ordering_window": base["ordering_window"], "anomaly_tag": "ordering"})
    elif "mixed" in name:
        cfg.update({
            "mode": "mixed",
            "missing_ratio": base["missing_ratio"],
            "duplicate_ratio": base["duplicate_ratio"],
            "delay_ms": base["delay_ms"],
            "ordering_window": base["ordering_window"],
            "conversion_multiplier": base["conversion_multiplier"],
            "anomaly_tag": "mixed",
        })
    else:
        cfg.update({"mode": "generic_marker", "anomaly_tag": name})
    return cfg


def mark(r: Dict[str, Any], tag: str) -> Dict[str, Any]:
    rr = dict(r)
    rr["anomaly_tag"] = tag
    return rr


def apply_missing(rows: List[Dict[str, Any]], cfg: Dict[str, Any], rng: random.Random):
    kept = []
    dropped = 0
    for r in rows:
        if r.get("service_domain") in cfg["target_domains"] and rng.random() < cfg["missing_ratio"]:
            dropped += 1
            continue
        kept.append(dict(r))
    return kept, dropped


def apply_delay(rows: List[Dict[str, Any]], cfg: Dict[str, Any]):
    out, changed = [], 0
    for r in rows:
        rr = dict(r)
        if rr.get("service_domain") in cfg["target_domains"]:
            rr["latency_ms"] = int(rr.get("latency_ms") or 0) + int(cfg["delay_ms"])
            rr["ts"] = rr["ts"] + timedelta(milliseconds=int(cfg["delay_ms"]))
            rr["anomaly_tag"] = cfg["anomaly_tag"]
            changed += 1
        out.append(rr)
    return out, changed


def apply_conversion_drop(rows: List[Dict[str, Any]], cfg: Dict[str, Any], rng: random.Random):
    out, changed = [], 0
    keep_prob = float(cfg.get("conversion_multiplier") or 1.0)
    for r in rows:
        rr = dict(r)
        if int(rr.get("is_conversion") or 0) == 1 and rr.get("service_domain") in cfg["target_domains"]:
            if rng.random() > keep_prob:
                rr["is_conversion"] = 0
                rr["anomaly_tag"] = cfg["anomaly_tag"]
                changed += 1
        out.append(rr)
    return out, changed


def apply_duplicate(rows: List[Dict[str, Any]], cfg: Dict[str, Any], rng: random.Random, mode: str):
    out, dup_cnt = [], 0
    ratio = float(cfg.get("duplicate_ratio") or 0.0)
    for idx, r in enumerate(rows):
        out.append(dict(r))
        if r.get("service_domain") in cfg["target_domains"] and rng.random() < ratio:
            rr = dict(r)
            rr["anomaly_tag"] = cfg["anomaly_tag"]
            rr["dup_group_id"] = f"{mode}_{r.get('service_domain','all')}_{idx}"
            out.append(rr)
            dup_cnt += 1
    return out, dup_cnt


def apply_volume_spike(rows: List[Dict[str, Any]], cfg: Dict[str, Any], rng: random.Random):
    multiplier = max(float(cfg.get("volume_multiplier") or 1.0), 1.0)
    extra_ratio = multiplier - 1.0
    out, added = [], 0
    for idx, r in enumerate(rows):
        out.append(dict(r))
        whole = int(extra_ratio)
        frac = extra_ratio - whole
        copies = whole + (1 if rng.random() < frac else 0)
        for c in range(copies):
            rr = dict(r)
            rr["anomaly_tag"] = cfg["anomaly_tag"]
            rr["dup_group_id"] = f"campaign_spike_{r.get('service_domain','all')}_{idx}_{c}"
            rr["ts"] = rr["ts"] + timedelta(milliseconds=1 + c)
            out.append(rr)
            added += 1
    return out, added


def apply_ordering(rows: List[Dict[str, Any]], cfg: Dict[str, Any]):
    window = int(cfg.get("ordering_window") or 0)
    if window <= 1:
        return rows, 0
    target = [dict(r) for r in rows if r.get("service_domain") in cfg["target_domains"]]
    other = [dict(r) for r in rows if r.get("service_domain") not in cfg["target_domains"]]
    out_target, changed = [], 0
    for i in range(0, len(target), window):
        block = target[i:i+window]
        if len(block) > 1:
            block = list(reversed(block))
            for j, rr in enumerate(block):
                rr["anomaly_tag"] = cfg["anomaly_tag"]
                rr["ordering_group_id"] = f"ord_{rr.get('service_domain','all')}_{i}"
                rr["ts"] = rr["ts"] + timedelta(milliseconds=j)
                changed += 1
        out_target.extend(block)
    merged = other + out_target
    merged.sort(key=lambda x: (x["ts"], x.get("raw_event_id") or 0))
    return merged, changed


def insert_queue_rows(cur, profile_id: str, dt: date, scenario_name: str, intensity: str, rows: List[Dict[str, Any]]):
    sql = """
        INSERT INTO stream_injection_event_queue
        (
            profile_id, dt, ts, raw_event_id, event_name, service_domain, funnel_stage, is_conversion,
            uid, pcid, sid, status, latency_ms, source_type, path, evt, anomaly_tag,
            scenario_name, scenario_intensity, dup_group_id, ordering_group_id, queue_sequence, payload_json
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    for seq, r in enumerate(rows, start=1):
        payload = {k: (str(v) if k in ("dt", "ts") else v) for k, v in r.items()}
        payload["scenario_name"] = scenario_name
        payload["scenario_intensity"] = intensity
        cur.execute(sql, (
            profile_id, r["dt"], r["ts"], r.get("raw_event_id"), r.get("event_name"), r.get("service_domain"),
            r.get("funnel_stage"), int(r.get("is_conversion") or 0), r.get("uid"), r.get("pcid"), r.get("sid"),
            r.get("status"), r.get("latency_ms"), r.get("source_type"), r.get("path"), r.get("evt"),
            r.get("anomaly_tag"), scenario_name, intensity, r.get("dup_group_id"), r.get("ordering_group_id"),
            seq, json.dumps(payload, ensure_ascii=False)
        ))


def log_result(cur, profile_id: str, dt: date, scenario_name: str, metric: str, value: float, detail: Dict[str, Any]):
    cur.execute("""
        INSERT INTO scenario_adapter_result_log
        (profile_id, dt, scenario_name, adapter_name, result_metric, result_value, result_status, detail)
        VALUES (%s,%s,%s,'stream_injection_adapter_v7',%s,%s,'ok',%s)
    """, (profile_id, dt, scenario_name, metric, value, json.dumps(detail, ensure_ascii=False)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-host", required=True)
    ap.add_argument("--db-port", type=int, required=True)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", default="")
    ap.add_argument("--db-name", required=True)
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
            ensure_tables(cur)
            if args.clear_range:
                cur.execute("""
                    DELETE FROM stream_injection_event_queue
                    WHERE profile_id=%s AND dt BETWEEN %s AND %s
                """, (args.profile_id, args.dt_from, args.dt_to))

            for dt in daterange(args.dt_from, args.dt_to):
                run = fetch_run(cur, args.profile_id, dt)
                cfg = scenario_config(run)
                original = fetch_events(cur, args.profile_id, dt)
                working = [dict(r) for r in original]

                stats = {
                    "source_rows": len(original),
                    "queue_rows": 0,
                    "missing_dropped_rows": 0,
                    "duplicate_rows": 0,
                    "delay_rows": 0,
                    "ordering_rows": 0,
                    "conversion_changed_rows": 0,
                    "volume_added_rows": 0,
                }

                if cfg["mode"] == "partial_missing":
                    working, stats["missing_dropped_rows"] = apply_missing(working, cfg, rng)
                elif cfg["mode"] == "weather_drop":
                    working, stats["missing_dropped_rows"] = apply_missing(working, cfg, rng)
                    working, stats["delay_rows"] = apply_delay(working, cfg)
                    working, stats["conversion_changed_rows"] = apply_conversion_drop(working, cfg, rng)
                elif cfg["mode"] == "campaign_spike":
                    working, stats["volume_added_rows"] = apply_volume_spike(working, cfg, rng)
                elif cfg["mode"] == "duplicate":
                    working, stats["duplicate_rows"] = apply_duplicate(working, cfg, rng, "duplicate")
                elif cfg["mode"] == "delay":
                    working, stats["delay_rows"] = apply_delay(working, cfg)
                elif cfg["mode"] == "ordering":
                    working, stats["ordering_rows"] = apply_ordering(working, cfg)
                elif cfg["mode"] == "mixed":
                    working, stats["missing_dropped_rows"] = apply_missing(working, cfg, rng)
                    working, stats["duplicate_rows"] = apply_duplicate(working, cfg, rng, "mixed")
                    working, stats["delay_rows"] = apply_delay(working, cfg)
                    working, stats["conversion_changed_rows"] = apply_conversion_drop(working, cfg, rng)
                    working, stats["ordering_rows"] = apply_ordering(working, cfg)
                elif cfg["mode"] == "generic_marker":
                    working = [mark(r, cfg["anomaly_tag"]) for r in working]

                stats["queue_rows"] = len(working)
                tags = Counter((r.get("anomaly_tag") or "normal") for r in working)
                detail = {
                    "config": cfg,
                    "stats": stats,
                    "tag_counts": dict(tags),
                }

                insert_queue_rows(cur, args.profile_id, dt, cfg["scenario_name"], cfg["intensity"], working)
                for k, v in stats.items():
                    log_result(cur, args.profile_id, dt, cfg["scenario_name"], k, float(v), detail)

        conn.commit()
        print("[stream_injection_adapter_v7] done")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
