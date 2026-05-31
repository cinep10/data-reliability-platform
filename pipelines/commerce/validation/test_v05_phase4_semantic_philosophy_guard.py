from __future__ import annotations
import argparse
import json
import pymysql


def parse_args():
    p = argparse.ArgumentParser(description='Standalone guardrail test: verify v0.5 semantic layer preserves v0.4 Measurement-to-Decision philosophy.')
    p.add_argument('--db-host', required=True)
    p.add_argument('--db-port', type=int, required=True)
    p.add_argument('--db-user', required=True)
    p.add_argument('--db-pass', required=True)
    p.add_argument('--db-name', required=True)
    p.add_argument('--profile-id', required=True)
    p.add_argument('--target-date', required=True)
    p.add_argument('--run-id', type=int, required=True)
    p.add_argument('--source-gen-run-id', type=int)
    return p.parse_args()


def conn(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset='utf8mb4', autocommit=True, cursorclass=pymysql.cursors.DictCursor)


def where(a):
    w = 'profile_id=%s AND target_date=%s AND run_id=%s'
    p = [a.profile_id, a.target_date, a.run_id]
    if a.source_gen_run_id is not None:
        w += ' AND source_gen_run_id=%s'
        p.append(a.source_gen_run_id)
    return w, p


def get_one(cur, table, a):
    w, p = where(a)
    cur.execute(f'SELECT * FROM {table} WHERE {w} LIMIT 1', p)
    return cur.fetchone()


def js(v):
    try:
        return json.loads(v or '{}')
    except Exception:
        return {}


def main():
    a = parse_args()
    c = conn(a)
    failures = []
    with c.cursor() as cur:
        an = get_one(cur, 'reliability_analysis_result_day_v05', a)
        sem = get_one(cur, 'semantic_interpretation_day_v05', a)
        score = get_one(cur, 'unified_reliability_score_day_v05', a)
        action = get_one(cur, 'action_recommendation_day_v05', a)
    c.close()
    for name, row in [('analysis', an), ('semantic', sem), ('score', score), ('action', action)]:
        if not row:
            failures.append(f'missing_{name}')
    if failures:
        raise SystemExit('[FAIL] ' + ', '.join(failures))

    ap = js(an.get('analysis_payload_json'))
    sp = js(sem.get('semantic_payload_json'))
    up = js(score.get('score_payload_json'))
    xp = js(action.get('action_payload_json'))
    checks = {
        'analysis_uses_measurement_source': ap.get('source_table') == 'v05_reconciliation_measurement_day',
        'analysis_separates_expected_incomplete': ap.get('expected_incomplete_handling', {}).get('expected_incomplete_transaction_is_not_failure') is True,
        'analysis_not_scenario_driven': ap.get('v04_philosophy_guard', {}).get('scenario_name_used_as_risk_driver') is False,
        'analysis_no_direct_missing_state_high': ap.get('v04_philosophy_guard', {}).get('raw_missing_state_to_high_risk_direct_mapping') is False,
        'semantic_delta_based': sp.get('v04_philosophy_guard', {}).get('semantic_is_measurement_delta_based') is True,
        'semantic_no_business_heuristic_hardcoding': sp.get('v04_philosophy_guard', {}).get('business_heuristic_hardcoding_detected') is False,
        'score_keeps_boundary': up.get('v04_philosophy_guard', {}).get('measurement_to_semantic_to_score') is True,
        'action_no_final_risk_calc': xp.get('v04_philosophy_guard', {}).get('python_final_semantic_calculation') is False,
    }
    for name, ok in checks.items():
        print(f'[CHECK] {name}: {"PASS" if ok else "FAIL"}')
        if not ok:
            failures.append(name)
    if failures:
        raise SystemExit('[FAIL] ' + ', '.join(failures))
    print('[OK] v0.5 semantic layer preserves v0.4 Measurement-to-Decision philosophy')


if __name__ == '__main__':
    main()
