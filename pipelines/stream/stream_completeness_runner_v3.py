from __future__ import annotations
import argparse
import pymysql

def connect_mysql(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset='utf8mb4', autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)

def ensure_table(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stream_completeness_result (
      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
      profile_id VARCHAR(64) NOT NULL DEFAULT 'default',
      metric_minute DATETIME NOT NULL,
      service_domain VARCHAR(50) NULL,
      expected_count BIGINT NOT NULL DEFAULT 0,
      actual_count BIGINT NOT NULL DEFAULT 0,
      missing_count BIGINT NOT NULL DEFAULT 0,
      missing_rate DECIMAL(18,6) NOT NULL DEFAULT 0,
      status VARCHAR(20) NOT NULL DEFAULT 'ok',
      note VARCHAR(255) NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (id),
      KEY idx_metric_minute (metric_minute),
      KEY idx_profile_dt (profile_id, metric_minute, service_domain)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db-host', default='127.0.0.1')
    ap.add_argument('--db-port', type=int, default=3306)
    ap.add_argument('--db-user', required=True)
    ap.add_argument('--db-pass', default='')
    ap.add_argument('--db-name', required=True)
    ap.add_argument('--profile-id', required=True)
    ap.add_argument('--dt-from', required=True)
    ap.add_argument('--dt-to', required=True)
    args = ap.parse_args()

    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            ensure_table(cur)
            cur.execute('DELETE FROM stream_completeness_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s',
                        (args.profile_id, args.dt_from, args.dt_to))
            cur.execute("""
                INSERT INTO stream_completeness_result
                (profile_id, metric_minute, service_domain, expected_count, actual_count, missing_count, missing_rate, status, note)
                SELECT
                    %s,
                    DATE_FORMAT(e.ts, '%%Y-%%m-%%d %%H:%%i:00') AS metric_minute,
                    COALESCE(e.service_domain, 'all') AS service_domain,
                    COUNT(*) AS expected_count,
                    COUNT(s.stream_ingest_id) AS actual_count,
                    COUNT(*) - COUNT(s.stream_ingest_id) AS missing_count,
                    CASE WHEN COUNT(*) = 0 THEN 0 ELSE (COUNT(*) - COUNT(s.stream_ingest_id)) / COUNT(*) END AS missing_rate,
                    CASE
                        WHEN (COUNT(*) - COUNT(s.stream_ingest_id)) / NULLIF(COUNT(*), 0) >= 0.10 THEN 'fail'
                        WHEN (COUNT(*) - COUNT(s.stream_ingest_id)) / NULLIF(COUNT(*), 0) >= 0.03 THEN 'warn'
                        ELSE 'ok'
                    END AS status,
                    'metric_minute anchored to event_log_raw.ts' AS note
                FROM event_log_raw e
                LEFT JOIN stg_event_stream s
                  ON e.raw_event_id = s.raw_event_id
                 AND s.dt BETWEEN %s AND %s
                WHERE e.dt BETWEEN %s AND %s
                GROUP BY DATE_FORMAT(e.ts, '%%Y-%%m-%%d %%H:%%i:00'), COALESCE(e.service_domain, 'all')
            """, (args.profile_id, args.dt_from, args.dt_to, args.dt_from, args.dt_to))
        conn.commit()
        print('[stream_completeness_runner_v3] done')
    finally:
        conn.close()

if __name__ == '__main__':
    main()
