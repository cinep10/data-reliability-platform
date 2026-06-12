#!/usr/bin/env python3
"""Validate that scenario-calendar backfill produces sensitivity signals.

This is not a hard risk-score gate. It checks that anomaly days exist and that at
least one statistical evidence domain shows a higher max score than the baseline target.
"""
from __future__ import annotations
import argparse
import pymysql


def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument('--db-host', default='127.0.0.1')
    p.add_argument('--db-port', type=int, default=3306)
    p.add_argument('--db-user', required=True)
    p.add_argument('--db-pass', default='')
    p.add_argument('--db-name', required=True)
    p.add_argument('--profile-id', required=True)
    p.add_argument('--from-date', required=True)
    p.add_argument('--to-date', required=True)
    p.add_argument('--baseline-scenario', default='baseline')
    p.add_argument('--anomaly-scenarios', default='source_partial_missing,source_wc_collection_missing')
    p.add_argument('--min-anomaly-days', type=int, default=3)
    p.add_argument('--allow-no-sensitivity', action='store_true')
    return p.parse_args()


def connect(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=True)


def main():
    a=parse_args(); anomalies=[s.strip() for s in a.anomaly_scenarios.split(',') if s.strip()]
    con=connect(a)
    try:
        with con.cursor() as cur:
            cur.execute("""
                SELECT scenario_name, COUNT(DISTINCT target_date) AS days,
                       COUNT(*) AS row_count, MAX(COALESCE(statistical_score,0)) AS max_score,
                       MAX(COALESCE(ABS(z_score),0)) AS max_abs_z,
                       MAX(COALESCE(co_movement_score,0)) AS max_co_movement
                FROM v05_baseline_science_statistical_evidence_day
                WHERE profile_id=%s AND target_date BETWEEN %s AND %s
                  AND evidence_domain IN ('batch_metric_delta','reconciliation_measurement')
                GROUP BY scenario_name
                ORDER BY scenario_name
            """, (a.profile_id, a.from_date, a.to_date))
            rows=cur.fetchall()
            by={r['scenario_name']: r for r in rows}
            for r in rows:
                print(f"[SENSITIVITY] scenario={r['scenario_name']} days={r['days']} rows={r['row_count']} max_score={float(r['max_score'] or 0):.6f} max_abs_z={float(r['max_abs_z'] or 0):.6f} max_co_movement={float(r['max_co_movement'] or 0):.6f}")
            base_score=float((by.get(a.baseline_scenario) or {}).get('max_score') or 0)
            anomaly_days=sum(int((by.get(s) or {}).get('days') or 0) for s in anomalies)
            anomaly_score=max([float((by.get(s) or {}).get('max_score') or 0) for s in anomalies] or [0])
            failures=[]
            if anomaly_days < a.min_anomaly_days:
                failures.append(f'anomaly days {anomaly_days} < {a.min_anomaly_days}')
            if anomaly_score <= base_score and not a.allow_no_sensitivity:
                failures.append(f'anomaly max_score {anomaly_score:.6f} <= baseline max_score {base_score:.6f}')
            if failures:
                print('[FAIL] ' + '; '.join(failures)); return 1
            print('[OK] validate_v05_scenario_sensitivity passed')
            return 0
    finally:
        con.close()

if __name__ == '__main__':
    raise SystemExit(main())
