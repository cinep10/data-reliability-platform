#!/usr/bin/env python3
from __future__ import annotations
import argparse
import pymysql

CHECK_TABLES = ["stg_webserver_log_hit", "stg_wc_log_hit", "event_log_raw", "canonical_events"]

def parse_args():
    p = argparse.ArgumentParser(description="Validate only one active source_gen_run_id remains for a scenario/date/profile.")
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--active-source-gen-run-id", type=int, required=True)
    p.add_argument("--warn-only", action="store_true")
    return p.parse_args()

def connect(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=True, cursorclass=pymysql.cursors.DictCursor)

def table_exists(cur, t):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (t,))
    return int(cur.fetchone()["cnt"]) == 1

def cols(cur, t):
    if not table_exists(cur, t):
        return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (t,))
    return {str(r["column_name"]) for r in cur.fetchall()}

def main():
    a = parse_args()
    failures = []
    con = connect(a)
    try:
        with con.cursor() as cur:
            for t in CHECK_TABLES:
                if not table_exists(cur, t):
                    print(f"[SKIP] {t} missing"); continue
                cs = cols(cur, t)
                if "source_gen_run_id" not in cs:
                    print(f"[SKIP] {t} no source_gen_run_id"); continue
                wh = []; ps = []
                if "profile_id" in cs: wh.append("profile_id=%s"); ps.append(a.profile_id)
                if "target_date" in cs: wh.append("target_date=%s"); ps.append(a.target_date)
                elif "dt" in cs: wh.append("dt=%s"); ps.append(a.target_date)
                if "scenario_name" in cs: wh.append("scenario_name=%s"); ps.append(a.scenario_name)
                elif "scenario_id" in cs: wh.append("scenario_id=%s"); ps.append(a.scenario_name)
                if not wh: continue
                sql = f"SELECT source_gen_run_id, COUNT(*) cnt FROM `{t}` WHERE {' AND '.join(wh)} GROUP BY source_gen_run_id ORDER BY source_gen_run_id"
                cur.execute(sql, tuple(ps))
                rows = cur.fetchall()
                print(f"[ACTIVE_CHECK] {t}")
                for r in rows:
                    print(f"  source_gen_run_id={r.get('source_gen_run_id')} cnt={r.get('cnt')}")
                    if int(r.get("source_gen_run_id") or -1) != a.active_source_gen_run_id:
                        failures.append(f"{t}: unexpected source_gen_run_id={r.get('source_gen_run_id')}")
    finally:
        con.close()
    if failures:
        for f in failures: print(f"[FAIL] {f}")
        return 0 if a.warn_only else 1
    print(f"[OK] active source_gen_run_id guard passed scenario={a.scenario_name} active={a.active_source_gen_run_id}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
