#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from typing import Any, Dict, List, Set

import pymysql


INTENSITY_MAP = {
    "mild": {
        "missing_rate": 0.03,
        "duplicate_rate": 0.02,
        "delay_ms": 1500,
        "shuffle_window": 5,
        "volume_multiplier": 0.98,
        "conversion_multiplier": 0.90,
        "timeout_multiplier": 1.10,
    },
    "medium": {
        "missing_rate": 0.08,
        "duplicate_rate": 0.05,
        "delay_ms": 5000,
        "shuffle_window": 10,
        "volume_multiplier": 0.92,
        "conversion_multiplier": 0.75,
        "timeout_multiplier": 1.50,
    },
    "high": {
        "missing_rate": 0.15,
        "duplicate_rate": 0.10,
        "delay_ms": 15000,
        "shuffle_window": 20,
        "volume_multiplier": 0.80,
        "conversion_multiplier": 0.55,
        "timeout_multiplier": 2.00,
    },
}

INTENSITY_NUMERIC = {
    "baseline": 0.0,
    "mild": 0.3,
    "medium": 0.6,
    "high": 1.0,
}


def intensity_to_numeric(intensity: str | None) -> float:
    return INTENSITY_NUMERIC.get((intensity or "medium").lower(), 0.6)


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


def parse_scenario(scenario_name: str, intensity: str, params: dict[str, Any] | None = None) -> Dict[str, Any]:
    params = params or {}
    scenario_name = scenario_name or "baseline"
    lname = scenario_name.lower()
    intensity = (intensity or params.get("intensity") or "medium").lower()
    base = INTENSITY_MAP.get(intensity, INTENSITY_MAP["medium"])

    cfg: Dict[str, Any] = {
        "scenario_name": scenario_name,
        "intensity": intensity,
        "mode": "baseline",
        "target_service_domain": None,
        "state_subtype": params.get("state_subtype"),
        "state_level": params.get("state_level") or intensity,
        "weather_type": params.get("weather_type"),
        "missing_rate": 0.0,
        "duplicate_rate": 0.0,
        "delay_ms": 0,
        "shuffle_window": 0,
        "volume_multiplier": 1.0,
        "conversion_multiplier": 1.0,
        "timeout_multiplier": 1.0,
        "drop_enabled": False,
        "duplicate_enabled": False,
        "delay_enabled": False,
        "ordering_enabled": False,
        "anomaly_tag": params.get("anomaly_tag"),
    }

    if lname == "baseline":
        cfg.update({
            "state_subtype": "baseline",
            "state_level": "normal",
            "weather_type": "clear",
        })
        return cfg

    if lname == "weather_drop":
        cfg.update({
            "mode": "weather_drop",
            "target_service_domain": None,
            "state_subtype": "weather",
            "state_level": intensity,
            "weather_type": params.get("weather_type") or ("heavy_rain" if intensity in ("medium", "high") else "rain"),
            "missing_rate": base["missing_rate"],
            "delay_ms": base["delay_ms"],
            "volume_multiplier": base["volume_multiplier"],
            "conversion_multiplier": base["conversion_multiplier"],
            "timeout_multiplier": base["timeout_multiplier"],
            "drop_enabled": True,
            "delay_enabled": True,
            "anomaly_tag": params.get("anomaly_tag") or "weather_drop",
        })
        return cfg


    if lname == "campaign_spike":
        cfg.update({
            "mode": "campaign_spike",
            "target_service_domain": None,
            "state_subtype": "campaign",
            "state_level": intensity,
            "weather_type": params.get("weather_type") or "clear",
            "missing_rate": 0.0,
            "duplicate_rate": base["duplicate_rate"],
            "delay_ms": 0,
            "volume_multiplier": 1.5 if intensity == "medium" else (2.0 if intensity == "high" else 1.25),
            "conversion_multiplier": 1.10 if intensity in ("medium", "high") else 1.05,
            "timeout_multiplier": 1.0,
            "duplicate_enabled": True,
            "anomaly_tag": params.get("anomaly_tag") or "campaign_spike",
        })
        return cfg

    if lname == "partial_missing":
        cfg.update({
            "mode": "partial_missing",
            "target_service_domain": None,
            "state_subtype": "missing",
            "state_level": intensity,
            "weather_type": params.get("weather_type") or "clear",
            "missing_rate": base["missing_rate"],
            "volume_multiplier": base["volume_multiplier"],
            "conversion_multiplier": 1.0,
            "timeout_multiplier": 1.0,
            "drop_enabled": True,
            "anomaly_tag": params.get("anomaly_tag") or "partial_missing",
        })
        return cfg

    if lname.startswith("partial_missing_"):
        domain = lname.replace("partial_missing_", "", 1)
        cfg.update({
            "mode": "partial_missing",
            "target_service_domain": domain,
            "missing_rate": base["missing_rate"],
            "volume_multiplier": base["volume_multiplier"],
            "drop_enabled": True,
            "anomaly_tag": "partial_missing",
        })
    elif lname.startswith("duplicate_"):
        domain = lname.replace("duplicate_", "", 1)
        cfg.update({
            "mode": "duplicate",
            "target_service_domain": domain,
            "duplicate_rate": base["duplicate_rate"],
            "duplicate_enabled": True,
            "anomaly_tag": "duplicate",
        })
    elif lname.startswith("delay_"):
        domain = lname.replace("delay_", "", 1)
        cfg.update({
            "mode": "delay",
            "target_service_domain": domain,
            "delay_ms": base["delay_ms"],
            "timeout_multiplier": base["timeout_multiplier"],
            "delay_enabled": True,
            "anomaly_tag": "delay",
        })
    elif lname.startswith("ordering_"):
        domain = lname.replace("ordering_", "", 1)
        cfg.update({
            "mode": "ordering",
            "target_service_domain": domain,
            "shuffle_window": base["shuffle_window"],
            "ordering_enabled": True,
            "anomaly_tag": "ordering",
        })
    elif lname.startswith("mixed_"):
        domain = lname.replace("mixed_", "", 1)
        cfg.update({
            "mode": "mixed",
            "target_service_domain": domain,
            "missing_rate": base["missing_rate"],
            "duplicate_rate": base["duplicate_rate"],
            "delay_ms": base["delay_ms"],
            "shuffle_window": base["shuffle_window"],
            "volume_multiplier": base["volume_multiplier"],
            "conversion_multiplier": base["conversion_multiplier"],
            "timeout_multiplier": base["timeout_multiplier"],
            "drop_enabled": True,
            "duplicate_enabled": True,
            "delay_enabled": True,
            "ordering_enabled": True,
            "anomaly_tag": "mixed",
        })
    return cfg


