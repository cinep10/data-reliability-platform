#!/usr/bin/env python3
from __future__ import annotations
import argparse, pickle
from pathlib import Path
from pipelines.commerce.ml.predict._v05_common import *

NUM_FEATURES=["reconciliation_gap","orphan_ratio","duplicate_ratio","delivery_delay_ms","payment_state_gap","conversion_distortion","transaction_without_state_ratio","behavior_only_ratio","transaction_only_ratio","coupon_reconciliation_gap","semantic_base_score","overall_risk_score","runtime_evidence_score","batch_evidence_score","stream_evidence_score","operational_evidence_score"]
LEVEL_SCORE={"stable":0.02,"normal":0.02,"low":0.15,"warning":0.45,"high":0.72,"critical":0.92}

def parse_args():
    p=argparse.ArgumentParser(description="Predict v0.5 reconciliation risk to DB. ML is supplemental.")
    for k in ["db-host","db-user","db-pass","db-name","profile-id","target-date"]: p.add_argument("--"+k, required=True)
    p.add_argument("--db-port", type=int, required=True); p.add_argument("--run-id", type=int, required=True); p.add_argument("--source-gen-run-id", type=int); p.add_argument("--scenario-name", default="baseline"); p.add_argument("--model-dir", default="artifacts/ml_v05"); p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def derived(feat,k):
    if k in feat and feat.get(k) is not None: return f(feat,k)
    btm=f(feat,"behavior_transaction_match_rate"); tsm=f(feat,"transaction_state_match_rate")
    bc=max(1.0,f(feat,"canonical_behavior_count")); tc=max(1.0,f(feat,"canonical_transaction_count")); sc=max(1.0,f(feat,"canonical_state_count"))
    return {
      "reconciliation_gap":clamp01((1-btm)*0.5+(1-tsm)*0.5),
      "orphan_ratio":clamp01(f(feat,"orphan_state_count")/sc),
      "duplicate_ratio":clamp01(f(feat,"duplicate_order_count")/tc),
      "delivery_delay_ms":f(feat,"p95_transaction_state_gap_ms"),
      "payment_state_gap":clamp01(1-tsm),
      "conversion_distortion":f(feat,"conversion_distortion_score", f(feat,"distortion_score")),
      "transaction_without_state_ratio":clamp01(f(feat,"transaction_without_state_count")/tc),
      "behavior_only_ratio":clamp01(f(feat,"behavior_only_count")/bc),
      "transaction_only_ratio":clamp01(f(feat,"transaction_only_count")/tc),
      "coupon_reconciliation_gap":f(feat,"coupon_reconciliation_gap"),
      "semantic_base_score":f(feat,"semantic_base_score", f(feat,"overall_risk_score"))
    }.get(k, f(feat,k))

def vector(feat): return {k:derived(feat,k) for k in NUM_FEATURES}
def cls(score): return "critical_reconciliation_failure" if score>=0.75 else "high_reconciliation_risk" if score>=0.55 else "warning_reconciliation_risk" if score>=0.30 else "low_reconciliation_residual" if score>=0.08 else "normal_reconciliation_variation"

def det(feat):
    v=vector(feat); raw=1.2*v["reconciliation_gap"]+1.2*v["payment_state_gap"]+0.9*v["orphan_ratio"]+1.6*v["duplicate_ratio"]+0.8*v["conversion_distortion"]+0.8*v["transaction_without_state_ratio"]+0.25*v["runtime_evidence_score"]
    prob=clamp01(sigmoid(raw-1.6)); score=clamp01(0.65*f(feat,"overall_risk_score")+0.35*prob)
    level="critical" if score>=0.75 else "high" if score>=0.55 else "warning" if score>=0.30 else "low" if score>=0.08 else "stable"
    return cls(score),score,prob,level,{"feature_vector":v,"raw_logit":raw,"model_mode":"deterministic_fallback"}

def main():
    a=parse_args(); con=connect(a)
    try:
      with con.cursor() as cur:
        feat=fetch_one(cur,"v05_ml_feature_snapshot_day",a)
        if not feat: raise RuntimeError("missing v05_ml_feature_snapshot_day")
        pc,ps,prob,pl,payload=det(feat)
        expected=LEVEL_SCORE.get(s(feat,"final_risk_level").lower(), f(feat,"overall_risk_score")); gap=abs(ps-expected); status="PASS" if gap<=0.35 else "REVIEW"
        if a.truncate_target: delete_scoped(cur,"v05_ml_prediction_day",a)
        insert_dict(cur,"v05_ml_prediction_day",{"run_id":a.run_id,"profile_id":a.profile_id,"source_gen_run_id":a.source_gen_run_id,"target_date":a.target_date,"scenario_name":a.scenario_name,"model_source":payload["model_mode"],"model_version":"v05_deterministic_or_trained","predicted_risk_class":pc,"predicted_risk_score":ps,"predicted_risk_level":pl,"reconciliation_failure_probability":prob,"score_gap":gap,"prediction_status":status,"feature_vector_json":json_dumps(payload["feature_vector"]),"prediction_payload_json":json_dumps(payload)})
      con.commit(); print(f"[predict_v05_reconciliation_ml_to_db] OK class={pc} score={ps:.6f} status={status}")
    except Exception:
      con.rollback(); raise
    finally: con.close()
if __name__=="__main__": main()
