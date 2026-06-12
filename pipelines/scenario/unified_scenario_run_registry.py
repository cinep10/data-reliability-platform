from __future__ import annotations

import argparse
import json
import pymysql


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


def add_column_if_missing(cur, table_name: str, col_name: str, ddl: str) -> None:
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, col_name),
    )
    if int(cur.fetchone()["cnt"]) == 0:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def ensure_tables(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS scenario_experiment_run (
          scenario_run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          profile_id VARCHAR(64) NOT NULL,
          scenario_name VARCHAR(100) NOT NULL,
          scenario_type VARCHAR(50) NOT NULL,
          dt_from DATE NOT NULL,
          dt_to DATE NOT NULL,
          parameters_json TEXT NULL,
          note VARCHAR(255) NULL,
          started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (scenario_run_id),
          KEY idx_scenario_run_profile_dt (profile_id, dt_from, dt_to)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    add_column_if_missing(cur, "scenario_experiment_run", "scenario_severity", "scenario_severity VARCHAR(20) NULL")
    add_column_if_missing(cur, "scenario_experiment_run", "scenario_intensity", "scenario_intensity VARCHAR(20) NULL")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", default="")
    ap.add_argument("--db-name", required=True)
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--scenario-name", required=True)
    ap.add_argument("--scenario-type", default="unified")
    ap.add_argument("--scenario-intensity", default="medium")
    ap.add_argument("--scenario-severity", default="medium")
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--parameters-json", default="{}")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            ensure_tables(cur)
            cur.execute(
                """
                INSERT INTO scenario_experiment_run
                (profile_id, scenario_name, scenario_type, dt_from, dt_to, parameters_json, note, scenario_severity, scenario_intensity)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    args.profile_id,
                    args.scenario_name,
                    args.scenario_type,
                    args.dt_from,
                    args.dt_to,
                    args.parameters_json,
                    args.note or f"unified scenario run {args.scenario_name}:{args.scenario_intensity}",
                    args.scenario_severity,
                    args.scenario_intensity,
                ),
            )
            run_id = cur.lastrowid
        conn.commit()
        print(run_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
