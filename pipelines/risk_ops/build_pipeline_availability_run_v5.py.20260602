import argparse
from db_utils import add_db_args, execute, get_connection

parser = argparse.ArgumentParser()
add_db_args(parser)
parser.add_argument('--profile-id', required=True)
parser.add_argument('--dt-from', required=True)
parser.add_argument('--dt-to', required=True)
parser.add_argument('--run-id', type=int, default=None)
parser.add_argument('--truncate-target', action='store_true')
args = parser.parse_args()

conn = get_connection(args)

if args.truncate_target:
    if args.run_id is None:
        execute(conn, 'DELETE FROM pipeline_availability_run WHERE dt BETWEEN %s AND %s AND pipeline_name=%s', [args.dt_from, args.dt_to, args.profile_id])
    else:
        execute(conn, 'DELETE FROM pipeline_availability_run WHERE dt BETWEEN %s AND %s AND pipeline_name=%s AND run_id=%s', [args.dt_from, args.dt_to, args.profile_id, args.run_id])

stream_params = [args.profile_id, args.dt_from, args.dt_to]
run_filter_stream = ''
run_filter_ce = ''
run_filter_b = ''
if args.run_id is not None:
    run_filter_stream = ' AND c.run_id = %s'
    run_filter_ce = ' AND run_id = %s'
    run_filter_b = ' AND b.run_id = %s'
    stream_params.append(args.run_id)

stream_sql = f"""
INSERT INTO pipeline_availability_run (
    run_id, dt, pipeline_name, entity_scope, processing_mode, runtime_mode, source_gen_run_id,
    run_start_ts, run_end_ts, run_status, run_success_flag,
    expected_input_count, observed_input_count, output_count,
    no_data_interval_sec, downtime_sec, recovery_sec,
    first_input_ts, last_input_ts, first_output_ts, last_output_ts,
    failure_reason_code, failure_stage, metric_version
)
WITH replay_rows AS (
    SELECT
        COALESCE(c.run_id, 0) AS run_id,
        c.target_date AS dt,
        c.profile_id AS pipeline_name,
        c.source_gen_run_id,
        c.event_time AS input_ts,
        r.replayed_at AS output_ts,
        r.replay_event_id,
        LAG(r.replayed_at) OVER (
            PARTITION BY c.profile_id, c.target_date, COALESCE(c.run_id, 0)
            ORDER BY r.replayed_at, r.replay_sequence, r.replay_event_id
        ) AS prev_output_ts
    FROM canonical_events c
    LEFT JOIN stream_replay_event r
      ON r.canonical_event_id = c.canonical_event_id
     AND r.profile_id = c.profile_id
     AND r.target_date = c.target_date
     AND COALESCE(r.run_id, 0) = COALESCE(c.run_id, 0)
    WHERE c.profile_id = %s
      AND c.target_date BETWEEN %s AND %s
      {run_filter_stream}
), gap_agg AS (
    SELECT
        run_id,
        dt,
        pipeline_name,
        MAX(source_gen_run_id) AS source_gen_run_id,
        MIN(output_ts) AS run_start_ts,
        MAX(output_ts) AS run_end_ts,
        COUNT(*) AS expected_input_count,
        SUM(CASE WHEN replay_event_id IS NOT NULL THEN 1 ELSE 0 END) AS output_count,
        SUM(CASE WHEN replay_event_id IS NOT NULL THEN 1 ELSE 0 END) AS observed_input_count,
        MIN(input_ts) AS first_input_ts,
        MAX(input_ts) AS last_input_ts,
        MIN(output_ts) AS first_output_ts,
        MAX(output_ts) AS last_output_ts,
        COALESCE(MAX(CASE WHEN prev_output_ts IS NULL OR output_ts IS NULL THEN 0 ELSE TIMESTAMPDIFF(SECOND, prev_output_ts, output_ts) END), 0) AS max_gap_sec,
        COALESCE(SUM(CASE WHEN prev_output_ts IS NULL OR output_ts IS NULL THEN 0 WHEN TIMESTAMPDIFF(SECOND, prev_output_ts, output_ts) > 5 THEN TIMESTAMPDIFF(SECOND, prev_output_ts, output_ts) - 5 ELSE 0 END), 0) AS downtime_sec
    FROM replay_rows
    GROUP BY run_id, dt, pipeline_name
)
SELECT
    run_id,
    dt,
    pipeline_name,
    'stream_replay_consumer' AS entity_scope,
    'stream' AS processing_mode,
    'replay' AS runtime_mode,
    source_gen_run_id,
    run_start_ts,
    run_end_ts,
    CASE
        WHEN output_count = expected_input_count THEN 'success'
        WHEN output_count = 0 THEN 'failed'
        ELSE 'partial'
    END AS run_status,
    CASE WHEN output_count = expected_input_count THEN 1 ELSE 0 END AS run_success_flag,
    expected_input_count,
    observed_input_count,
    output_count,
    CASE WHEN max_gap_sec > 5 THEN max_gap_sec ELSE 0 END AS no_data_interval_sec,
    downtime_sec,
    NULL AS recovery_sec,
    first_input_ts,
    last_input_ts,
    first_output_ts,
    last_output_ts,
    CASE WHEN output_count = 0 THEN 'no_replay_output'
         WHEN output_count < expected_input_count THEN 'partial_replay_output'
         ELSE NULL END AS failure_reason_code,
    CASE WHEN output_count = expected_input_count THEN NULL ELSE 'stream_replay_consumer' END AS failure_stage,
    'v5_replay_internal_gap' AS metric_version
FROM gap_agg
ON DUPLICATE KEY UPDATE
    source_gen_run_id=VALUES(source_gen_run_id),
    run_start_ts=VALUES(run_start_ts),
    run_end_ts=VALUES(run_end_ts),
    run_status=VALUES(run_status),
    run_success_flag=VALUES(run_success_flag),
    expected_input_count=VALUES(expected_input_count),
    observed_input_count=VALUES(observed_input_count),
    output_count=VALUES(output_count),
    no_data_interval_sec=VALUES(no_data_interval_sec),
    downtime_sec=VALUES(downtime_sec),
    recovery_sec=VALUES(recovery_sec),
    first_input_ts=VALUES(first_input_ts),
    last_input_ts=VALUES(last_input_ts),
    first_output_ts=VALUES(first_output_ts),
    last_output_ts=VALUES(last_output_ts),
    failure_reason_code=VALUES(failure_reason_code),
    failure_stage=VALUES(failure_stage),
    metric_version=VALUES(metric_version)
"""

