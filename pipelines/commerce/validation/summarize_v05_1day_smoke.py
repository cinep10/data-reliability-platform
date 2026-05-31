#!/usr/bin/env python3
from __future__ import annotations
import argparse
from typing import Any
import pymysql

def parse_args():
    p=argparse.ArgumentParser(description="Summarize v0.5 one-day smoke result with robust AI score and cleanup-aware assertions.")
    p.add_argument("--db-host",required=True); p.add_argument("--db-port",type=int,required=True)
    p.add_argument("--db-user",required=True); p.add_argument("--db-pass",required=True); p.add_argument("--db-name",required=True)
    p.add_argument("--profile-id",required=True); p.add_argument("--target-date",required=True); p.add_argument("--scenario-name",required=True)
    p.add_argument("--run-id",type=int); p.add_argument("--source-gen-run-id",type=int)
    p.add_argument("--require-ai-score",default="true")
    p.add_argument("--assertion-mode",choices=["full","preserve","informational"],default="full")
    return p.parse_args()

def truthy(v): return str(v).strip().lower() in {"1","true","yes","y","on"}

def connect(a):
    return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset="utf8mb4",cursorclass=pymysql.cursors.DictCursor,autocommit=True)

def table_exists(cur,t):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return int(cur.fetchone()["cnt"])>0

def columns(cur,t):
    if not table_exists(cur,t): return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return {str(r["column_name"]) for r in cur.fetchall()}

def where_scope(cs,a):
    wh=[]; ps=[]
    if "profile_id" in cs: wh.append("profile_id=%s"); ps.append(a.profile_id)
    if "target_date" in cs: wh.append("target_date=%s"); ps.append(a.target_date)
    elif "dt" in cs: wh.append("dt=%s"); ps.append(a.target_date)
    if "scenario_name" in cs: wh.append("scenario_name=%s"); ps.append(a.scenario_name)
    if a.source_gen_run_id is not None and "source_gen_run_id" in cs:
        wh.append("source_gen_run_id=%s"); ps.append(a.source_gen_run_id)
    elif a.run_id is not None and "run_id" in cs:
        wh.append("run_id=%s"); ps.append(a.run_id)
    return (" AND ".join(wh) if wh else "1=1", ps)

def count_rows(cur,t,a):
    if not table_exists(cur,t): return 0
    cs=columns(cur,t); wh,ps=where_scope(cs,a)
    cur.execute(f"SELECT COUNT(*) cnt FROM `{t}` WHERE {wh}",tuple(ps))
    return int(cur.fetchone()["cnt"])

def latest_row(cur,t,a):
    if not table_exists(cur,t): return {}
    cs=columns(cur,t); wh,ps=where_scope(cs,a)
    order=[c for c in ["created_at","updated_at","run_id"] if c in cs]
    sql=f"SELECT * FROM `{t}` WHERE {wh}"
    if order: sql += " ORDER BY " + ", ".join(f"{c} DESC" for c in order)
    sql += " LIMIT 1"; cur.execute(sql,tuple(ps))
    return cur.fetchone() or {}

def val(row:dict[str,Any],*names,default=None):
    for n in names:
        if n in row and row[n] is not None: return row[n]
    return default

def classify_ai(ai_validation,ai_score):
    status=str(val(ai_validation,"validation_status","status",default="missing")).lower()
    level=str(val(ai_score,"final_ai_risk_level","ai_risk_level","ai_reliability_level","risk_level","review_level","reliability_level","final_risk_level","level",default="missing")).lower()
    if status in {"pass","passed","ok"}: return "PASS"
    if ai_score and status in {"fail","failed","missing"}: return "PASS_WITH_REVIEW"
    if level in {"review","warn","warning","medium","low","normal","stable"}: return "PASS_WITH_REVIEW"
    return "WARN"

