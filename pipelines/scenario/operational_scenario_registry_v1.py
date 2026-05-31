#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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


def params(args):
    name = args.scenario_name
    intensity = args.scenario_intensity
    p = {
        "intensity": intensity,
        "intensity_numeric": INTENSITY_NUMERIC.get((intensity or "medium").lower(), 0.6),
        "route": "operational",
        "op_scenario_name": name,
    }
    if name == "lag_spike":
        p.update({
            "scenario_subtype": "processing_delay",
            "lag_spike_from": os.environ.get("LAG_SPIKE_FROM"),
            "lag_spike_to": os.environ.get("LAG_SPIKE_TO"),
            "lag_spike_sleep_ms": os.environ.get("LAG_SPIKE_SLEEP_MS"),
            "lag_spike_every_n": os.environ.get("LAG_SPIKE_EVERY_N"),
        })
    elif name == "no_data":
        p.update({
            "scenario_subtype": "no_data_gap",
            "no_data_from": os.environ.get("NO_DATA_FROM"),
            "no_data_to": os.environ.get("NO_DATA_TO"),
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
                      AND scenario_type='operational'
                      AND dt_from >= %s
                      AND dt_to <= %s
                """, (args.profile_id, args.dt_from, args.dt_to))

            cur.execute("""
                INSERT INTO scenario_experiment_run
                (profile_id, scenario_name, scenario_type, dt_from, dt_to, parameters_json)
                VALUES (%s, %s, 'operational', %s, %s, %s)
            """, (
                args.profile_id,
                args.scenario_name,
                args.dt_from,
                args.dt_to,
                json.dumps(params(args), ensure_ascii=False),
            ))

        conn.commit()
        print(f"[operational_scenario_registry_v1] done scenario_name={args.scenario_name}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