batch_params = [args.profile_id, args.dt_from, args.dt_to, args.profile_id, args.dt_from, args.dt_to]
if args.run_id is not None:
    batch_params.extend([args.run_id, args.run_id])

batch_sql = f"""
INSERT INTO pipeline_availability_run (
    run_id, dt, pipeline_name, entity_scope, processing_mode, runtime_mode, source_gen_run_id,
    run_start_ts, run_end_ts, run_status, run_success_flag,
    expected_input_count, observed_input_count, output_count,
    no_data_interval_sec, downtime_sec, recovery_sec,
    first_input_ts, last_input_ts, first_output_ts, last_output_ts,
    failure_reason_code, failure_stage, metric_version
)
WITH ce AS (
    SELECT
        COALESCE(run_id, 0) AS run_id,
        target_date AS dt,
        profile_id AS pipeline_name,
        MAX(source_gen_run_id) AS source_gen_run_id,
        COUNT(*) AS expected_event_count,
        MIN(event_time) AS first_input_ts,
        MAX(event_time) AS last_input_ts
    FROM canonical_events
    WHERE profile_id = %s
      AND target_date BETWEEN %s AND %s
      {run_filter_ce}
    GROUP BY COALESCE(run_id, 0), target_date, profile_id
), bi AS (
    SELECT
        COALESCE(run_id, 0) AS run_id,
        target_date AS dt,
        profile_id AS pipeline_name,
        SUM(event_count) AS output_event_count,
        MIN(created_at) AS first_output_ts,
        MAX(created_at) AS last_output_ts,
        COUNT(*) AS batch_row_count,
        COALESCE(MAX(CASE WHEN prev_created_at IS NULL THEN 0 ELSE TIMESTAMPDIFF(SECOND, prev_created_at, created_at) END), 0) AS max_gap_sec,
        COALESCE(SUM(CASE WHEN prev_created_at IS NULL THEN 0 WHEN TIMESTAMPDIFF(SECOND, prev_created_at, created_at) > 5 THEN TIMESTAMPDIFF(SECOND, prev_created_at, created_at) - 5 ELSE 0 END), 0) AS downtime_sec
    FROM (
        SELECT
            b.*,
            LAG(created_at) OVER (PARTITION BY COALESCE(run_id, 0), target_date, profile_id ORDER BY created_at, batch_input_id) AS prev_created_at
        FROM batch_input_day b
        WHERE b.profile_id = %s
          AND b.target_date BETWEEN %s AND %s
          {run_filter_b}
    ) x
    GROUP BY COALESCE(run_id, 0), target_date, profile_id
)
SELECT
    ce.run_id,
    ce.dt,
    ce.pipeline_name,
    'batch_input_day_builder' AS entity_scope,
    'batch' AS processing_mode,
    'replay' AS runtime_mode,
    ce.source_gen_run_id,
    bi.first_output_ts AS run_start_ts,
    bi.last_output_ts AS run_end_ts,
    CASE
        WHEN COALESCE(bi.output_event_count, 0) = ce.expected_event_count THEN 'success'
        WHEN COALESCE(bi.output_event_count, 0) = 0 THEN 'failed'
        ELSE 'partial'
    END AS run_status,
    CASE WHEN COALESCE(bi.output_event_count, 0) = ce.expected_event_count THEN 1 ELSE 0 END AS run_success_flag,
    ce.expected_event_count AS expected_input_count,
    ce.expected_event_count AS observed_input_count,
    COALESCE(bi.output_event_count, 0) AS output_count,
    CASE WHEN COALESCE(bi.max_gap_sec, 0) > 5 THEN bi.max_gap_sec ELSE 0 END AS no_data_interval_sec,
    COALESCE(bi.downtime_sec, 0) AS downtime_sec,
    NULL AS recovery_sec,
    ce.first_input_ts,
    ce.last_input_ts,
    bi.first_output_ts,
    bi.last_output_ts,
    CASE WHEN COALESCE(bi.output_event_count, 0) = 0 THEN 'no_batch_output'
         WHEN COALESCE(bi.output_event_count, 0) < ce.expected_event_count THEN 'partial_batch_output'
         ELSE NULL END AS failure_reason_code,
    CASE WHEN COALESCE(bi.output_event_count, 0) = ce.expected_event_count THEN NULL ELSE 'batch_input_day_builder' END AS failure_stage,
    'v5_batch_internal_gap' AS metric_version
FROM ce
LEFT JOIN bi
  ON bi.run_id = ce.run_id
 AND bi.dt = ce.dt
 AND bi.pipeline_name = ce.pipeline_name
ON DUPLICATE KEY UPDATE
    source_gen_run_id=VALUES(source_gen_run_id),
    run_start_ts=VALUES(run_start_ts),
    run_end_ts=VALUES(run_end_ts),
    run_status=VALUES(run_status),
    run_success_flag=VALUES(run_success_flag),
    expected_input_count=VALUES(expected_input_count),
    observed_input_count=VALUES(observed_input_count),
    output_count=VALUES(output_count),
    no_data_interval_sec=VALUES(no_data_interval_sec),
    downtime_sec=VALUES(downtime_sec),
    recovery_sec=VALUES(recovery_sec),
    first_input_ts=VALUES(first_input_ts),
    last_input_ts=VALUES(last_input_ts),
    first_output_ts=VALUES(first_output_ts),
    last_output_ts=VALUES(last_output_ts),
    failure_reason_code=VALUES(failure_reason_code),
    failure_stage=VALUES(failure_stage),
    metric_version=VALUES(metric_version)
"""

execute(conn, stream_sql, stream_params)
execute(conn, batch_sql, batch_params)
conn.commit()
conn.close()
print('[DONE] pipeline_availability_run built (v5 replay-adjusted + batch)')
