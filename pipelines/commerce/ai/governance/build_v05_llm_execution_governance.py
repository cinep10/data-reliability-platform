#!/usr/bin/env python3
from __future__ import annotations
import argparse, os
from pipelines.commerce.ai.governance._v05_common import *

def parse_args():
    p=argparse.ArgumentParser(description="Record v0.5 LLM execution governance.")
    for k in ["db-host","db-user","db-pass","db-name","profile-id","target-date"]: p.add_argument("--"+k, required=True)
    p.add_argument("--db-port", type=int, required=True); p.add_argument("--run-id", type=int, required=True); p.add_argument("--source-gen-run-id", type=int); p.add_argument("--scenario-name", default="baseline"); p.add_argument("--llm-provider", default=os.getenv("V05_LLM_PROVIDER", os.getenv("LLM_PROVIDER","none"))); p.add_argument("--llm-model", default=os.getenv("V05_LLM_MODEL","none")); p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def main():
    a=parse_args(); con=connect(a)
    try:
      with con.cursor() as cur:
        summ=fetch_one(cur,"v05_ai_incident_summary_day",a); source=s(summ,"output_source","deterministic_fallback"); provider=a.llm_provider or "none"; fallback=1 if provider=="none" or "fallback" in source else 0; status="not_called" if provider=="none" else "completed_or_external"; gov="PASS" if fallback or summ else "REVIEW"
        if a.truncate_target: delete_scoped(cur,"v05_llm_execution_log_day",a)
        insert_dict(cur,"v05_llm_execution_log_day",{"run_id":a.run_id,"profile_id":a.profile_id,"source_gen_run_id":a.source_gen_run_id,"target_date":a.target_date,"scenario_name":a.scenario_name,"provider":provider,"model_name":a.llm_model,"prompt_tokens":0,"completion_tokens":0,"total_tokens":0,"latency_ms":0,"api_status":status,"api_error":None,"fallback_used":fallback,"llm_cost_usd":0.0,"governance_status":gov,"execution_payload_json":json_dumps({"policy":"LLM optional/advisory; deterministic evidence summary remains valid","summary_source":source})})
      con.commit(); print(f"[build_v05_llm_execution_governance] {gov} provider={provider} fallback={fallback}")
    except Exception:
      con.rollback(); raise
    finally: con.close()
if __name__=="__main__": main()
