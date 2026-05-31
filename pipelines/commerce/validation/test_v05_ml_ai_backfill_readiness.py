#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys, pymysql
REQUIRED = [
    'v05_ml_feature_snapshot_day',
    'v05_ml_calibration_result_day',
    'v05_ai_incident_context_day',
    'v05_ai_incident_summary_day',
    'v05_ai_validation_result_day',
    'v05_ai_reliability_score_day',
]
BATCH_REQUIRED = [
    'batch_behavior_distribution_day',
    'r_batch_distribution_analysis_day',
    'batch_behavior_anomaly_day',
]
def parse_args():
    p=argparse.ArgumentParser(description='Validate v0.5 ML/AI backfill readiness including batch distribution/anomaly feature interface.')
    for k in ['db-host','db-user','db-pass','db-name','profile-id','start-date','end-date','scenarios']:
        p.add_argument('--'+k, required=True)
    p.add_argument('--db-port', type=int, required=True)
    p.add_argument('--min-rows-per-scenario', type=int, default=7)
    return p.parse_args()
def conn(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset='utf8mb4', autocommit=True, cursorclass=pymysql.cursors.DictCursor)
def table_exists(cur,t):
    cur.execute("SELECT COUNT(*) c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",(t,)); return int(cur.fetchone()['c'])>0
def has_col(cur,t,c):
    cur.execute("SELECT COUNT(*) c FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s",(t,c)); return int(cur.fetchone()['c'])>0
def scenario_counts(cur, table, profile, start, end, date_col):
    cur.execute(f"SELECT scenario_name, COUNT(*) c FROM {table} WHERE profile_id=%s AND {date_col} BETWEEN %s AND %s GROUP BY scenario_name",(profile,start,end))
    return {r['scenario_name']:int(r['c']) for r in cur.fetchall()}
def main():
    a=parse_args(); scenarios=a.scenarios.split(); failed=[]; c=conn(a)
    try:
        with c.cursor() as cur:
            for table in REQUIRED:
                if not table_exists(cur,table): failed.append(f'missing_table:{table}'); continue
                rows=scenario_counts(cur,table,a.profile_id,a.start_date,a.end_date,'target_date')
                print(f'[SUMMARY] {table}: {rows}')
                for s in scenarios:
                    if rows.get(s,0) < a.min_rows_per_scenario: failed.append(f'{table}:{s}:rows={rows.get(s,0)}')
            for table in BATCH_REQUIRED:
                if not table_exists(cur,table): failed.append(f'missing_table:{table}'); continue
                rows=scenario_counts(cur,table,a.profile_id,a.start_date,a.end_date,'dt')
                print(f'[SUMMARY] {table}: {rows}')
                for s in scenarios:
                    if rows.get(s,0) < a.min_rows_per_scenario: failed.append(f'{table}:{s}:rows={rows.get(s,0)}')
            # batch feature interface columns must exist and be populated in feature snapshot.
            feature_cols=['batch_distribution_risk_score','batch_anomaly_score','batch_anomaly_signal','batch_feature_json']
            for col in feature_cols:
                if not has_col(cur,'v05_ml_feature_snapshot_day',col): failed.append(f'missing_feature_column:{col}')
            cur.execute("SELECT scenario_name, COUNT(*) c FROM v05_ml_feature_snapshot_day WHERE profile_id=%s AND target_date BETWEEN %s AND %s AND COALESCE(CHAR_LENGTH(batch_feature_json),0) > 0 GROUP BY scenario_name",(a.profile_id,a.start_date,a.end_date))
            payload_rows={r['scenario_name']:int(r['c']) for r in cur.fetchall()}
            print('[SUMMARY] batch_feature_json_populated:', payload_rows)
            for s in scenarios:
                if payload_rows.get(s,0) < a.min_rows_per_scenario: failed.append(f'batch_feature_json:{s}:rows={payload_rows.get(s,0)}')
            cur.execute("SELECT predicted_risk_class, COUNT(*) c FROM v05_ml_calibration_result_day WHERE profile_id=%s AND target_date BETWEEN %s AND %s GROUP BY predicted_risk_class",(a.profile_id,a.start_date,a.end_date))
            class_rows={r['predicted_risk_class']:int(r['c']) for r in cur.fetchall()}
            print('[SUMMARY] predicted_risk_class:', class_rows)
            if len(class_rows)<2: print('[WARN] ml_class_diversity_lt_2 - acceptable for short smoke, review before long backfill')
            cur.execute("SELECT validation_status, COUNT(*) c FROM v05_ai_validation_result_day WHERE profile_id=%s AND target_date BETWEEN %s AND %s GROUP BY validation_status",(a.profile_id,a.start_date,a.end_date))
            ai_rows={r['validation_status']:int(r['c']) for r in cur.fetchall()}
            print('[SUMMARY] ai_validation_status:', ai_rows)
            if ai_rows.get('PASS',0)==0: failed.append('no_ai_validation_pass')
    finally:
        c.close()
    if failed:
        print('[FAIL] ML/AI backfill readiness failed:', ', '.join(failed[:80])); sys.exit(1)
    print('[OK] v0.5 ML/AI backfill readiness validation passed')
if __name__=='__main__': main()