def table_columns(cur, table_name: str) -> Set[str]:
    cur.execute(f"SHOW COLUMNS FROM {table_name}")
    return {r["Field"] for r in cur.fetchall()}


def build_insert_sql(table_name: str, cols: List[str]) -> str:
    placeholders = ",".join(["%s"] * len(cols))
    return f"INSERT INTO {table_name} ({','.join(cols)}) VALUES ({placeholders})"


def build_update_sql(table_name: str, cols: List[str], key_cols: Set[str]) -> str:
    non_keys = [c for c in cols if c not in key_cols]
    if not non_keys:
        return ""
    updates = ",".join([f"{c}=VALUES({c})" for c in non_keys])
    return f" ON DUPLICATE KEY UPDATE {updates}"


def put_if_col(record: dict[str, Any], cols: Set[str], key: str, value: Any):
    if key in cols:
        record[key] = value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-host", required=True)
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", default="")
    ap.add_argument("--db-name", required=True)
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--target-table", default="exogenous_state_timeline")
    ap.add_argument("--clear-range", action="store_true")
    args = ap.parse_args()

    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            cols = table_columns(cur, args.target_table)

            if args.clear_range and {"profile_id", "dt"}.issubset(cols):
                cur.execute(
                    f"DELETE FROM {args.target_table} WHERE profile_id=%s AND dt BETWEEN %s AND %s",
                    (args.profile_id, args.dt_from, args.dt_to),
                )

            cur.execute(
                """
                SELECT profile_id, scenario_name, scenario_type, dt_from, dt_to, parameters_json
                FROM scenario_experiment_run
                WHERE profile_id=%s
                  AND dt_from >= %s
                  AND dt_to <= %s
                ORDER BY dt_from, dt_to, scenario_run_id
                """,
                (args.profile_id, args.dt_from, args.dt_to),
            )
            rows = cur.fetchall()
            inserted = 0

            for row in rows:
                params = json.loads(row.get("parameters_json") or "{}")
                intensity = params.get("intensity", "medium")
                cfg = parse_scenario(row["scenario_name"], intensity, params)

                day = row["dt_from"]
                while day <= row["dt_to"]:
                    payload = {
                        "scenario_name": row["scenario_name"],
                        "scenario_type": row.get("scenario_type") or "stream",
                        **cfg,
                    }

                    record: Dict[str, Any] = {}
                    put_if_col(record, cols, "profile_id", row["profile_id"])
                    put_if_col(record, cols, "dt", day)
                    put_if_col(record, cols, "hh", 23)
                    put_if_col(record, cols, "scenario_name", row["scenario_name"])
                    put_if_col(record, cols, "scenario_type", row.get("scenario_type") or "stream")
                    put_if_col(record, cols, "scenario_intensity", intensity_to_numeric(intensity))
                    put_if_col(record, cols, "intensity", intensity)
                    put_if_col(record, cols, "state_subtype", cfg["state_subtype"])
                    put_if_col(record, cols, "state_level", cfg["state_level"])
                    put_if_col(record, cols, "weather_type", cfg["weather_type"])
                    put_if_col(record, cols, "target_service_domain", cfg["target_service_domain"])
                    put_if_col(record, cols, "mode", cfg["mode"])
                    put_if_col(record, cols, "volume_multiplier", cfg["volume_multiplier"])
                    put_if_col(record, cols, "conversion_multiplier", cfg["conversion_multiplier"])
                    put_if_col(record, cols, "timeout_multiplier", cfg["timeout_multiplier"])
                    put_if_col(record, cols, "missing_rate", cfg["missing_rate"])
                    put_if_col(record, cols, "duplicate_rate", cfg["duplicate_rate"])
                    put_if_col(record, cols, "delay_ms", cfg["delay_ms"])
                    put_if_col(record, cols, "shuffle_window", cfg["shuffle_window"])
                    put_if_col(record, cols, "anomaly_tag", cfg["anomaly_tag"])
                    put_if_col(record, cols, "state_json", json.dumps(payload, ensure_ascii=False))
                    put_if_col(record, cols, "state_value", json.dumps(payload, ensure_ascii=False))

                    if not record:
                        raise RuntimeError(f"No compatible writable columns found in {args.target_table}")

                    key_cols = {"profile_id", "dt", "hh", "scenario_name"} & set(record.keys())
                    sql = build_insert_sql(args.target_table, list(record.keys()))
                    upd = build_update_sql(args.target_table, list(record.keys()), key_cols)
                    cur.execute(sql + upd, list(record.values()))
                    inserted += 1
                    day = day + timedelta(days=1)

        conn.commit()
        print(f"[build_exogenous_timeline_from_registry_v4_2] done inserted={inserted}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
