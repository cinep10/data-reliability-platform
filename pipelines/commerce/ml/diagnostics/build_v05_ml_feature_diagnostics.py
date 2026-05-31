#!/usr/bin/env python3
from __future__ import annotations
import argparse, statistics
from pipelines.commerce.ml.diagnostics._v05_common import *

FEATURES=["behavior_transaction_match_rate","transaction_state_match_rate","behavior_only_count","transaction_only_count","transaction_without_state_count","orphan_state_count","overall_risk_score","runtime_evidence_score","batch_evidence_score","stream_evidence_score","operational_evidence_score","realism_evidence_score"]

def parse_args():
    p=argparse.ArgumentParser(description="Build v0.5 ML feature diagnostics.")
    for k in ["db-host","db-user","db-pass","db-name","profile-id","target-date"]: p.add_argument("--"+k, required=True)
    p.add_argument("--db-port", type=int, required=True); p.add_argument("--run-id", type=int, required=True); p.add_argument("--source-gen-run-id", type=int); p.add_argument("--scenario-name", default="baseline"); p.add_argument("--baseline-days", type=int, default=30); p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def main():
    a=parse_args(); con=connect(a)
    try:
      with con.cursor() as cur:
        feat=fetch_one(cur,"v05_ml_feature_snapshot_day",a)
        if not feat: raise RuntimeError("missing v05_ml_feature_snapshot_day")
        if a.truncate_target: delete_scoped(cur,"v05_ml_feature_diagnostics_day",a)
        hist={k:[] for k in FEATURES}
        if table_exists(cur,"v05_ml_feature_snapshot_day"):
          cur.execute("SELECT * FROM v05_ml_feature_snapshot_day WHERE profile_id=%s AND target_date < %s AND scenario_name='baseline' ORDER BY target_date DESC LIMIT %s",(a.profile_id,a.target_date,a.baseline_days))
          for row in cur.fetchall():
            for k in FEATURES: hist[k].append(f(row,k))
        for k in FEATURES:
          val=f(feat,k); h=hist[k]; mean=statistics.mean(h) if h else None; std=statistics.pstdev(h) if len(h)>=2 else None; z=(val-mean)/std if mean is not None and std not in (None,0) else None; drift=1 if z is not None and abs(z)>=3 else 0; imp=abs(z or 0)*0.1
          insert_dict(cur,"v05_ml_feature_diagnostics_day",{"run_id":a.run_id,"profile_id":a.profile_id,"source_gen_run_id":a.source_gen_run_id,"target_date":a.target_date,"scenario_name":a.scenario_name,"feature_name":k,"feature_value":val,"baseline_mean":mean,"baseline_std":std,"z_score":z,"drift_flag":drift,"importance_score":imp,"diagnostic_status":"REVIEW" if drift else "PASS","diagnostic_payload_json":json_dumps({"baseline_points":len(h)})})
      con.commit(); print("[build_v05_ml_feature_diagnostics] OK")
    except Exception:
      con.rollback(); raise
    finally: con.close()
if __name__=="__main__": main()
