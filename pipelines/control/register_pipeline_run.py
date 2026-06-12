#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pymysql

TABLE_NAME = "pipeline_run_registry"

def connect_mysql(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass, database=args.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def ensure_table(cur):
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS pipeline_run_registry (
          run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          profile_id VARCHAR(100) NOT NULL,
          dt_from DATE NOT NULL,
          dt_to DATE NOT NULL,
          processing_mode VARCHAR(20) NOT NULL,
          runtime_mode VARCHAR(20) NOT NULL,
          scenario_mode VARCHAR(50) NULL,
          source_mode VARCHAR(50) NULL,
          exogenous_mode VARCHAR(50) NULL,
          note TEXT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (run_id),
          KEY idx_prr_profile_dates (profile_id, dt_from, dt_to)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        '''
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    ap.add_argument("--db-user", default=os.getenv("DB_USER"))
    ap.add_argument("--db-pass", default=os.getenv("DB_PASSWORD", ""))
    ap.add_argument("--db-name", default=os.getenv("DB_NAME"))
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--processing-mode", default="stream")
    ap.add_argument("--runtime-mode", default="replay")
    ap.add_argument("--scenario-mode", default="baseline")
    ap.add_argument("--source-mode", default="simulator_file_generate")
    ap.add_argument("--exogenous-mode", default="static")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            ensure_table(cur)
            cur.execute(
                f'''
                INSERT INTO {TABLE_NAME}
                (profile_id, dt_from, dt_to, processing_mode, runtime_mode, scenario_mode, source_mode, exogenous_mode, note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ''',
                (
                    args.profile_id, args.dt_from, args.dt_to, args.processing_mode, args.runtime_mode,
                    args.scenario_mode, args.source_mode, args.exogenous_mode, args.note
                ),
            )
            run_id = cur.lastrowid
        conn.commit()
        print(run_id)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
