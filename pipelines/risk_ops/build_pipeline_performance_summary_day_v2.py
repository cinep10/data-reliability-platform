import argparse
from db_utils import add_db_args, execute, get_connection

parser = argparse.ArgumentParser()
add_db_args(parser)
parser.add_argument('--profile-id', required=True)
parser.add_argument('--dt-from', required=True)
parser.add_argument('--dt-to', required=True)
parser.add_argument('--truncate-target', action='store_true')
args = parser.parse_args()

conn = get_connection(args)
if args.truncate_target:
    execute(conn, 'DELETE FROM pipeline_performance_summary_day WHERE dt BETWEEN %s AND %s AND pipeline_name=%s', [args.dt_from, args.dt_to, args.profile_id])

# stream replay rows from minute summary
stream_sql = """
INSERT INTO pipeline_performance_summary_day (
    dt, pipeline_name, entity_scope, processing_mode, runtime_mode, run_id, source_gen_run_id,
    minute_window_count, active_minute_count, observed_event_count,
    throughput_per_minute_avg, throughput_per_minute_p50, throughput_per_minute_p95,
    throughput_drop_ratio_avg, throughput_drop_ratio_p95, throughput_drop_ratio_max,
    freshness_delay_sec_p50, freshness_delay_sec_p95, freshness_delay_sec_max,
    consumer_lag_p50, consumer_lag_p95, consumer_lag_max,
    backlog_size_avg, backlog_size_p95, backlog_size_max,
    recovery_sec_avg, recovery_sec_max, degraded_minute_count, severe_minute_count, metric_version
)
SELECT
    dt, pipeline_name, entity_scope, processing_mode, runtime_mode, run_id, MAX(source_gen_run_id),
    COUNT(*), SUM(CASE WHEN observed_event_count > 0 THEN 1 ELSE 0 END), SUM(observed_event_count),
    AVG(throughput_per_minute), AVG(throughput_per_minute), MAX(throughput_per_minute),
    AVG(throughput_drop_ratio), MAX(throughput_drop_ratio), MAX(throughput_drop_ratio),
    AVG(freshness_delay_sec_p50), MAX(freshness_delay_sec_p95), MAX(freshness_delay_sec_max),
    AVG(consumer_lag_p50), MAX(consumer_lag_p95), MAX(consumer_lag_max),
    AVG(backlog_size_avg), MAX(backlog_size_avg), MAX(backlog_size_max),
    AVG(recovery_sec), MAX(recovery_sec),
    SUM(CASE WHEN COALESCE(freshness_delay_sec_p95, 0) >= 300 OR COALESCE(consumer_lag_p95, 0) >= 300 OR COALESCE(throughput_drop_ratio, 0) >= 0.30 THEN 1 ELSE 0 END),
    SUM(CASE WHEN COALESCE(freshness_delay_sec_p95, 0) >= 900 OR COALESCE(consumer_lag_p95, 0) >= 900 OR COALESCE(throughput_drop_ratio, 0) >= 0.60 THEN 1 ELSE 0 END),
    MAX(metric_version)
FROM pipeline_performance_summary_minute
WHERE dt BETWEEN %s AND %s AND pipeline_name=%s AND entity_scope='stream_replay_consumer'
GROUP BY dt, pipeline_name, entity_scope, processing_mode, runtime_mode, run_id
ON DUPLICATE KEY UPDATE
    source_gen_run_id=VALUES(source_gen_run_id),
    minute_window_count=VALUES(minute_window_count),
    active_minute_count=VALUES(active_minute_count),
    observed_event_count=VALUES(observed_event_count),
    throughput_per_minute_avg=VALUES(throughput_per_minute_avg),
    throughput_per_minute_p50=VALUES(throughput_per_minute_p50),
    throughput_per_minute_p95=VALUES(throughput_per_minute_p95),
    throughput_drop_ratio_avg=VALUES(throughput_drop_ratio_avg),
    throughput_drop_ratio_p95=VALUES(throughput_drop_ratio_p95),
    throughput_drop_ratio_max=VALUES(throughput_drop_ratio_max),
    freshness_delay_sec_p50=VALUES(freshness_delay_sec_p50),
    freshness_delay_sec_p95=VALUES(freshness_delay_sec_p95),
    freshness_delay_sec_max=VALUES(freshness_delay_sec_max),
    consumer_lag_p50=VALUES(consumer_lag_p50),
    consumer_lag_p95=VALUES(consumer_lag_p95),
    consumer_lag_max=VALUES(consumer_lag_max),
    backlog_size_avg=VALUES(backlog_size_avg),
    backlog_size_p95=VALUES(backlog_size_p95),
    backlog_size_max=VALUES(backlog_size_max),
    recovery_sec_avg=VALUES(recovery_sec_avg),
    recovery_sec_max=VALUES(recovery_sec_max),
    degraded_minute_count=VALUES(degraded_minute_count),
    severe_minute_count=VALUES(severe_minute_count),
    metric_version=VALUES(metric_version)
"""

