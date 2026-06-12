from __future__ import annotations
import argparse, json, pymysql

def parse_args():
    p=argparse.ArgumentParser(description='Build deterministic v0.5 AI incident summary. No LLM judgement; summary cites evidence.')
    for k in ['db-host','db-user','db-pass','db-name','profile-id','target-date']:
        p.add_argument('--'+k, required=True)
    p.add_argument('--db-port', type=int, required=True); p.add_argument('--run-id', type=int, required=True); p.add_argument('--source-gen-run-id', type=int); p.add_argument('--scenario-name', default='baseline'); p.add_argument('--truncate-target', action='store_true')
    return p.parse_args()

def conn(a): return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset='utf8mb4',autocommit=False,cursorclass=pymysql.cursors.DictCursor)

def main():
  a=parse_args(); c=conn(a)
  try:
    with c.cursor() as cur:
      where='profile_id=%s AND target_date=%s AND run_id=%s'; params=[a.profile_id,a.target_date,a.run_id]
      if a.source_gen_run_id is not None: where+=' AND source_gen_run_id=%s'; params.append(a.source_gen_run_id)
      cur.execute('SELECT * FROM v05_ai_incident_context_day WHERE '+where,params); ctx=cur.fetchone()
      if not ctx: raise RuntimeError('missing v05_ai_incident_context_day')
      p=json.loads(ctx.get('context_payload_json') or '{}')
      m=p.get('measurement') or {}; u=p.get('unified_score') or {}; sem=p.get('semantic') or {}; ml=p.get('ml_calibration') or {}; actions=p.get('actions') or []
      level=(u.get('final_risk_level') or 'unknown'); score=float(u.get('overall_risk_score') or 0); dom=sem.get('dominant_semantic_risk') or 'None'
      explanation=(f"For {a.profile_id} {a.target_date} scenario={a.scenario_name}, v0.5 reconciliation evidence shows behavior_transaction_match_rate={m.get('behavior_transaction_match_rate')} and transaction_state_match_rate={m.get('transaction_state_match_rate')}. The rule/semantic layer produced final_risk_level={level}, overall_risk_score={score:.6f}, dominant_semantic_risk={dom}.")
      root=("Baseline residual mismatch is treated as non-promoted evidence when semantic/action gates suppress it." if dom in ('None',None,'') else f"Primary evidence is {dom}, supported by reconciliation and semantic tables.")
      action=(actions[0].get('recommended_action') if actions else 'no action')
      action_summary=f"Recommended action from governed action layer: {action}. ML prediction is supplemental: {ml.get('predicted_risk_class','unknown')} / severity={ml.get('predicted_severity_score','unknown')} and must not override rule/semantic output."
      payload={'summary_source':'deterministic_fallback','evidence_tables_used':['v05_ai_incident_context_day','v05_reconciliation_measurement_day','semantic_interpretation_day_v05','unified_reliability_score_day_v05','action_recommendation_day_v05','v05_ml_calibration_result_day'],'no_unsupported_claims':True,'ai_is_explanation_layer':True}
      if a.truncate_target: cur.execute('DELETE FROM v05_ai_incident_summary_day WHERE '+where,params)
      cur.execute('INSERT INTO v05_ai_incident_summary_day(run_id,profile_id,source_gen_run_id,target_date,scenario_name,incident_explanation,root_cause_summary,recommended_action_summary,output_source,summary_payload_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(a.run_id,a.profile_id,a.source_gen_run_id,a.target_date,a.scenario_name,explanation,root,action_summary,'deterministic_fallback',json.dumps(payload,ensure_ascii=False)))
    c.commit(); print('[build_v05_ai_incident_summary] OK')
  except Exception:
    c.rollback(); raise
  finally: c.close()
if __name__=='__main__': main()
