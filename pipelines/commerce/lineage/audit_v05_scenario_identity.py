#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import pymysql

DEFAULT_TABLES=[
"stg_webserver_log_hit","event_log_raw","canonical_events","stg_event_batch","stg_event_stream","stream_replay_event",
"canonical_behavior_events","canonical_transaction_events","canonical_state_events","behavior_transaction_mapping","transaction_state_mapping",
"v05_runtime_evidence_day","v05_ml_feature_snapshot_day","v05_ai_validation_result_day","v05_ai_reliability_score_day"]

def parse_args():
    p=argparse.ArgumentParser(description="Audit v0.5 scenario identity propagation.")
    p.add_argument("--db-host",required=True); p.add_argument("--db-port",type=int,required=True)
    p.add_argument("--db-user",required=True); p.add_argument("--db-pass",required=True); p.add_argument("--db-name",required=True)
    p.add_argument("--profile-id",required=True); p.add_argument("--target-date",required=True); p.add_argument("--scenario-name",required=True)
    p.add_argument("--source-gen-run-id",type=int); p.add_argument("--run-id",type=int)
    p.add_argument("--tables",default=",".join(DEFAULT_TABLES)); p.add_argument("--fail-on-mismatch",action="store_true"); p.add_argument("--json-out")
    return p.parse_args()

def connect(a):
    return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset="utf8mb4",autocommit=True,cursorclass=pymysql.cursors.DictCursor)

def table_exists(cur,t):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return int(cur.fetchone()["cnt"])==1

def columns(cur,t):
    if not table_exists(cur,t): return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return {str(r["column_name"]) for r in cur.fetchall()}

def where_scope(cs,a):
    wh=[]; ps=[]
    if "profile_id" in cs: wh.append("profile_id=%s"); ps.append(a.profile_id)
    if "target_date" in cs: wh.append("target_date=%s"); ps.append(a.target_date)
    elif "dt" in cs: wh.append("dt=%s"); ps.append(a.target_date)
    elif "event_date" in cs: wh.append("event_date=%s"); ps.append(a.target_date)
    if a.source_gen_run_id is not None and "source_gen_run_id" in cs:
        wh.append("source_gen_run_id=%s"); ps.append(a.source_gen_run_id)
    elif a.run_id is not None and "run_id" in cs:
        wh.append("run_id=%s"); ps.append(a.run_id)
    return (" AND ".join(wh) if wh else "1=1", ps)

def group_identity(cur,t,a):
    if not table_exists(cur,t):
        return {"table":t,"exists":False,"rows":0,"groups":[],"identity_columns":[]}
    cs=columns(cur,t); wh,ps=where_scope(cs,a)
    ids=[c for c in ["scenario_id","scenario_name","source_generation_scenario","source_gen_run_id","run_id"] if c in cs]
    if not ids:
        cur.execute(f"SELECT COUNT(*) cnt FROM `{t}` WHERE {wh}",tuple(ps))
        return {"table":t,"exists":True,"rows":int(cur.fetchone()["cnt"]),"groups":[],"identity_columns":[]}
    sel=", ".join(f"`{c}`" for c in ids)
    cur.execute(f"SELECT {sel}, COUNT(*) cnt FROM `{t}` WHERE {wh} GROUP BY {sel} ORDER BY cnt DESC",tuple(ps))
    groups=[dict(r) for r in cur.fetchall()]
    return {"table":t,"exists":True,"rows":sum(int(g["cnt"]) for g in groups),"groups":groups,"identity_columns":ids}

def mismatch_count(r,expected):
    cnt=0
    for g in r.get("groups",[]):
        for key in ("scenario_name","scenario_id"):
            if key in g and g[key] is not None and str(g[key]) != expected:
                cnt += int(g.get("cnt") or 0); break
    return cnt

def main():
    a=parse_args(); con=connect(a)
    try:
        with con.cursor() as cur:
            results=[group_identity(cur,t.strip(),a) for t in a.tables.split(",") if t.strip()]
    finally:
        con.close()
    total=0
    for r in results:
        if not r.get("exists"):
            print(f"[AUDIT] {r['table']}: missing"); continue
        mm=mismatch_count(r,a.scenario_name); total+=mm
        print(f"[AUDIT] {r['table']}: rows={r.get('rows',0)} mismatch_rows={mm} identity_columns={','.join(r.get('identity_columns',[]))}")
        for g in r.get("groups",[])[:10]:
            print("  - cnt="+str(g.get("cnt"))+" "+" ".join(f"{k}={g.get(k)}" for k in r.get("identity_columns",[])))
    if a.json_out:
        Path(a.json_out).write_text(json.dumps({"profile_id":a.profile_id,"target_date":a.target_date,"scenario_name":a.scenario_name,"source_gen_run_id":a.source_gen_run_id,"run_id":a.run_id,"total_mismatch_rows":total,"results":results},ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    if total>0:
        print(f"[WARN] scenario identity mismatch rows={total}")
        return 1 if a.fail_on_mismatch else 0
    print("[OK] scenario identity audit passed")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
