from __future__ import annotations
import argparse
import pymysql

def connect_mysql(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset='utf8mb4', autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)

def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stream_ordering_result (
          id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          profile_id VARCHAR(64) NOT NULL DEFAULT 'default',
          metric_minute DATETIME NOT NULL,
          service_domain VARCHAR(50) NULL,
          ordering_violation_count BIGINT NOT NULL DEFAULT 0,
          ordering_gap_score DECIMAL(18,6) NOT NULL DEFAULT 0,
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
            cur.execute('DELETE FROM stream_ordering_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s',
                        (args.profile_id, args.dt_from, args.dt_to))
            cur.execute("""
                INSERT INTO stream_ordering_result
                (profile_id, metric_minute, service_domain, ordering_violation_count, ordering_gap_score, status, note)
                SELECT
                    %s,
                    metric_minute,
                    service_domain,
                    SUM(CASE WHEN curr_seq <= prev_seq THEN 1 ELSE 0 END) AS ordering_violation_count,
                    AVG(CASE WHEN curr_seq <= prev_seq THEN ABS(curr_seq - prev_seq) ELSE 0 END) AS ordering_gap_score,
                    CASE
                        WHEN SUM(CASE WHEN curr_seq <= prev_seq THEN 1 ELSE 0 END) >= 10 THEN 'fail'
                        WHEN SUM(CASE WHEN curr_seq <= prev_seq THEN 1 ELSE 0 END) >= 1 THEN 'warn'
                        ELSE 'ok'
                    END AS status,
                    'ordering anchored to producer/event minute; uses sequence then stream_offset' AS note
                FROM (
                    SELECT
                        DATE_FORMAT(COALESCE(producer_ts, ts), '%%Y-%%m-%%d %%H:%%i:00') AS metric_minute,
                        COALESCE(service_domain,'all') AS service_domain,
                        COALESCE(sequence_no, stream_offset) AS curr_seq,
                        LAG(COALESCE(sequence_no, stream_offset)) OVER (
                            PARTITION BY COALESCE(service_domain,'all'), stream_partition
                            ORDER BY COALESCE(producer_ts, ts), stream_offset, stream_ingest_id
                        ) AS prev_seq
                    FROM stg_event_stream
                    WHERE dt BETWEEN %s AND %s
                ) x
                GROUP BY metric_minute, service_domain
            """, (args.profile_id, args.dt_from, args.dt_to))
        conn.commit()
        print('[stream_ordering_runner_v3] done')
    finally:
        conn.close()

if __name__ == '__main__':
    main()
