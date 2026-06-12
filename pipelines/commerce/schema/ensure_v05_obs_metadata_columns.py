#!/usr/bin/env python3
from __future__ import annotations
import argparse
import pymysql

# CASE-OBS-001 Phase2-A native app metadata propagation.
# canonical_events is the behavior canonical layer, and canonical_behavior_events is the
# v0.5 behavior anchor used by transaction/state reconciliation. Both need app/sdk
# metadata so observability gaps can later be linked to business mappings.
TABLE_COLUMNS = {
    "stg_webserver_log_hit": {
        "app_platform": "VARCHAR(64) NULL",
        "app_version": "VARCHAR(64) NULL",
        "sdk_version": "VARCHAR(64) NULL",
    },
    "stg_wc_log_hit": {
        "app_platform": "VARCHAR(64) NULL",
        "app_version": "VARCHAR(64) NULL",
        "sdk_version": "VARCHAR(64) NULL",
    },
    "event_log_raw": {
        "app_platform": "VARCHAR(64) NULL",
        "app_version": "VARCHAR(64) NULL",
        "sdk_version": "VARCHAR(64) NULL",
    },
    "canonical_events": {
        "app_platform": "VARCHAR(64) NULL",
        "app_version": "VARCHAR(64) NULL",
        "sdk_version": "VARCHAR(64) NULL",
    },
    "canonical_behavior_events": {
        "app_platform": "VARCHAR(64) NULL",
        "app_version": "VARCHAR(64) NULL",
        "sdk_version": "VARCHAR(64) NULL",
    },
}
INDEXES = {
    "stg_webserver_log_hit": "idx_v05_swh_obs_meta",
    "stg_wc_log_hit": "idx_v05_wc_obs_meta",
    "event_log_raw": "idx_v05_elr_obs_meta",
    "canonical_events": "idx_v05_ce_obs_meta",
    "canonical_behavior_events": "idx_v05_cb_obs_meta",
}

def parse_args():
    p=argparse.ArgumentParser(description="Ensure CASE-OBS-001 Phase2 app/sdk metadata columns exist.")
    p.add_argument("--db-host", required=True); p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True); p.add_argument("--db-pass", required=True); p.add_argument("--db-name", required=True)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()

def connect(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def table_exists(cur,t):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return int(cur.fetchone()["cnt"]) == 1

def column_exists(cur,t,c):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s",(t,c))
    return int(cur.fetchone()["cnt"]) == 1

def index_exists(cur,t,i):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=%s AND index_name=%s",(t,i))
    return int(cur.fetchone()["cnt"]) > 0

def main():
    a=parse_args(); con=connect(a)
    statements=[]
    try:
        with con.cursor() as cur:
            for table, cols in TABLE_COLUMNS.items():
                if not table_exists(cur, table):
                    print(f"[SKIP] missing table {table}")
                    continue
                for col, ddl in cols.items():
                    if not column_exists(cur, table, col):
                        statements.append(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                idx = INDEXES.get(table)
                if idx and not index_exists(cur, table, idx):
                    statements.append(
                        f"ALTER TABLE {table} ADD KEY {idx} "
                        f"(profile_id, source_gen_run_id, app_platform, app_version, sdk_version)"
                    )
            for stmt in statements:
                print(stmt + ";")
                if not a.dry_run:
                    cur.execute(stmt)
        if a.dry_run:
            con.rollback(); print(f"[DRY_RUN] statements={len(statements)}")
        else:
            con.commit(); print(f"[DONE] statements={len(statements)}")
    except Exception:
        con.rollback(); raise
    finally:
        con.close()

if __name__ == "__main__":
    main()