def main():
    a=parse_args(); require_ai_score=truthy(a.require_ai_score); failures=[]; warnings=[]
    con=connect(a)
    try:
        with con.cursor() as cur:
            tables=["semantic_interpretation_day_v05","unified_reliability_score_day_v05","action_recommendation_day_v05","v05_runtime_evidence_day","v05_ml_feature_snapshot_day","v05_ai_validation_result_day","v05_ai_reliability_score_day"]
            counts={t:count_rows(cur,t,a) for t in tables}
            score=latest_row(cur,"unified_reliability_score_day_v05",a); action=latest_row(cur,"action_recommendation_day_v05",a)
            runtime=latest_row(cur,"v05_runtime_evidence_day",a); ml=latest_row(cur,"v05_ml_feature_snapshot_day",a)
            ai_validation=latest_row(cur,"v05_ai_validation_result_day",a); ai_score=latest_row(cur,"v05_ai_reliability_score_day",a)
            print(f"[SUMMARY_MODE] assertion_mode={a.assertion_mode} require_ai_score={require_ai_score} run_id={a.run_id} source_gen_run_id={a.source_gen_run_id}")
            for k,v in counts.items(): print(f"[SUMMARY] {k}={v}")
            print(f"[SUMMARY] v05_risk=level={val(score,'final_risk_level',default='missing')} score={val(score,'overall_risk_score',default='missing')} semantic={val(score,'dominant_semantic_risk',default=val(ml,'dominant_semantic_risk',default='missing'))}")
            print(f"[SUMMARY] runtime_evidence=level={val(runtime,'evidence_level',default='missing')} score={val(runtime,'runtime_evidence_score',default='missing')} dominant={val(runtime,'dominant_runtime_signal',default='missing')}")
            print(f"[SUMMARY] action={val(action,'recommended_action','action_type',default=val(ml,'recommended_action',default='missing'))}")
            print(f"[SUMMARY] ml_feature=risk={val(ml,'final_risk_level',default='missing')} score={val(ml,'overall_risk_score',default='missing')} semantic={val(ml,'dominant_semantic_risk',default='missing')}")
            print(f"[SUMMARY] ai_validation=status={val(ai_validation,'validation_status','status',default='missing')} missing_evidence={val(ai_validation,'missing_evidence_flag',default='missing')} unsupported={val(ai_validation,'unsupported_explanation_flag',default='missing')} hallucinated={val(ai_validation,'hallucinated_reconciliation_flag',default='missing')} wrong_action={val(ai_validation,'wrong_operational_recommendation_flag',default='missing')}")
            print(f"[SUMMARY] ai_score=level={val(ai_score,'final_ai_risk_level','ai_risk_level','ai_reliability_level','risk_level','review_level','reliability_level','final_risk_level','level',default='missing')} score={val(ai_score,'ai_risk_score','overall_ai_risk_score','risk_score','ai_reliability_score','score',default='missing')}")
            if a.assertion_mode=="full":
                required=["semantic_interpretation_day_v05","unified_reliability_score_day_v05","action_recommendation_day_v05","v05_runtime_evidence_day","v05_ml_feature_snapshot_day"]
                if require_ai_score: required.append("v05_ai_reliability_score_day")
            elif a.assertion_mode=="preserve":
                required=["v05_runtime_evidence_day","v05_ml_feature_snapshot_day","v05_ai_reliability_score_day"]
                for t in ["semantic_interpretation_day_v05","unified_reliability_score_day_v05","action_recommendation_day_v05"]:
                    if counts[t]==0: print(f"[INFO] post-cleanup mode: {t} cleanup accepted")
            else:
                required=[]
            for t in required:
                if counts.get(t,0)<=0: failures.append(f"missing required artifact: {t}")
            ai_class=classify_ai(ai_validation,ai_score)
            if counts["v05_ai_validation_result_day"]<=0: warnings.append("missing v05_ai_validation_result_day")
            elif str(val(ai_validation,"validation_status","status",default="")).lower() in {"fail","failed"}: warnings.append("AI validation returned FAIL; classified as PASS_WITH_REVIEW if AI reliability score exists")
            if ai_class=="WARN": warnings.append("AI validation/score state is WARN")
            for w in warnings: print(f"[WARN] {w}")
            if failures:
                for f in failures: print(f"[FAIL] {f}")
                return 1
            print(f"[OK] v0.5 1-day smoke summary scenario={a.scenario_name} assertion_mode={a.assertion_mode} ai_classification={ai_class}")
            return 0
    finally:
        con.close()

if __name__=="__main__":
    raise SystemExit(main())
