from __future__ import annotations
import argparse, pymysql

def connect_mysql(args):
    return pymysql.connect(host=args.host, port=args.port, user=args.user, password=args.password,
                           database=args.db, charset='utf8mb4', autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)

def ensure_table(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS performance_metric_day (dt DATE NOT NULL, profile_id VARCHAR(64) NOT NULL, throughput_per_sec DECIMAL(18,6) NULL, queue_backlog DECIMAL(18,6) NULL, timeout_count DECIMAL(18,6) NULL, retry_count DECIMAL(18,6) NULL, partial_fail_count DECIMAL(18,6) NULL, fallback_count DECIMAL(18,6) NULL, sampling_ratio DECIMAL(18,6) NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, PRIMARY KEY (profile_id, dt)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1'); ap.add_argument('--port', type=int, default=3306)
    ap.add_argument('--user', required=True); ap.add_argument('--password', default=''); ap.add_argument('--db', required=True)
    ap.add_argument('--profile-id', required=True); ap.add_argument('--dt-from', required=True); ap.add_argument('--dt-to', required=True)
    args = ap.parse_args(); conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            ensure_table(cur)
            cur.execute("""SELECT DISTINCT dt, system_flag, timeout_multiplier, retry_multiplier FROM exogenous_state_timeline WHERE profile_id=%s AND dt BETWEEN %s AND %s AND performance_adapter_apply_flag=1 ORDER BY dt""", (args.profile_id, args.dt_from, args.dt_to))
            rows = cur.fetchall()
            for r in rows:
                dt = r['dt'].isoformat(); system_flag = (r['system_flag'] or 'normal').lower(); timeout_mult = float(r['timeout_multiplier'] or 1.0); retry_mult = float(r['retry_multiplier'] or 1.0)
                timeout_count = 0.0; retry_count = 0.0; queue_backlog = 0.0; partial_fail_count = 0.0
                if system_flag in {'degraded','auth_delay'}:
                    timeout_count = round(100 * (timeout_mult - 1.0), 6); queue_backlog = round(80 * (timeout_mult - 1.0), 6)
                if system_flag in {'degraded','collector_drop'}:
                    retry_count = round(120 * (retry_mult - 1.0), 6)
                if system_flag == 'submit_partial_loss':
                    partial_fail_count = 35.0
                cur.execute("""INSERT INTO performance_metric_day (dt, profile_id, throughput_per_sec, queue_backlog, timeout_count, retry_count, partial_fail_count, fallback_count, sampling_ratio) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE queue_backlog=VALUES(queue_backlog), timeout_count=VALUES(timeout_count), retry_count=VALUES(retry_count), partial_fail_count=VALUES(partial_fail_count)""", (dt, args.profile_id, None, queue_backlog, timeout_count, retry_count, partial_fail_count, 0.0, 0.0))
        conn.commit(); print(f"[OK] performance_adapter completed: profile={args.profile_id}, dt_from={args.dt_from}, dt_to={args.dt_to}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
