from __future__ import annotations
import argparse, sys, pymysql
from datetime import date, timedelta

REQUIRED_PHASE4 = [
    'unified_reliability_score_day_v05',
    'semantic_interpretation_day_v05',
    'action_recommendation_day_v05',
]
REQUIRED_PHASE5 = [
    'v05_ml_feature_snapshot_day',
    'v05_ml_calibration_result_day',
    'v05_ai_incident_context_day',
    'v05_ai_incident_summary_day',
    'v05_ai_validation_result_day',
    'v05_ai_reliability_score_day',
]

def parse_args():
    p = argparse.ArgumentParser(description='Validate v0.5 7-day scenario smoke outputs before backfill.')
    for k in ['db-host','db-user','db-pass','db-name','profile-id','start-date','scenarios']:
        p.add_argument('--'+k, required=True)
    p.add_argument('--db-port', type=int, required=True)
    p.add_argument('--days', type=int, default=7)
    return p.parse_args()

def conn(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset='utf8mb4', autocommit=True, cursorclass=pymysql.cursors.DictCursor)

def daterange(start: str, days: int):
    d = date.fromisoformat(start)
    for i in range(days):
        yield (d + timedelta(days=i)).isoformat()

def count(cur, table, where, params):
    cur.execute(f'SELECT COUNT(*) c FROM {table} WHERE {where}', params)
    return int(cur.fetchone()['c'])

def one(cur, sql, params):
    cur.execute(sql, params)
    return cur.fetchone() or {}

def main():
    a = parse_args()
    scenarios = a.scenarios.split()
    failed = []
    c = conn(a)
    try:
        with c.cursor() as cur:
            for dt in daterange(a.start_date, a.days):
                for scenario in scenarios:
                    where = 'profile_id=%s AND target_date=%s AND scenario_name=%s'
                    params = [a.profile_id, dt, scenario]
                    print(f'[CHECK] dt={dt} scenario={scenario}')
                    for table in REQUIRED_PHASE4 + REQUIRED_PHASE5:
                        ok = count(cur, table, where, params) > 0
                        print(f'  {table}: ' + ('PASS' if ok else 'FAIL'))
                        if not ok:
                            failed.append(f'{table}:{dt}:{scenario}')
                    score = one(cur, 'SELECT final_risk_level, overall_risk_score, dominant_semantic_risk FROM unified_reliability_score_day_v05 WHERE '+where+' ORDER BY created_at DESC LIMIT 1', params)
                    action = one(cur, 'SELECT recommended_action FROM action_recommendation_day_v05 WHERE '+where+' ORDER BY action_rank ASC LIMIT 1', params)
                    ai = one(cur, 'SELECT validation_status FROM v05_ai_validation_result_day WHERE '+where+' ORDER BY created_at DESC LIMIT 1', params)
                    if scenario == 'baseline':
                        level = (score.get('final_risk_level') or '').lower()
                        dom = (score.get('dominant_semantic_risk') or '').lower()
                        rec = (action.get('recommended_action') or '').lower()
                        if level not in ('stable','low'):
                            failed.append(f'baseline_level:{dt}:{level}')
                        if dom not in ('', 'none', 'null'):
                            failed.append(f'baseline_dominant:{dt}:{dom}')
                        if 'no action' not in rec:
                            failed.append(f'baseline_action:{dt}:{rec}')
                    if ai.get('validation_status') != 'PASS':
                        failed.append(f'ai_validation:{dt}:{scenario}')
    finally:
        c.close()
    if failed:
        print('[FAIL] scenario smoke readiness failed:', ', '.join(failed[:50]))
        sys.exit(1)
    print('[OK] v0.5 scenario smoke readiness validation passed')

if __name__ == '__main__':
    main()
