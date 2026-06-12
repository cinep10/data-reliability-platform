from __future__ import annotations
import argparse, json, math, pymysql

LEVEL_MAP={'stable':0.02,'normal':0.02,'low':0.15,'warning':0.45,'high':0.72,'critical':0.92}

def parse_args():
    p=argparse.ArgumentParser(description='Build v0.5 ML calibration interface. ML is supplemental and does not overwrite semantic/rule outputs.')
    for k in ['db-host','db-user','db-pass','db-name','profile-id','target-date']:
        p.add_argument('--'+k, required=True)
    p.add_argument('--db-port', type=int, required=True)
    p.add_argument('--run-id', type=int, required=True)
    p.add_argument('--source-gen-run-id', type=int)
    p.add_argument('--scenario-name', default='baseline')
    p.add_argument('--truncate-target', action='store_true')
    p.add_argument('--model-path', default='')
    return p.parse_args()

def conn(a):
    return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset='utf8mb4',autocommit=False,cursorclass=pymysql.cursors.DictCursor)

def f(r,k,d=0.0):
    try: return float((r or {}).get(k,d) or 0)
    except Exception: return d

def sigmoid(x): return 1/(1+math.exp(-x))

def main():
    a=parse_args(); c=conn(a)
    try:
        with c.cursor() as cur:
            where='profile_id=%s AND target_date=%s AND run_id=%s'; params=[a.profile_id,a.target_date,a.run_id]
            if a.source_gen_run_id is not None:
                where+=' AND source_gen_run_id=%s'; params.append(a.source_gen_run_id)
            cur.execute('SELECT * FROM v05_ml_feature_snapshot_day WHERE '+where,params); feat=cur.fetchone()
            if not feat: raise RuntimeError('missing v05_ml_feature_snapshot_day')
            # Interface calibration: a deterministic small model until backfill training is requested.
            raw = (1.25*f(feat,'reconciliation_gap') + 1.4*f(feat,'payment_state_gap') + 1.0*f(feat,'orphan_ratio') +
                   2.0*f(feat,'duplicate_ratio') + 1.1*f(feat,'conversion_distortion') + 0.8*f(feat,'transaction_without_state_ratio'))
            prob = max(0,min(1,sigmoid(raw-1.6)))
            severity = max(0,min(1,0.65*f(feat,'overall_risk_score') + 0.35*prob))
            level=(feat.get('final_risk_level') or 'unknown').lower()
            if level in ('stable','normal') or (level=='low' and severity < 0.25):
                pred='normal_reconciliation_variation'
            elif severity >= 0.75:
                pred='critical_reconciliation_failure'
            elif severity >= 0.55:
                pred='high_reconciliation_risk'
            elif severity >= 0.30:
                pred='warning_reconciliation_risk'
            else:
                pred='low_reconciliation_residual'
            expected=LEVEL_MAP.get(level, f(feat,'overall_risk_score'))
            score_gap=abs(severity-expected)
            status='PASS' if score_gap <= 0.35 else 'REVIEW'
            payload={'model_role':'supplemental_ml_calibration','model_source':'heuristic_interface_until_backfill_training','rule_semantic_source_of_truth':True,'does_not_update_unified_score':True,'features_used':['reconciliation_gap','payment_state_gap','orphan_ratio','duplicate_ratio','conversion_distortion','transaction_without_state_ratio'],'backfill_ready':True}
            if a.truncate_target: cur.execute('DELETE FROM v05_ml_calibration_result_day WHERE '+where,params)
            cur.execute('''INSERT INTO v05_ml_calibration_result_day(run_id,profile_id,source_gen_run_id,target_date,scenario_name,predicted_risk_class,predicted_severity_score,reconciliation_failure_probability,score_gap,calibration_status,model_source,ml_payload_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (a.run_id,a.profile_id,a.source_gen_run_id,a.target_date,a.scenario_name,pred,severity,prob,score_gap,status,'heuristic_interface',json.dumps(payload,ensure_ascii=False)))
        c.commit(); print('[build_v05_ml_calibration] OK')
    except Exception:
        c.rollback(); raise
    finally:
        c.close()
if __name__=='__main__': main()
