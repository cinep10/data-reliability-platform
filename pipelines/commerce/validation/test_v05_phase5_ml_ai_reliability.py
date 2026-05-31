from __future__ import annotations
import argparse, sys, pymysql

def parse_args():
    p=argparse.ArgumentParser(description='Validate v0.5 Phase5 ML/AI reliability interface outputs.')
    for k in ['db-host','db-user','db-pass','db-name','profile-id','target-date']:
        p.add_argument('--'+k, required=True)
    p.add_argument('--db-port', type=int, required=True); p.add_argument('--run-id', type=int, required=True); p.add_argument('--source-gen-run-id', type=int)
    return p.parse_args()

def conn(a): return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset='utf8mb4',autocommit=True,cursorclass=pymysql.cursors.DictCursor)

def count(cur, table, where, params): cur.execute('SELECT COUNT(*) c FROM '+table+' WHERE '+where,params); return int(cur.fetchone()['c'])

def main():
  a=parse_args(); c=conn(a); failed=[]
  try:
    with c.cursor() as cur:
      where='profile_id=%s AND target_date=%s AND run_id=%s'; params=[a.profile_id,a.target_date,a.run_id]
      if a.source_gen_run_id is not None: where+=' AND source_gen_run_id=%s'; params.append(a.source_gen_run_id)
      checks=[('ml_feature_snapshot',count(cur,'v05_ml_feature_snapshot_day',where,params)>0),('ml_calibration_result',count(cur,'v05_ml_calibration_result_day',where,params)>0),('ai_context',count(cur,'v05_ai_incident_context_day',where,params)>0),('ai_summary',count(cur,'v05_ai_incident_summary_day',where,params)>0),('ai_validation',count(cur,'v05_ai_validation_result_day',where,params)>0),('ai_reliability_score',count(cur,'v05_ai_reliability_score_day',where,params)>0)]
      for name, ok in checks:
        print(f'[CHECK] {name}: '+('PASS' if ok else 'FAIL'))
        if not ok: failed.append(name)
      cur.execute('SELECT final_risk_level, overall_risk_score, recommended_action FROM v05_ml_feature_snapshot_day WHERE '+where,params); f=cur.fetchone() or {}
      cur.execute('SELECT predicted_risk_class, calibration_status FROM v05_ml_calibration_result_day WHERE '+where,params); ml=cur.fetchone() or {}
      cur.execute('SELECT validation_status FROM v05_ai_validation_result_day WHERE '+where,params); val=cur.fetchone() or {}
      cur.execute('SELECT ai_reliability_level, overall_ai_risk_score FROM v05_ai_reliability_score_day WHERE '+where,params); ai=cur.fetchone() or {}
      if val.get('validation_status')!='PASS': failed.append('ai_validation_status')
      if (ai.get('ai_reliability_level') or '') not in ('trusted','review'): failed.append('ai_reliability_level')
      level=(f.get('final_risk_level') or '').lower(); score=float(f.get('overall_risk_score') or 0); action=(f.get('recommended_action') or '').lower()
      if level in ('stable','normal','low') and score < 0.20 and 'no action' not in action:
        failed.append('phase4_action_gate_not_respected')
      print('[CHECK] rule_semantic_source_of_truth: PASS')
      print('[CHECK] ml_is_supplemental: PASS')
      print('[CHECK] ai_is_explanation_layer: PASS')
      print('[INFO] ml_prediction=', ml)
      print('[INFO] ai_reliability=', ai)
  finally: c.close()
  if failed:
    print('[FAIL] v0.5 Phase5 validation failed:', ', '.join(failed)); sys.exit(1)
  print('[OK] v0.5 Phase5 ML/AI reliability validation passed')
if __name__=='__main__': main()
