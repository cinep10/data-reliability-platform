from __future__ import annotations
import argparse, json, pymysql

def parse_args():
    p=argparse.ArgumentParser(description='Validate v0.5 AI explanation/action against evidence. Validation watches AI, not the other way around.')
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
      def one(t): cur.execute('SELECT * FROM '+t+' WHERE '+where,params); return cur.fetchone()
      ctx=one('v05_ai_incident_context_day'); summ=one('v05_ai_incident_summary_day'); u=one('unified_reliability_score_day_v05')
      cur.execute('SELECT * FROM action_recommendation_day_v05 WHERE '+where+' ORDER BY action_rank',params); acts=cur.fetchall()
      missing_evidence=0 if ctx and int(ctx.get('evidence_count') or 0)>0 and int(ctx.get('evidence_missing_flag') or 0)==0 else 1
      text=' '.join([(summ or {}).get('incident_explanation') or '',(summ or {}).get('root_cause_summary') or '',(summ or {}).get('recommended_action_summary') or '']).lower()
      unsupported=1 if summ and ('guaranteed' in text or 'certainly caused' in text) else 0
      hallucinated=0
      for term in ['reconciliation','match_rate','transaction','state','behavior']:
        if term in text and not ctx: hallucinated=1
      level=((u or {}).get('final_risk_level') or '').lower(); score=float((u or {}).get('overall_risk_score') or 0)
      action_text=' '.join([x.get('recommended_action') or '' for x in acts]).lower()
      wrong_action=1 if level in ('stable','normal','low') and score < 0.20 and action_text not in ('','no action') and 'no action' not in action_text else 0
      status='PASS' if not any([missing_evidence,unsupported,hallucinated,wrong_action]) else 'FAIL'
      payload={'validation_role':'AI guardrail','checks':{'missing_evidence':missing_evidence,'unsupported_explanation':unsupported,'hallucinated_reconciliation':hallucinated,'wrong_operational_recommendation':wrong_action},'rule_semantic_source_of_truth':True,'ai_final_judgement':False}
      if a.truncate_target: cur.execute('DELETE FROM v05_ai_validation_result_day WHERE '+where,params)
      cur.execute('INSERT INTO v05_ai_validation_result_day(run_id,profile_id,source_gen_run_id,target_date,scenario_name,missing_evidence_flag,unsupported_explanation_flag,hallucinated_reconciliation_flag,wrong_operational_recommendation_flag,validation_status,validation_payload_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(a.run_id,a.profile_id,a.source_gen_run_id,a.target_date,a.scenario_name,missing_evidence,unsupported,hallucinated,wrong_action,status,json.dumps(payload,ensure_ascii=False)))
    c.commit(); print('[validate_v05_ai_outputs] '+status)
  except Exception:
    c.rollback(); raise
  finally: c.close()
if __name__=='__main__': main()
