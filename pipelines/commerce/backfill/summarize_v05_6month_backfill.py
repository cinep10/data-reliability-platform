#!/usr/bin/env python3
from __future__ import annotations

import argparse, csv
from pathlib import Path
import pymysql

def parse_args():
    p=argparse.ArgumentParser(description="Cleanup-aware v0.5 6-month backfill summary.")
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--calendar-file", required=True)
    p.add_argument("--expected-file", required=True)
    p.add_argument("--out-file", required=True)
    p.add_argument("--assertion-mode", choices=["preserve","full","informational"], default="preserve")
    return p.parse_args()

def connect(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=True)

def table_exists(cur,t):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return int(cur.fetchone()["cnt"])>0

def cols(cur,t):
    if not table_exists(cur,t): return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return {r["column_name"] for r in cur.fetchall()}

def count_rows(cur,t,profile,dt,sc):
    if not table_exists(cur,t): return 0
    cs=cols(cur,t); wh=[]; ps=[]
    if "profile_id" in cs: wh.append("profile_id=%s"); ps.append(profile)
    if "target_date" in cs: wh.append("target_date=%s"); ps.append(dt)
    elif "dt" in cs: wh.append("dt=%s"); ps.append(dt)
    if "scenario_name" in cs: wh.append("scenario_name=%s"); ps.append(sc)
    sql=f"SELECT COUNT(*) cnt FROM `{t}`"
    if wh: sql += " WHERE " + " AND ".join(wh)
    cur.execute(sql, tuple(ps))
    return int(cur.fetchone()["cnt"])

def latest(cur,t,profile,dt,sc):
    if not table_exists(cur,t): return {}
    cs=cols(cur,t); wh=[]; ps=[]
    if "profile_id" in cs: wh.append("profile_id=%s"); ps.append(profile)
    if "target_date" in cs: wh.append("target_date=%s"); ps.append(dt)
    elif "dt" in cs: wh.append("dt=%s"); ps.append(dt)
    if "scenario_name" in cs: wh.append("scenario_name=%s"); ps.append(sc)
    sql=f"SELECT * FROM `{t}`"
    if wh: sql += " WHERE " + " AND ".join(wh)
    order=[c for c in ["created_at","updated_at","run_id","source_gen_run_id"] if c in cs]
    if order: sql += " ORDER BY " + ",".join(f"{c} DESC" for c in order)
    sql += " LIMIT 1"
    cur.execute(sql, tuple(ps))
    return cur.fetchone() or {}

def val(row,*names,default=""):
    for n in names:
        if n in row and row[n] is not None: return row[n]
    return default

def main():
    a=parse_args()
    calendar=list(csv.DictReader(open(a.calendar_file, newline='', encoding='utf-8')))
    expected={r["scenario_name"]:r for r in csv.DictReader(open(a.expected_file, newline='', encoding='utf-8'))}
    out=[]
    con=connect(a)
    try:
        with con.cursor() as cur:
            for c in calendar:
                dt=c["target_date"]; sc=c["scenario_name"]; exp=expected.get(sc,{})
                counts={
                    "semantic": count_rows(cur,"semantic_interpretation_day_v05",a.profile_id,dt,sc),
                    "risk": count_rows(cur,"unified_reliability_score_day_v05",a.profile_id,dt,sc),
                    "action": count_rows(cur,"action_recommendation_day_v05",a.profile_id,dt,sc),
                    "ml": count_rows(cur,"v05_ml_feature_snapshot_day",a.profile_id,dt,sc),
                    "ai_score": count_rows(cur,"v05_ai_reliability_score_day",a.profile_id,dt,sc),
                    "ai_validation": count_rows(cur,"v05_ai_validation_result_day",a.profile_id,dt,sc),
                }
                ml=latest(cur,"v05_ml_feature_snapshot_day",a.profile_id,dt,sc)
                ai=latest(cur,"v05_ai_reliability_score_day",a.profile_id,dt,sc)
                score=latest(cur,"unified_reliability_score_day_v05",a.profile_id,dt,sc)
                action=latest(cur,"action_recommendation_day_v05",a.profile_id,dt,sc)
                if a.assertion_mode=="preserve":
                    artifact_ok = counts["ml"]>0 and counts["ai_score"]>0
                    artifact_policy = "preserve_requires_ml_ai_only"
                elif a.assertion_mode=="full":
                    artifact_ok = counts["semantic"]>0 and counts["risk"]>0 and counts["action"]>0 and counts["ml"]>0 and counts["ai_score"]>0
                    artifact_policy = "full_requires_phase4_and_phase5"
                else:
                    artifact_ok = True
                    artifact_policy = "informational"
                semantic=val(score,"dominant_semantic_risk",default=val(ml,"dominant_semantic_risk",default=""))
                risk_level=val(score,"final_risk_level",default=val(ml,"final_risk_level",default=""))
                risk_score=val(score,"overall_risk_score",default=val(ml,"overall_risk_score",default=""))
                action_text=val(action,"recommended_action","action_type",default=val(ml,"recommended_action",default=""))
                ai_level=val(ai,"final_ai_risk_level","ai_risk_level","ai_reliability_level","risk_level","level",default="")
                cal="review"
                if sc=="baseline" and str(risk_level).lower()=="low": cal="pass"
                elif semantic and exp.get("expected_semantic_hint") and str(semantic).lower()==exp["expected_semantic_hint"].lower(): cal="pass"
                out.append({
                    "backfill_day": c.get("backfill_day") or c.get("pilot_day") or "",
                    "target_date": dt, "scenario_name": sc,
                    "artifact_ok": "PASS" if artifact_ok else "FAIL",
                    "artifact_policy": artifact_policy,
                    **{f"{k}_rows":v for k,v in counts.items()},
                    "final_risk_level": risk_level,
                    "overall_risk_score": risk_score,
                    "dominant_semantic_risk": semantic,
                    "recommended_action": action_text,
                    "ai_reliability_level": ai_level,
                    "expected_risk_family": exp.get("expected_risk_family",""),
                    "expected_semantic_hint": exp.get("expected_semantic_hint",""),
                    "expected_action_hint": exp.get("expected_action_hint",""),
                    "calibration_review": cal,
                })
    finally:
        con.close()
    Path(a.out_file).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out_file,"w",newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=list(out[0].keys()), delimiter="\t")
        w.writeheader(); w.writerows(out)
    print("[REPORT] "+a.out_file)
    print("[REPORT_SUMMARY] rows=%d artifact_fail=%d calibration_pass=%d calibration_review=%d assertion_mode=%s" % (
        len(out), sum(1 for r in out if r["artifact_ok"]!="PASS"), sum(1 for r in out if r["calibration_review"]=="pass"), sum(1 for r in out if r["calibration_review"]!="pass"), a.assertion_mode
    ))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
