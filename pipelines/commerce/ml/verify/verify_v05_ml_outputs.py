#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pipelines.commerce.ml.verify._v05_common import *

def parse_args():
    p=argparse.ArgumentParser(description="Verify v0.5 ML outputs.")
    for k in ["db-host","db-user","db-pass","db-name","profile-id","target-date"]: p.add_argument("--"+k, required=True)
    p.add_argument("--db-port", type=int, required=True); p.add_argument("--run-id", type=int, required=True); p.add_argument("--source-gen-run-id", type=int); p.add_argument("--scenario-name", default="baseline"); p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def main():
    a=parse_args(); con=connect(a)
    try:
      with con.cursor() as cur:
        feat=fetch_one(cur,"v05_ml_feature_snapshot_day",a); cal=fetch_one(cur,"v05_ml_calibration_result_day",a); pred=fetch_one(cur,"v05_ml_prediction_day",a); sem=fetch_one(cur,"semantic_interpretation_day_v05",a); risk=fetch_one(cur,"unified_reliability_score_day_v05",a); act=fetch_one(cur,"action_recommendation_day_v05",a)
        ff=1 if feat else 0; cf=1 if cal else 0; pf=1 if pred else 0
        baseline=a.scenario_name.lower() in {"baseline","normal","stable"}; dom=s(sem,"dominant_semantic_risk",s(feat,"dominant_semantic_risk","None")); level=s(risk,"final_risk_level",s(feat,"final_risk_level","unknown")).lower(); action=s(act,"recommended_action",s(feat,"recommended_action",""))
        baseline_ok=1 if (not baseline or (dom in {"","None","none","NULL"} and level in {"stable","normal","low"} and ("no action" in action.lower() or action==""))) else 0
        gap=f(pred,"score_gap",f(cal,"score_gap",0)); gap_flag=1 if gap>0.35 else 0
        issues=[]
        if not ff: issues.append("missing feature snapshot")
        if not cf: issues.append("missing ML calibration")
        if not pf: issues.append("missing ML prediction")
        if not baseline_ok: issues.append("baseline false escalation")
        if gap_flag: issues.append(f"score gap review={gap:.6f}")
        status="FAIL" if not ff else ("REVIEW" if issues else "PASS")
        if a.truncate_target: delete_scoped(cur,"v05_ml_output_verification_day",a)
        insert_dict(cur,"v05_ml_output_verification_day",{"run_id":a.run_id,"profile_id":a.profile_id,"source_gen_run_id":a.source_gen_run_id,"target_date":a.target_date,"scenario_name":a.scenario_name,"feature_snapshot_flag":ff,"calibration_flag":cf,"prediction_flag":pf,"baseline_no_false_escalation_flag":baseline_ok,"score_gap_review_flag":gap_flag,"label_concentration_review_flag":0,"verification_status":status,"verification_reason":"; ".join(issues) if issues else "all ML governance artifacts valid","verification_payload_json":json_dumps({"score_gap":gap})})
      con.commit(); print(f"[verify_v05_ml_outputs] {status}")
    except Exception:
      con.rollback(); raise
    finally: con.close()
if __name__=="__main__": main()
