import argparse
import pymysql
from typing import List, Any


def get_conn(args):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def execute(conn, sql: str, params: List[Any] | None = None):
    with conn.cursor() as cur:
        cur.execute(sql, params or [])
    return cur.rowcount


parser = argparse.ArgumentParser()
parser.add_argument("--db-host", default="127.0.0.1")
parser.add_argument("--db-port", type=int, default=3306)
parser.add_argument("--db-user", default="root")
parser.add_argument("--db-pass", default="")
parser.add_argument("--db-name", required=True)
parser.add_argument("--profile-id", required=True)
parser.add_argument("--dt-from", required=True)
parser.add_argument("--dt-to", required=True)
parser.add_argument("--run-id", type=int, default=None)
parser.add_argument("--truncate-target", action="store_true")
parser.add_argument("--baseline-throughput-per-minute", type=float, default=0)
parser.add_argument("--warmup-seconds", type=int, default=3)
parser.add_argument("--throughput-baseline-mode", choices=["auto_active_minutes", "argument"], default="auto_active_minutes")
args = parser.parse_args()

conn = get_conn(args)
try:
    params_base = [args.dt_from, args.dt_to, args.profile_id]
    if args.truncate_target:
        if args.run_id is None:
            execute(
                conn,
                """
                DELETE FROM pipeline_performance_summary_minute
                WHERE dt BETWEEN %s AND %s
                  AND pipeline_name=%s
                  AND entity_scope IN ('stream_replay_consumer','batch_input_day_builder')
                """,
                params_base,
            )
        else:
            execute(
                conn,
                """
                DELETE FROM pipeline_performance_summary_minute
                WHERE dt BETWEEN %s AND %s
                  AND pipeline_name=%s
                  AND entity_scope IN ('stream_replay_consumer','batch_input_day_builder')
                  AND run_id=%s
                """,
                params_base + [args.run_id],
            )
        conn.commit()

    ce_run_filter = " AND run_id = %s" if args.run_id is not None else ""
    r_run_filter = " AND run_id = %s" if args.run_id is not None else ""
    joined_r_run_filter = " AND r.run_id = %s" if args.run_id is not None else ""
    b_run_filter = " AND run_id = %s" if args.run_id is not None else ""

    params_ce = [args.profile_id, args.dt_from, args.dt_to]
    params_replay = [args.profile_id, args.dt_from, args.dt_to]
    params_joined = [args.profile_id, args.dt_from, args.dt_to]
    if args.run_id is not None:
        params_ce.append(args.run_id)
        params_replay.append(args.run_id)
        params_joined.append(args.run_id)

    sql_stream = f"""
    INSERT INTO pipeline_performance_summary_minute (
        minute_ts, dt, pipeline_name, entity_scope, processing_mode, runtime_mode, run_id, source_gen_run_id,
        expected_event_count, observed_event_count, throughput_per_minute, baseline_throughput_per_minute,
        throughput_drop_ratio, freshness_delay_sec_p50, freshness_delay_sec_p95, freshness_delay_sec_max,
        consumer_lag_p50, consumer_lag_p95, consumer_lag_max, backlog_size_avg, backlog_size_max, recovery_sec, metric_version
    )
    WITH canonical_baseline AS (
        SELECT
            profile_id,
            target_date,
            COALESCE(run_id, 0) AS run_id,
            COUNT(*) AS canonical_cnt,
            COUNT(DISTINCT STR_TO_DATE(DATE_FORMAT(event_time, '%%Y-%%m-%%d %%H:%%i:00'), '%%Y-%%m-%%d %%H:%%i:00')) AS active_minutes,
            COUNT(*) / NULLIF(COUNT(DISTINCT STR_TO_DATE(DATE_FORMAT(event_time, '%%Y-%%m-%%d %%H:%%i:00'), '%%Y-%%m-%%d %%H:%%i:00')), 0) AS baseline_tpm
        FROM canonical_events
        WHERE profile_id=%s
          AND target_date BETWEEN %s AND %s
          {ce_run_filter}
        GROUP BY profile_id, target_date, COALESCE(run_id, 0)
    ), replay_bounds AS (
        SELECT
            profile_id,
            target_date,
            COALESCE(run_id, 0) AS run_id,
            MIN(replayed_at) AS replay_start_ts,
            MAX(replayed_at) AS replay_end_ts,
            COUNT(*) AS replay_event_count
        FROM stream_replay_event
        WHERE profile_id=%s
          AND target_date BETWEEN %s AND %s
          {r_run_filter}
        GROUP BY profile_id, target_date, COALESCE(run_id, 0)
    ), joined AS (
        SELECT
            STR_TO_DATE(DATE_FORMAT(c.event_time, '%%Y-%%m-%%d %%H:%%i:00'), '%%Y-%%m-%%d %%H:%%i:00') AS minute_ts,
            r.target_date AS dt,
            r.profile_id AS pipeline_name,
            'stream_replay_consumer' AS entity_scope,
            'stream' AS processing_mode,
            'replay' AS runtime_mode,
            COALESCE(r.run_id,0) AS run_id,
            r.source_gen_run_id,
            r.replay_event_id,
            cb.canonical_cnt,
            CASE
              WHEN %s = 'argument' AND %s > 0 THEN %s
              ELSE cb.baseline_tpm
            END AS baseline_tpm,
            CASE
                WHEN TIMESTAMPDIFF(SECOND, rb.replay_start_ts, r.replayed_at) <= %s THEN 0
                ELSE GREATEST(0,
                    TIMESTAMPDIFF(MICROSECOND, rb.replay_start_ts, r.replayed_at) / 1000000.0
                    - (r.replay_sequence / NULLIF(cb.baseline_tpm / 60.0, 0))
                )
            END AS lag_sec,
            CASE
                WHEN TIMESTAMPDIFF(SECOND, rb.replay_start_ts, r.replayed_at) <= %s THEN 0
                ELSE GREATEST(0,
                    ((TIMESTAMPDIFF(MICROSECOND, rb.replay_start_ts, r.replayed_at) / 1000000.0) * (cb.baseline_tpm / 60.0))
                    - r.replay_sequence
                )
            END AS backlog_size,
            COUNT(*) OVER (
                PARTITION BY STR_TO_DATE(DATE_FORMAT(c.event_time, '%%Y-%%m-%%d %%H:%%i:00'), '%%Y-%%m-%%d %%H:%%i:00')
            ) AS cnt_in_minute,
            ROW_NUMBER() OVER (
                PARTITION BY STR_TO_DATE(DATE_FORMAT(c.event_time, '%%Y-%%m-%%d %%H:%%i:00'), '%%Y-%%m-%%d %%H:%%i:00')
                ORDER BY CASE
                    WHEN TIMESTAMPDIFF(SECOND, rb.replay_start_ts, r.replayed_at) <= %s THEN 0
                    ELSE GREATEST(0,
                        TIMESTAMPDIFF(MICROSECOND, rb.replay_start_ts, r.replayed_at) / 1000000.0
                        - (r.replay_sequence / NULLIF(cb.baseline_tpm / 60.0, 0))
                    )
                END,
                r.replay_sequence
            ) AS rn_in_minute
        FROM stream_replay_event r
        JOIN canonical_events c
          ON c.profile_id=r.profile_id
         AND c.target_date=r.target_date
         AND c.run_id=r.run_id
         AND c.canonical_event_id=r.canonical_event_id
        JOIN replay_bounds rb
          ON rb.profile_id=r.profile_id
         AND rb.target_date=r.target_date
         AND rb.run_id=COALESCE(r.run_id,0)
        JOIN canonical_baseline cb
          ON cb.profile_id=r.profile_id
         AND cb.target_date=r.target_date
         AND cb.run_id=COALESCE(r.run_id,0)
        WHERE r.profile_id=%s
          AND r.target_date BETWEEN %s AND %s
          {joined_r_run_filter}
    ), agg AS (
        SELECT
            minute_ts,
            dt,
            pipeline_name,
            entity_scope,
            processing_mode,
            runtime_mode,
            run_id,
            MAX(source_gen_run_id) AS source_gen_run_id,
            MAX(canonical_cnt) AS expected_event_count,
            COUNT(*) AS observed_event_count,
            COUNT(*) AS throughput_per_minute,
            MAX(baseline_tpm) AS baseline_throughput_per_minute,
            GREATEST(0, 1 - (COUNT(*) / NULLIF(MAX(baseline_tpm), 0))) AS throughput_drop_ratio,
            AVG(CASE WHEN rn_in_minute IN (GREATEST(1, FLOOR(cnt_in_minute * 0.50)), GREATEST(1, CEIL(cnt_in_minute * 0.50))) THEN lag_sec END) AS freshness_delay_sec_p50,
            AVG(CASE WHEN rn_in_minute IN (GREATEST(1, FLOOR(cnt_in_minute * 0.95)), GREATEST(1, CEIL(cnt_in_minute * 0.95))) THEN lag_sec END) AS freshness_delay_sec_p95,
            MAX(lag_sec) AS freshness_delay_sec_max,
            AVG(CASE WHEN rn_in_minute IN (GREATEST(1, FLOOR(cnt_in_minute * 0.50)), GREATEST(1, CEIL(cnt_in_minute * 0.50))) THEN lag_sec END) AS consumer_lag_p50,
            AVG(CASE WHEN rn_in_minute IN (GREATEST(1, FLOOR(cnt_in_minute * 0.95)), GREATEST(1, CEIL(cnt_in_minute * 0.95))) THEN lag_sec END) AS consumer_lag_p95,
            MAX(lag_sec) AS consumer_lag_max,
            AVG(backlog_size) AS backlog_size_avg,
            MAX(backlog_size) AS backlog_size_max,
            NULL AS recovery_sec,
            'v6_1_event_time_active_minutes_baseline' AS metric_version
        FROM joined
        GROUP BY minute_ts, dt, pipeline_name, entity_scope, processing_mode, runtime_mode, run_id
    )
    SELECT * FROM agg
    ON DUPLICATE KEY UPDATE
        source_gen_run_id=VALUES(source_gen_run_id),
        expected_event_count=VALUES(expected_event_count),
        observed_event_count=VALUES(observed_event_count),
        throughput_per_minute=VALUES(throughput_per_minute),
        baseline_throughput_per_minute=VALUES(baseline_throughput_per_minute),
        throughput_drop_ratio=VALUES(throughput_drop_ratio),
        freshness_delay_sec_p50=VALUES(freshness_delay_sec_p50),
        freshness_delay_sec_p95=VALUES(freshness_delay_sec_p95),
        freshness_delay_sec_max=VALUES(freshness_delay_sec_max),
        consumer_lag_p50=VALUES(consumer_lag_p50),
        consumer_lag_p95=VALUES(consumer_lag_p95),
        consumer_lag_max=VALUES(consumer_lag_max),
        backlog_size_avg=VALUES(backlog_size_avg),
        backlog_size_max=VALUES(backlog_size_max),
        recovery_sec=VALUES(recovery_sec),
        metric_version=VALUES(metric_version)
    """
    params = (
        params_ce
        + params_replay
        + [
            args.throughput_baseline_mode,
            args.baseline_throughput_per_minute,
            args.baseline_throughput_per_minute,
            args.warmup_seconds,
            args.warmup_seconds,
            args.warmup_seconds,
        ]
        + params_joined
    )
    execute(conn, sql_stream, params)

    batch_ce_filter = " AND run_id = %s" if args.run_id is not None else ""
    batch_b_filter = " AND run_id = %s" if args.run_id is not None else ""

    batch_ce = [args.profile_id, args.dt_from, args.dt_to]
    batch_b = [args.profile_id, args.dt_from, args.dt_to]
    if args.run_id is not None:
        batch_ce.append(args.run_id)
        batch_b.append(args.run_id)

    sql_batch = f"""
    INSERT INTO pipeline_performance_summary_minute (
        minute_ts, dt, pipeline_name, entity_scope, processing_mode, runtime_mode, run_id, source_gen_run_id,
        expected_event_count, observed_event_count, throughput_per_minute, baseline_throughput_per_minute,
        throughput_drop_ratio, freshness_delay_sec_p50, freshness_delay_sec_p95, freshness_delay_sec_max,
        consumer_lag_p50, consumer_lag_p95, consumer_lag_max, backlog_size_avg, backlog_size_max, recovery_sec, metric_version
    )
    WITH ce AS (
        SELECT target_date, COALESCE(run_id,0) AS run_id, MAX(source_gen_run_id) AS source_gen_run_id, COUNT(*) AS expected_cnt
        FROM canonical_events
        WHERE profile_id=%s
          AND target_date BETWEEN %s AND %s
          {batch_ce_filter}
        GROUP BY target_date, COALESCE(run_id,0)
    ), bi AS (
        SELECT
            target_date,
            COALESCE(run_id,0) AS run_id,
            MIN(created_at) AS minute_ts,
            SUM(event_count) AS observed_cnt
        FROM batch_input_day
        WHERE profile_id=%s
          AND target_date BETWEEN %s AND %s
          {batch_b_filter}
        GROUP BY target_date, COALESCE(run_id,0)
    )
    SELECT
        COALESCE(bi.minute_ts, STR_TO_DATE(CONCAT(ce.target_date,' 00:00:00'), '%%Y-%%m-%%d %%H:%%i:%%s')) AS minute_ts,
        ce.target_date AS dt,
        %s AS pipeline_name,
        'batch_input_day_builder' AS entity_scope,
        'batch' AS processing_mode,
        'replay' AS runtime_mode,
        ce.run_id,
        ce.source_gen_run_id,
        ce.expected_cnt,
        COALESCE(bi.observed_cnt,0),
        COALESCE(bi.observed_cnt,0),
        NULL,
        CASE WHEN ce.expected_cnt = 0 THEN NULL ELSE GREATEST(0, 1 - (COALESCE(bi.observed_cnt,0) / ce.expected_cnt)) END,
        0,0,0,0,0,0,
        GREATEST(0, ce.expected_cnt - COALESCE(bi.observed_cnt,0)),
        GREATEST(0, ce.expected_cnt - COALESCE(bi.observed_cnt,0)),
        NULL,
        'v6_1_batch_passthrough'
    FROM ce
    LEFT JOIN bi ON bi.target_date=ce.target_date AND bi.run_id=ce.run_id
    ON DUPLICATE KEY UPDATE
        source_gen_run_id=VALUES(source_gen_run_id),
        expected_event_count=VALUES(expected_event_count),
        observed_event_count=VALUES(observed_event_count),
        throughput_per_minute=VALUES(throughput_per_minute),
        baseline_throughput_per_minute=VALUES(baseline_throughput_per_minute),
        throughput_drop_ratio=VALUES(throughput_drop_ratio),
        freshness_delay_sec_p50=VALUES(freshness_delay_sec_p50),
        freshness_delay_sec_p95=VALUES(freshness_delay_sec_p95),
        freshness_delay_sec_max=VALUES(freshness_delay_sec_max),
        consumer_lag_p50=VALUES(consumer_lag_p50),
        consumer_lag_p95=VALUES(consumer_lag_p95),
        consumer_lag_max=VALUES(consumer_lag_max),
        backlog_size_avg=VALUES(backlog_size_avg),
        backlog_size_max=VALUES(backlog_size_max),
        recovery_sec=VALUES(recovery_sec),
        metric_version=VALUES(metric_version)
    """
    execute(conn, sql_batch, batch_ce + batch_b + [args.profile_id])

    conn.commit()
    print("[DONE] pipeline_performance_summary_minute built (v6.1 event-time active-minute baseline)")
finally:
    conn.close()
