#!/usr/bin/env python3
from __future__ import annotations
import argparse
import pymysql

def parse_args():
    p=argparse.ArgumentParser(description="Fast stage scenario identity validation for one source_gen_run_id.")
    p.add_argument("--db-host",required=True); p.add_argument("--db-port",type=int,required=True)
    p.add_argument("--db-user",required=True); p.add_argument("--db-pass",required=True); p.add_argument("--db-name",required=True)
    p.add_argument("--profile-id",required=True); p.add_argument("--target-date",required=True); p.add_argument("--scenario-name",required=True)
    p.add_argument("--source-gen-run-id",type=int,required=True)
    p.add_argument("--expected-source-generation-scenario")
    return p.parse_args()

def connect(a):
    return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset="utf8mb4",autocommit=True,cursorclass=pymysql.cursors.DictCursor)

def has_col(cur, table, col):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s",(table,col))
    return int(cur.fetchone()["cnt"])==1

def main():
    a=parse_args(); con=connect(a)
    try:
        with con.cursor() as cur:
            missing=[c for c in ["scenario_id","scenario_name","source_generation_scenario","source_gen_run_id"] if not has_col(cur,"stg_webserver_log_hit",c)]
            if missing:
                print(f"[FAIL] stg_webserver_log_hit missing columns: {','.join(missing)}"); return 1
            cur.execute("""
                SELECT scenario_id, scenario_name, source_generation_scenario, source_gen_run_id, COUNT(*) cnt
                FROM stg_webserver_log_hit
                WHERE profile_id=%s AND dt=%s AND source_gen_run_id=%s
                GROUP BY scenario_id, scenario_name, source_generation_scenario, source_gen_run_id
                ORDER BY cnt DESC
            """,(a.profile_id,a.target_date,a.source_gen_run_id))
            rows=cur.fetchall()
    finally:
        con.close()
    if not rows:
        print("[FAIL] no stg_webserver_log_hit rows for source_gen_run_id"); return 1
    total=0; mismatch=0
    for r in rows:
        cnt=int(r["cnt"]); total+=cnt
        sid=r.get("scenario_id"); sname=r.get("scenario_name"); sgen=r.get("source_generation_scenario")
        print(f"[IDENTITY] scenario_id={sid} scenario_name={sname} source_generation_scenario={sgen} source_gen_run_id={r.get('source_gen_run_id')} cnt={cnt}")
        if sid != a.scenario_name or sname != a.scenario_name: mismatch += cnt
        if a.expected_source_generation_scenario and sgen != a.expected_source_generation_scenario: mismatch += cnt
    if mismatch:
        print(f"[FAIL] scenario identity mismatch rows={mismatch} total={total}"); return 1
    print(f"[OK] stage scenario identity valid rows={total} scenario_name={a.scenario_name}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
