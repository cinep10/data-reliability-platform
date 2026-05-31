#!/usr/bin/env python3
from __future__ import annotations
import argparse
import pymysql

TABLE_COLUMNS = {
    "stg_webserver_log_hit": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "event_log_raw": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "canonical_events": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "stg_event_batch": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "stg_event_stream": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "stream_replay_event": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "canonical_behavior_events": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "canonical_transaction_events": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "canonical_state_events": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "behavior_transaction_mapping": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
    "transaction_state_mapping": {"scenario_id":"VARCHAR(100) NULL","scenario_name":"VARCHAR(100) NULL","source_generation_scenario":"VARCHAR(100) NULL"},
}

def parse_args():
    p=argparse.ArgumentParser(description="Ensure v0.5 scenario identity columns exist.")
    p.add_argument("--db-host",required=True); p.add_argument("--db-port",type=int,required=True)
    p.add_argument("--db-user",required=True); p.add_argument("--db-pass",required=True); p.add_argument("--db-name",required=True)
    p.add_argument("--dry-run",action="store_true")
    return p.parse_args()

def connect(a):
    return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset="utf8mb4",autocommit=False,cursorclass=pymysql.cursors.DictCursor)

def table_exists(cur,t):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return int(cur.fetchone()["cnt"])==1

def column_exists(cur,t,c):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s",(t,c))
    return int(cur.fetchone()["cnt"])==1

def main():
    a=parse_args(); con=connect(a)
    try:
        with con.cursor() as cur:
            for table, cols in TABLE_COLUMNS.items():
                if not table_exists(cur,table):
                    print(f"[SKIP] missing table {table}"); continue
                for col, ddl in cols.items():
                    if column_exists(cur,table,col):
                        print(f"[OK] column exists {table}.{col}"); continue
                    sql=f"ALTER TABLE `{table}` ADD COLUMN `{col}` {ddl}"
                    print(f"[ALTER] {sql}")
                    if not a.dry_run: cur.execute(sql)
        con.rollback() if a.dry_run else con.commit()
    except Exception:
        con.rollback(); raise
    finally:
        con.close()
    print("[DONE] ensure_v05_scenario_identity_columns")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