# batch branch inserted directly at day grain
batch_sql = """
INSERT INTO pipeline_performance_summary_day (
    dt, pipeline_name, entity_scope, processing_mode, runtime_mode, run_id, source_gen_run_id,
    minute_window_count, active_minute_count, observed_event_count,
    throughput_per_minute_avg, throughput_per_minute_p50, throughput_per_minute_p95,
    throughput_drop_ratio_avg, throughput_drop_ratio_p95, throughput_drop_ratio_max,
    freshness_delay_sec_p50, freshness_delay_sec_p95, freshness_delay_sec_max,
    consumer_lag_p50, consumer_lag_p95, consumer_lag_max,
    backlog_size_avg, backlog_size_p95, backlog_size_max,
    recovery_sec_avg, recovery_sec_max, degraded_minute_count, severe_minute_count, metric_version
)
WITH ce AS (
    SELECT
        COALESCE(run_id, 0) AS run_id,
        target_date AS dt,
        profile_id AS pipeline_name,
        MAX(source_gen_run_id) AS source_gen_run_id,
        COUNT(*) AS expected_event_count
    FROM canonical_events
    WHERE profile_id=%s
      AND target_date BETWEEN %s AND %s
    GROUP BY COALESCE(run_id, 0), target_date, profile_id
), bi AS (
    SELECT
        COALESCE(run_id, 0) AS run_id,
        target_date AS dt,
        profile_id AS pipeline_name,
        SUM(event_count) AS observed_event_count,
        COUNT(*) AS batch_row_count,
        TIMESTAMPDIFF(SECOND, MIN(created_at), MAX(created_at)) AS batch_completion_sec
    FROM batch_input_day
    WHERE profile_id=%s
      AND target_date BETWEEN %s AND %s
    GROUP BY COALESCE(run_id, 0), target_date, profile_id
)
SELECT
    ce.dt,
    ce.pipeline_name,
    'batch_input_day_builder' AS entity_scope,
    'batch' AS processing_mode,
    'replay' AS runtime_mode,
    ce.run_id,
    ce.source_gen_run_id,
    1 AS minute_window_count,
    CASE WHEN COALESCE(bi.observed_event_count, 0) > 0 THEN 1 ELSE 0 END AS active_minute_count,
    COALESCE(bi.observed_event_count, 0) AS observed_event_count,
    COALESCE(bi.observed_event_count, 0) / 1440.0 AS throughput_per_minute_avg,
    COALESCE(bi.observed_event_count, 0) / 1440.0 AS throughput_per_minute_p50,
    COALESCE(bi.observed_event_count, 0) / 1440.0 AS throughput_per_minute_p95,
    CASE WHEN ce.expected_event_count = 0 THEN NULL ELSE GREATEST(0, 1 - (COALESCE(bi.observed_event_count, 0) / ce.expected_event_count)) END AS throughput_drop_ratio_avg,
    CASE WHEN ce.expected_event_count = 0 THEN NULL ELSE GREATEST(0, 1 - (COALESCE(bi.observed_event_count, 0) / ce.expected_event_count)) END AS throughput_drop_ratio_p95,
    CASE WHEN ce.expected_event_count = 0 THEN NULL ELSE GREATEST(0, 1 - (COALESCE(bi.observed_event_count, 0) / ce.expected_event_count)) END AS throughput_drop_ratio_max,
    0 AS freshness_delay_sec_p50,
    0 AS freshness_delay_sec_p95,
    0 AS freshness_delay_sec_max,
    0 AS consumer_lag_p50,
    0 AS consumer_lag_p95,
    0 AS consumer_lag_max,
    GREATEST(0, ce.expected_event_count - COALESCE(bi.observed_event_count, 0)) AS backlog_size_avg,
    GREATEST(0, ce.expected_event_count - COALESCE(bi.observed_event_count, 0)) AS backlog_size_p95,
    GREATEST(0, ce.expected_event_count - COALESCE(bi.observed_event_count, 0)) AS backlog_size_max,
    NULL AS recovery_sec_avg,
    NULL AS recovery_sec_max,
    CASE WHEN COALESCE(bi.observed_event_count, 0) < ce.expected_event_count THEN 1 ELSE 0 END AS degraded_minute_count,
    CASE WHEN COALESCE(bi.observed_event_count, 0) = 0 THEN 1 ELSE 0 END AS severe_minute_count,
    'v2_batch_relative' AS metric_version
FROM ce
LEFT JOIN bi
  ON bi.run_id = ce.run_id
 AND bi.dt = ce.dt
 AND bi.pipeline_name = ce.pipeline_name
ON DUPLICATE KEY UPDATE
    source_gen_run_id=VALUES(source_gen_run_id),
    minute_window_count=VALUES(minute_window_count),
    active_minute_count=VALUES(active_minute_count),
    observed_event_count=VALUES(observed_event_count),
    throughput_per_minute_avg=VALUES(throughput_per_minute_avg),
    throughput_per_minute_p50=VALUES(throughput_per_minute_p50),
    throughput_per_minute_p95=VALUES(throughput_per_minute_p95),
    throughput_drop_ratio_avg=VALUES(throughput_drop_ratio_avg),
    throughput_drop_ratio_p95=VALUES(throughput_drop_ratio_p95),
    throughput_drop_ratio_max=VALUES(throughput_drop_ratio_max),
    freshness_delay_sec_p50=VALUES(freshness_delay_sec_p50),
    freshness_delay_sec_p95=VALUES(freshness_delay_sec_p95),
    freshness_delay_sec_max=VALUES(freshness_delay_sec_max),
    consumer_lag_p50=VALUES(consumer_lag_p50),
    consumer_lag_p95=VALUES(consumer_lag_p95),
    consumer_lag_max=VALUES(consumer_lag_max),
    backlog_size_avg=VALUES(backlog_size_avg),
    backlog_size_p95=VALUES(backlog_size_p95),
    backlog_size_max=VALUES(backlog_size_max),
    recovery_sec_avg=VALUES(recovery_sec_avg),
    recovery_sec_max=VALUES(recovery_sec_max),
    degraded_minute_count=VALUES(degraded_minute_count),
    severe_minute_count=VALUES(severe_minute_count),
    metric_version=VALUES(metric_version)
"""

execute(conn, stream_sql, [args.dt_from, args.dt_to, args.profile_id])
execute(conn, batch_sql, [args.profile_id, args.dt_from, args.dt_to, args.profile_id, args.dt_from, args.dt_to])
conn.commit()
conn.close()
print('[DONE] pipeline_performance_summary_day built (v2 stream+batch)')
