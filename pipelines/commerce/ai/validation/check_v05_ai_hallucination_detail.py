#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pipelines.commerce.ai.validation._v05_common import *
VALIDATION_TYPE="hallucination"

def parse_args():
    p=argparse.ArgumentParser(description="v0.5 AI detail validation")
    for k in ["db-host","db-user","db-pass","db-name","profile-id","target-date"]: p.add_argument("--"+k, required=True)
    p.add_argument("--db-port", type=int, required=True); p.add_argument("--run-id", type=int, required=True); p.add_argument("--source-gen-run-id", type=int); p.add_argument("--scenario-name", default="baseline"); p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def main():
    a=parse_args(); con=connect(a)
    try:
      with con.cursor() as cur:
        ctx=fetch_one(cur,"v05_ai_incident_context_day",a); summ=fetch_one(cur,"v05_ai_incident_summary_day",a); risk=fetch_one(cur,"unified_reliability_score_day_v05",a); sem=fetch_one(cur,"semantic_interpretation_day_v05",a); action=fetch_one(cur,"action_recommendation_day_v05",a)
        text=" ".join([s(summ,"incident_explanation"),s(summ,"root_cause_summary"),s(summ,"recommended_action_summary")]).lower()
        evidence=int(f(ctx,"evidence_count",0)); dominant=s(sem,"dominant_semantic_risk","None"); level=s(risk,"final_risk_level","unknown").lower(); recommended=s(action,"recommended_action","").lower()
        missing=unsupported=hallucination=wrong=0; reasons=[]
        if VALIDATION_TYPE=="interpretation":
          missing=1 if not ctx or evidence<=0 else 0; unsupported=1 if any(x in text for x in ["guaranteed","certainly caused","definitely caused"]) else 0
          if missing: reasons.append("missing AI context evidence")
          if unsupported: reasons.append("overconfident unsupported wording")
        elif VALIDATION_TYPE=="action_alignment":
          baseline=a.scenario_name.lower() in {"baseline","normal","stable"}; wrong=1 if baseline and dominant in {"None","none","","NULL"} and level in {"stable","normal","low"} and "no action" not in recommended else 0
          if wrong: reasons.append("baseline no-dominant low risk generated non-no-action")
        elif VALIDATION_TYPE=="hallucination":
          hallucination=1 if ("outage" in text and "runtime" not in text and "availability" not in text) else 0
          if hallucination: reasons.append("unsupported outage/root-cause wording")
        issues=missing+unsupported+hallucination+wrong; status="PASS" if issues==0 else "REVIEW"
        if a.truncate_target and table_exists(cur,"v05_ai_validation_detail_day"):
          cur.execute("DELETE FROM v05_ai_validation_detail_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND validation_type=%s",(a.profile_id,a.target_date,a.scenario_name,a.run_id,VALIDATION_TYPE))
        insert_dict(cur,"v05_ai_validation_detail_day",{"run_id":a.run_id,"profile_id":a.profile_id,"source_gen_run_id":a.source_gen_run_id,"target_date":a.target_date,"scenario_name":a.scenario_name,"validation_type":VALIDATION_TYPE,"validation_status":status,"evidence_count":evidence,"issue_count":issues,"missing_evidence_flag":missing,"unsupported_explanation_flag":unsupported,"hallucination_flag":hallucination,"wrong_action_flag":wrong,"validation_reason":"; ".join(reasons) if reasons else "detail validation passed","validation_payload_json":json_dumps({"dominant_semantic_risk":dominant,"final_risk_level":level,"recommended_action":recommended})})
      con.commit(); print(f"[validate_v05_ai_{VALIDATION_TYPE}] {status}")
    except Exception:
      con.rollback(); raise
    finally: con.close()
if __name__=="__main__": main()
