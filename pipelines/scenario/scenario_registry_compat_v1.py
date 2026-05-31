#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pymysql


INTENSITY_NUMERIC = {
    "baseline": 0.0,
    "mild": 0.3,
    "medium": 0.6,
    "high": 1.0,
}


def connect(args):
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


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scenario_experiment_run (
            scenario_run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            profile_id VARCHAR(64) NOT NULL,
            scenario_name VARCHAR(100) NOT NULL,
            scenario_type VARCHAR(30) NOT NULL DEFAULT 'stream',
            dt_from DATE NOT NULL,
            dt_to DATE NOT NULL,
            parameters_json LONGTEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (scenario_run_id),
            KEY idx_profile_dt (profile_id, dt_from, dt_to),
            KEY idx_profile_scenario (profile_id, scenario_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def scenario_params(name: str, intensity: str, route: str) -> dict:
    lname = (name or "baseline").lower()
    i = (intensity or "medium").lower()
    p = {
        "intensity": i,
        "intensity_numeric": INTENSITY_NUMERIC.get(i, 0.6),
        "route": route,
    }

    if lname == "weather_drop":
        p.update({
            "state_subtype": "weather",
            "state_level": i,
            "weather_type": "heavy_rain" if i in ("medium", "high") else "rain",
            "stream_effect": "weather_drop",
            "anomaly_tag": "weather_drop",
        })
    elif lname == "campaign_spike":
        p.update({
            "state_subtype": "campaign",
            "state_level": i,
            "campaign_flag": "spike",
            "stream_effect": "volume_spike",
            "anomaly_tag": "campaign_spike",
        })
    elif lname.startswith("partial_missing"):
        p.update({
            "state_subtype": "missing",
            "state_level": i,
            "stream_effect": "partial_missing",
            "anomaly_tag": "partial_missing",
        })
    elif lname == "baseline":
        p.update({
            "state_subtype": "baseline",
            "state_level": "normal",
            "stream_effect": "none",
        })
    else:
        p.update({
            "state_subtype": "generic",
            "state_level": i,
            "stream_effect": lname,
            "anomaly_tag": lname,
        })
    return p


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
    ap.add_argument("--scenario-name", required=True)
    ap.add_argument("--scenario-intensity", default="medium")
    ap.add_argument("--scenario-type", default="stream")
    ap.add_argument("--route", default="command")
    ap.add_argument("--replace-range", action="store_true")
    args = ap.parse_args()

    conn = connect(args)
    try:
        with conn.cursor() as cur:
            ensure_table(cur)
            if args.replace_range:
                cur.execute("""
                    DELETE FROM scenario_experiment_run
                    WHERE profile_id=%s
                      AND dt_from >= %s
                      AND dt_to <= %s
                """, (args.profile_id, args.dt_from, args.dt_to))

            cur.execute("""
                INSERT INTO scenario_experiment_run
                (profile_id, scenario_name, scenario_type, dt_from, dt_to, parameters_json)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                args.profile_id,
                args.scenario_name,
                args.scenario_type,
                args.dt_from,
                args.dt_to,
                json.dumps(scenario_params(args.scenario_name, args.scenario_intensity, args.route), ensure_ascii=False),
            ))

        conn.commit()
        print(
            "[scenario_registry_compat_v1] done "
            f"scenario_name={args.scenario_name} intensity={args.scenario_intensity} route={args.route}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
