#!/usr/bin/env python3
from __future__ import annotations
import argparse
import pymysql

TABLE_DATE_COL = {
    "stg_webserver_log_hit": "dt",
    "stg_wc_log_hit": "dt",
    "event_log_raw": "dt",
    "canonical_events": "target_date",
    "canonical_behavior_events": "target_date",
}
META_COLS = ["app_platform", "app_version", "sdk_version"]

def parse_args():
    p=argparse.ArgumentParser(description="Validate CASE-OBS-001 app/sdk metadata propagation.")
    p.add_argument("--db-host", required=True); p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True); p.add_argument("--db-pass", required=True); p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True); p.add_argument("--target-date", required=True)
    p.add_argument("--run-id", type=int); p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--fail-on-null", action="store_true", default=True)
    p.add_argument("--require-native", action="store_true", help="Fail unless ios_app and android_app metadata are present in canonical_events.")
    return p.parse_args()

def connect(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=True, cursorclass=pymysql.cursors.DictCursor)

def table_exists(cur,t):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return int(cur.fetchone()["cnt"]) == 1

def cols(cur,t):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return {r["column_name"] for r in cur.fetchall()}

def main():
    a=parse_args(); con=connect(a); failed=False
    try:
        native_platforms_seen = set()
        with con.cursor() as cur:
            for table, date_col in TABLE_DATE_COL.items():
                if not table_exists(cur, table):
                    print(f"[SKIP] {table}: missing table")
                    continue
                c=cols(cur, table)
                missing=[x for x in META_COLS if x not in c]
                if missing:
                    failed=True; print(f"[FAIL] {table}: missing columns {missing}"); continue
                where=["profile_id=%s", f"{date_col}=%s"]; params=[a.profile_id, a.target_date]
                if a.source_gen_run_id and "source_gen_run_id" in c:
                    where.append("source_gen_run_id=%s"); params.append(a.source_gen_run_id)
                if a.run_id and "run_id" in c:
                    where.append("run_id=%s"); params.append(a.run_id)
                where_sql=" AND ".join(where)
                cur.execute(f"SELECT COUNT(*) cnt FROM {table} WHERE {where_sql}", params)
                total=int(cur.fetchone()["cnt"] or 0)
                null_expr=" OR ".join([f"{x} IS NULL OR {x}=''" for x in META_COLS])
                cur.execute(f"SELECT COUNT(*) cnt FROM {table} WHERE {where_sql} AND ({null_expr})", params)
                nulls=int(cur.fetchone()["cnt"] or 0)
                cur.execute(f"""
                    SELECT app_platform, app_version, sdk_version, COUNT(*) cnt
                    FROM {table}
                    WHERE {where_sql}
                    GROUP BY app_platform, app_version, sdk_version
                    ORDER BY cnt DESC
                    LIMIT 10
                """, params)
                groups=cur.fetchall()
                status="PASS" if total > 0 and nulls == 0 else "FAIL"
                if status == "FAIL": failed=True
                print(f"[{status}] {table}: total={total} null_or_blank={nulls}")
                for g in groups:
                    platform = str(g.get('app_platform') or '')
                    if table == "canonical_events":
                        native_platforms_seen.add(platform)
                    print(f"  - {g.get('app_platform')}/{g.get('app_version')}/{g.get('sdk_version')}: {g.get('cnt')}")
            if a.require_native:
                missing_native = {"ios_app", "android_app"} - native_platforms_seen
                if missing_native:
                    failed = True
                    print(f"[FAIL] native metadata missing in canonical_events: {sorted(missing_native)}")
                else:
                    print("[PASS] native metadata present in canonical_events: ios_app/android_app")
        if failed and a.fail_on_null:
            raise SystemExit(1)
    finally:
        con.close()

if __name__ == "__main__":
    main()
