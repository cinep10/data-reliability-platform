#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from datetime import datetime
import pymysql

def connect(args):
    return pymysql.connect(
        host=args.host, port=args.port, user=args.user, password=args.password,
        database=args.db, charset='utf8mb4', autocommit=False,
        cursorclass=pymysql.cursors.DictCursor
    )

def percentile(vals, p):
    if not vals:
        return 0.0
    vals = sorted(vals)
    if len(vals) == 1:
        return float(vals[0])
    k = (len(vals)-1) * p
    f = math.floor(k); c = math.ceil(k)
    if f == c:
        return float(vals[int(k)])
    return float(vals[f] * (c-k) + vals[c] * (k-f))

def fetch_metric(cur, table_name, metric_col, profile_id, dt_from, dt_to):
    cur.execute(f"""
        SELECT CAST({metric_col} AS DECIMAL(20,6)) AS v
        FROM {table_name}
        WHERE profile_id=%s
          AND DATE(metric_minute) BETWEEN %s AND %s
          AND {metric_col} IS NOT NULL
    """, (profile_id, dt_from, dt_to))
    return sorted([float(r['v']) for r in cur.fetchall() if float(r['v']) > 0])

def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stream_risk_threshold_profile (
          profile_id VARCHAR(64) NOT NULL,
          threshold_scope VARCHAR(20) NOT NULL DEFAULT 'auto_v3',
          dt_from DATE NOT NULL,
          dt_to DATE NOT NULL,
          missing_warn DECIMAL(18,6) NOT NULL DEFAULT 0.01,
          missing_fail DECIMAL(18,6) NOT NULL DEFAULT 0.10,
          duplicate_warn DECIMAL(18,6) NOT NULL DEFAULT 0.02,
          duplicate_fail DECIMAL(18,6) NOT NULL DEFAULT 0.10,
          ordering_warn DECIMAL(18,6) NOT NULL DEFAULT 4,
          ordering_fail DECIMAL(18,6) NOT NULL DEFAULT 12,
          delay_warn DECIMAL(18,6) NOT NULL DEFAULT 300,
          delay_fail DECIMAL(18,6) NOT NULL DEFAULT 1200,
          missing_weight DECIMAL(18,6) NOT NULL DEFAULT 1.00,
          duplicate_weight DECIMAL(18,6) NOT NULL DEFAULT 0.90,
          ordering_weight DECIMAL(18,6) NOT NULL DEFAULT 0.55,
          delay_weight DECIMAL(18,6) NOT NULL DEFAULT 0.35,
          stats_json LONGTEXT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (profile_id, threshold_scope)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', required=True)
    ap.add_argument('--port', type=int, required=True)
    ap.add_argument('--user', required=True)
    ap.add_argument('--password', default='')
    ap.add_argument('--db', required=True)
    ap.add_argument('--profile-id', required=True)
    ap.add_argument('--dt-from', required=True)
    ap.add_argument('--dt-to', required=True)
    args = ap.parse_args()

    conn = connect(args)
    try:
        with conn.cursor() as cur:
            ensure_table(cur)
            miss = fetch_metric(cur, 'stream_completeness_result', 'missing_rate', args.profile_id, args.dt_from, args.dt_to)
            dup = fetch_metric(cur, 'stream_duplicate_result', 'duplicate_ratio', args.profile_id, args.dt_from, args.dt_to)
            ordv = fetch_metric(cur, 'stream_ordering_result', 'ordering_gap_score', args.profile_id, args.dt_from, args.dt_to)
            dly = fetch_metric(cur, 'stream_latency_result', 'avg_event_delay_ms', args.profile_id, args.dt_from, args.dt_to)

            missing_warn = min(max(0.01, round(percentile(miss, 0.30), 6)), 0.05) if miss else 0.02
            missing_fail = min(max(round(percentile(miss, 0.80), 6), round(missing_warn * 1.8, 6)), 0.25) if miss else 0.10
            duplicate_warn = min(max(0.02, round(percentile(dup, 0.30), 6)), 0.08) if dup else 0.03
            duplicate_fail = min(max(round(percentile(dup, 0.80), 6), round(duplicate_warn * 1.8, 6)), 0.25) if dup else 0.10
            ordering_warn = min(max(4.0, round(percentile(ordv, 0.50), 6)), 12.0) if ordv else 5.0
            ordering_fail = max(round(percentile(ordv, 0.85), 6), round(ordering_warn * 1.5, 6)) if ordv else 12.0
            delay_warn = min(max(300.0, round(percentile(dly, 0.35), 6)), 1200.0) if dly else 400.0
            delay_fail = max(round(percentile(dly, 0.80), 6), round(delay_warn * 1.8, 6)) if dly else 1200.0

            payload = {
                'built_at': datetime.now().isoformat(timespec='seconds'),
                'profile_id': args.profile_id,
                'dt_from': args.dt_from,
                'dt_to': args.dt_to,
                'missing_warn': missing_warn,
                'missing_fail': missing_fail,
                'duplicate_warn': duplicate_warn,
                'duplicate_fail': duplicate_fail,
                'ordering_warn': ordering_warn,
                'ordering_fail': ordering_fail,
                'delay_warn': delay_warn,
                'delay_fail': delay_fail,
                'missing_weight': 1.00,
                'duplicate_weight': 0.90,
                'ordering_weight': 0.55,
                'delay_weight': 0.35
            }

            cur.execute("""
                INSERT INTO stream_risk_threshold_profile
                (profile_id, threshold_scope, dt_from, dt_to,
                 missing_warn, missing_fail, duplicate_warn, duplicate_fail,
                 ordering_warn, ordering_fail, delay_warn, delay_fail,
                 missing_weight, duplicate_weight, ordering_weight, delay_weight, stats_json)
                VALUES (%s,'auto_v3',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  dt_from=VALUES(dt_from), dt_to=VALUES(dt_to),
                  missing_warn=VALUES(missing_warn), missing_fail=VALUES(missing_fail),
                  duplicate_warn=VALUES(duplicate_warn), duplicate_fail=VALUES(duplicate_fail),
                  ordering_warn=VALUES(ordering_warn), ordering_fail=VALUES(ordering_fail),
                  delay_warn=VALUES(delay_warn), delay_fail=VALUES(delay_fail),
                  missing_weight=VALUES(missing_weight), duplicate_weight=VALUES(duplicate_weight),
                  ordering_weight=VALUES(ordering_weight), delay_weight=VALUES(delay_weight),
                  stats_json=VALUES(stats_json)
            """, (
                args.profile_id, args.dt_from, args.dt_to,
                missing_warn, missing_fail,
                duplicate_warn, duplicate_fail,
                ordering_warn, ordering_fail,
                delay_warn, delay_fail,
                1.00, 0.90, 0.55, 0.35,
                json.dumps(payload, ensure_ascii=False)
            ))
        conn.commit()
        print('[auto_stream_risk_threshold_tuner_v3] done')
    finally:
        conn.close()

if __name__ == '__main__':
    main()
