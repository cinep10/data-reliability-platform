from __future__ import annotations
import argparse, json, pymysql

def parse_args():
    p=argparse.ArgumentParser(description='Build v0.5 AI reliability score from AI validation flags.')
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
      cur.execute('SELECT * FROM v05_ai_validation_result_day WHERE '+where,params); v=cur.fetchone()
      if not v: raise RuntimeError('missing v05_ai_validation_result_day')
      miss=float(v.get('missing_evidence_flag') or 0); unsup=float(v.get('unsupported_explanation_flag') or 0); hall=float(v.get('hallucinated_reconciliation_flag') or 0); wrong=float(v.get('wrong_operational_recommendation_flag') or 0)
      overall=min(1.0, miss*0.30 + unsup*0.25 + hall*0.30 + wrong*0.15)
      level='trusted' if overall==0 else ('review' if overall < 0.5 else 'blocked')
      payload={'ai_guardrail':'validation_to_score','validation_status':v.get('validation_status'),'ai_reliability_interpretation':'AI output is acceptable only if it is evidence-backed and does not override rule/semantic/action gates.'}
      if a.truncate_target: cur.execute('DELETE FROM v05_ai_reliability_score_day WHERE '+where,params)
      cur.execute('INSERT INTO v05_ai_reliability_score_day(run_id,profile_id,source_gen_run_id,target_date,scenario_name,missing_evidence_risk,unsupported_explanation_risk,hallucination_risk,wrong_action_risk,overall_ai_risk_score,ai_reliability_level,ai_score_payload_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(a.run_id,a.profile_id,a.source_gen_run_id,a.target_date,a.scenario_name,miss,unsup,hall,wrong,overall,level,json.dumps(payload,ensure_ascii=False)))
    c.commit(); print('[build_v05_ai_reliability_score] OK level='+level)
  except Exception:
    c.rollback(); raise
  finally: c.close()
if __name__=='__main__': main()
