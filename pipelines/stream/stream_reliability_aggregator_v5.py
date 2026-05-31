#!/usr/bin/env python3
# v0.5 hotfix: stg_event_stream uses `ts` as event timestamp; fallback aggregator must not hardcode event_ts.
from __future__ import annotations
import argparse, pymysql


def connect_mysql(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass, database=args.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def table_exists(cur, name):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (name,))
    return int(cur.fetchone()["cnt"] or 0) == 1

def ensure_tables(cur):
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stream_reliability_summary_minute (
      profile_id VARCHAR(100) NOT NULL DEFAULT 'default',
      metric_minute DATETIME NOT NULL,
      service_domain VARCHAR(100) NOT NULL DEFAULT 'all',
      missing_rate DECIMAL(18,6) NOT NULL DEFAULT 0,
      duplicate_ratio DECIMAL(18,6) NOT NULL DEFAULT 0,
      ordering_gap_score DECIMAL(18,6) NOT NULL DEFAULT 0,
      avg_event_delay_ms DECIMAL(18,6) NOT NULL DEFAULT 0,
      stream_risk_score DECIMAL(18,6) NOT NULL DEFAULT 0,
      issue_flags VARCHAR(255) NULL,
      note VARCHAR(255) NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (profile_id, metric_minute, service_domain)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stream_reliability_summary_day (
      profile_id VARCHAR(100) NOT NULL DEFAULT 'default',
      dt DATE NOT NULL,
      service_domain VARCHAR(100) NOT NULL DEFAULT 'all',
      avg_missing_rate DECIMAL(18,6) NOT NULL DEFAULT 0,
      max_missing_rate DECIMAL(18,6) NOT NULL DEFAULT 0,
      avg_duplicate_ratio DECIMAL(18,6) NOT NULL DEFAULT 0,
      max_duplicate_ratio DECIMAL(18,6) NOT NULL DEFAULT 0,
      max_ordering_gap_score DECIMAL(18,6) NOT NULL DEFAULT 0,
      total_ordering_violations BIGINT NOT NULL DEFAULT 0,
      avg_event_delay_ms DECIMAL(18,6) NOT NULL DEFAULT 0,
      max_event_delay_ms DECIMAL(18,6) NOT NULL DEFAULT 0,
      stream_risk_score DECIMAL(18,6) NOT NULL DEFAULT 0,
      primary_stream_issue VARCHAR(50) NULL,
      note VARCHAR(255) NULL,
      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (profile_id, dt, service_domain)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

def result_inputs_available(cur, profile_id, dt_from, dt_to):
    for t in ["stream_completeness_result", "stream_duplicate_result", "stream_ordering_result", "stream_latency_result"]:
        if not table_exists(cur, t):
            return False
    cur.execute("""
      SELECT
        (SELECT COUNT(*) FROM stream_completeness_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s) +
        (SELECT COUNT(*) FROM stream_duplicate_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s) +
        (SELECT COUNT(*) FROM stream_ordering_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s) +
        (SELECT COUNT(*) FROM stream_latency_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s) AS cnt
    """, (profile_id,dt_from,dt_to,profile_id,dt_from,dt_to,profile_id,dt_from,dt_to,profile_id,dt_from,dt_to))
    return int(cur.fetchone()["cnt"] or 0) > 0

def aggregate_from_result_tables(cur, profile_id, dt_from, dt_to):
    cur.execute("""
    INSERT INTO stream_reliability_summary_minute
    (profile_id, metric_minute, service_domain, missing_rate, duplicate_ratio, ordering_gap_score, avg_event_delay_ms, stream_risk_score, issue_flags, note)
    SELECT g.profile_id, g.metric_minute, g.service_domain,
           COALESCE(c.missing_rate,0), COALESCE(d.duplicate_ratio,0), COALESCE(o.ordering_gap_score,0), COALESCE(l.avg_event_delay_ms,0),
           GREATEST(LEAST(COALESCE(c.missing_rate,0)/0.10,1.0)*85,
                    LEAST(COALESCE(d.duplicate_ratio,0)/0.20,1.0)*70,
                    LEAST(COALESCE(o.ordering_gap_score,0)/20.0,1.0)*55,
                    LEAST(GREATEST(COALESCE(l.avg_event_delay_ms,0)-1000,0)/10000.0,1.0)*35),
           CONCAT_WS(',', CASE WHEN COALESCE(c.missing_rate,0)>=0.01 THEN 'missing' END,
                         CASE WHEN COALESCE(d.duplicate_ratio,0)>=0.02 THEN 'duplicate' END,
                         CASE WHEN COALESCE(o.ordering_gap_score,0)>=5 THEN 'ordering' END,
                         CASE WHEN COALESCE(l.avg_event_delay_ms,0)>=1500 THEN 'delay' END),
           'result-table aggregation'
    FROM (
      SELECT profile_id, metric_minute, service_domain FROM stream_completeness_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s
      UNION SELECT profile_id, metric_minute, service_domain FROM stream_duplicate_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s
      UNION SELECT profile_id, metric_minute, service_domain FROM stream_ordering_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s
      UNION SELECT profile_id, metric_minute, service_domain FROM stream_latency_result WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s
    ) g
    LEFT JOIN stream_completeness_result c ON g.profile_id=c.profile_id AND g.metric_minute=c.metric_minute AND g.service_domain=c.service_domain
    LEFT JOIN stream_duplicate_result d ON g.profile_id=d.profile_id AND g.metric_minute=d.metric_minute AND g.service_domain=d.service_domain
    LEFT JOIN stream_ordering_result o ON g.profile_id=o.profile_id AND g.metric_minute=o.metric_minute AND g.service_domain=o.service_domain
    LEFT JOIN stream_latency_result l ON g.profile_id=l.profile_id AND g.metric_minute=l.metric_minute AND g.service_domain=l.service_domain
    """, (profile_id,dt_from,dt_to,profile_id,dt_from,dt_to,profile_id,dt_from,dt_to,profile_id,dt_from,dt_to))

def aggregate_from_stg_fallback(cur, profile_id, dt_from, dt_to):
    if not table_exists(cur, "stg_event_stream"):
        return 0
    cur.execute("""
    INSERT INTO stream_reliability_summary_minute
    (profile_id, metric_minute, service_domain, missing_rate, duplicate_ratio, ordering_gap_score, avg_event_delay_ms, stream_risk_score, issue_flags, note)
    SELECT profile_id,
           STR_TO_DATE(DATE_FORMAT(COALESCE(ts, CONCAT(dt,' 00:00:00')), '%%Y-%%m-%%d %%H:%%i:00'), '%%Y-%%m-%%d %%H:%%i:%%s') AS metric_minute,
           COALESCE(service_domain,'commerce') AS service_domain,
           0, 0, 0, 0, 0, NULL,
           'fallback aggregation from stg_event_stream because stream result tables are empty or unavailable'
    FROM stg_event_stream
    WHERE profile_id=%s AND dt BETWEEN %s AND %s
    GROUP BY profile_id, metric_minute, service_domain
    """, (profile_id, dt_from, dt_to))
    return cur.rowcount

def aggregate_day(cur, profile_id, dt_from, dt_to):
    cur.execute("""
    INSERT INTO stream_reliability_summary_day
    (profile_id, dt, service_domain, avg_missing_rate, max_missing_rate, avg_duplicate_ratio, max_duplicate_ratio,
     max_ordering_gap_score, total_ordering_violations, avg_event_delay_ms, max_event_delay_ms, stream_risk_score,
     primary_stream_issue, note)
    SELECT profile_id, DATE(metric_minute), service_domain,
           AVG(missing_rate), MAX(missing_rate), AVG(duplicate_ratio), MAX(duplicate_ratio),
           MAX(ordering_gap_score), SUM(CASE WHEN ordering_gap_score>=5 THEN 1 ELSE 0 END),
           AVG(avg_event_delay_ms), MAX(avg_event_delay_ms), MAX(stream_risk_score),
           CASE WHEN MAX(missing_rate)>=0.01 THEN 'missing'
                WHEN MAX(duplicate_ratio)>=0.02 THEN 'duplicate'
                WHEN MAX(ordering_gap_score)>=5 THEN 'ordering'
                WHEN MAX(avg_event_delay_ms)>=1500 THEN 'delay'
                ELSE NULL END,
           'daily rollup from stream_reliability_summary_minute'
    FROM stream_reliability_summary_minute
    WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s
    GROUP BY profile_id, DATE(metric_minute), service_domain
    """, (profile_id, dt_from, dt_to))

def main():
    ap = argparse.ArgumentParser(description="Build stream reliability summary minute/day with Kafka-off fallback support.")
    ap.add_argument("--db-host", default="127.0.0.1"); ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", required=True); ap.add_argument("--db-pass", default=""); ap.add_argument("--db-name", required=True)
    ap.add_argument("--profile-id", required=True); ap.add_argument("--dt-from", required=True); ap.add_argument("--dt-to", required=True)
    args = ap.parse_args(); conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            ensure_tables(cur)
            cur.execute("DELETE FROM stream_reliability_summary_minute WHERE profile_id=%s AND DATE(metric_minute) BETWEEN %s AND %s", (args.profile_id,args.dt_from,args.dt_to))
            cur.execute("DELETE FROM stream_reliability_summary_day WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id,args.dt_from,args.dt_to))
            if result_inputs_available(cur,args.profile_id,args.dt_from,args.dt_to):
                aggregate_from_result_tables(cur,args.profile_id,args.dt_from,args.dt_to)
                mode="result_tables"
            else:
                rows=aggregate_from_stg_fallback(cur,args.profile_id,args.dt_from,args.dt_to)
                mode=f"stg_event_stream_fallback rows={rows}"
            aggregate_day(cur,args.profile_id,args.dt_from,args.dt_to)
        conn.commit(); print(f"[stream_reliability_aggregator_v5] done mode={mode}")
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
if __name__ == "__main__": main()
