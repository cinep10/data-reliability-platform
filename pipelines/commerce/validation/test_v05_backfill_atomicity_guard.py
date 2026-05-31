from __future__ import annotations
import argparse
import sys
import pymysql

PHASE5_TABLES = [
    'v05_ml_feature_snapshot_day',
    'v05_ml_calibration_result_day',
    'v05_ai_incident_context_day',
    'v05_ai_incident_summary_day',
    'v05_ai_validation_result_day',
    'v05_ai_reliability_score_day',
]

def parse_args():
    p=argparse.ArgumentParser(description='Validate v0.5 backfill atomicity: Phase5 outputs must share the same run/source ids and not mix stale evidence.')
    for k in ['db-host','db-user','db-pass','db-name','profile-id','target-date','scenario-name']:
        p.add_argument('--'+k, required=True)
    p.add_argument('--db-port', type=int, required=True)
    p.add_argument('--run-id', type=int)
    p.add_argument('--source-gen-run-id', type=int)
    return p.parse_args()

def conn(a):
    return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset='utf8mb4',autocommit=True,cursorclass=pymysql.cursors.DictCursor)

def main():
    a=parse_args(); failed=[]
    c=conn(a)
    try:
        with c.cursor() as cur:
            # Resolve expected latest Phase4 run if omitted.
            if a.run_id is None:
                cur.execute("""SELECT run_id, source_gen_run_id FROM unified_reliability_score_day_v05
                              WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                              ORDER BY created_at DESC, run_id DESC LIMIT 1""", [a.profile_id,a.target_date,a.scenario_name])
                row=cur.fetchone()
                if not row:
                    print('[FAIL] missing Phase4 unified score for atomicity guard'); sys.exit(1)
                a.run_id=int(row['run_id']); a.source_gen_run_id=row.get('source_gen_run_id')
            print(f'[INFO] atomicity expected run_id={a.run_id} source_gen_run_id={a.source_gen_run_id}')
            for t in PHASE5_TABLES:
                cur.execute(f"""SELECT run_id, COALESCE(source_gen_run_id,-1) source_gen_run_id, COUNT(*) c
                               FROM {t}
                               WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                               GROUP BY run_id, COALESCE(source_gen_run_id,-1)""", [a.profile_id,a.target_date,a.scenario_name])
                rows=cur.fetchall()
                print(f'[CHECK] {t}: {rows}')
                if len(rows) != 1:
                    failed.append(f'{t}:expected_one_run_group_got_{len(rows)}')
                    continue
                r=rows[0]
                if int(r['run_id']) != int(a.run_id):
                    failed.append(f'{t}:run_id_mismatch:{r["run_id"]}!={a.run_id}')
                expected_sg = int(a.source_gen_run_id) if a.source_gen_run_id is not None else -1
                if int(r['source_gen_run_id']) != expected_sg:
                    failed.append(f'{t}:source_gen_run_id_mismatch:{r["source_gen_run_id"]}!={expected_sg}')
            # Verify AI summary did not invent action outside governed action table.
            cur.execute("""SELECT recommended_action FROM action_recommendation_day_v05
                           WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s
                           ORDER BY action_rank LIMIT 1""", [a.profile_id,a.target_date,a.scenario_name,a.run_id])
            action_row=cur.fetchone() or {'recommended_action':'no action'}
            cur.execute("""SELECT recommended_action_summary FROM v05_ai_incident_summary_day
                           WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s
                           ORDER BY created_at DESC LIMIT 1""", [a.profile_id,a.target_date,a.scenario_name,a.run_id])
            summary_row=cur.fetchone()
            if summary_row and action_row['recommended_action'] not in (summary_row.get('recommended_action_summary') or ''):
                failed.append('ai_summary_not_grounded_to_action_layer')
    finally:
        c.close()
    if failed:
        print('[FAIL] backfill atomicity guard failed:', ', '.join(failed)); sys.exit(1)
    print('[OK] v0.5 backfill atomicity guard passed')

if __name__ == '__main__':
    main()
