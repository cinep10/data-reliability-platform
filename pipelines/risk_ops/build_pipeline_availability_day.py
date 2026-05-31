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
    execute(conn, 'DELETE FROM pipeline_availability_day WHERE dt BETWEEN %s AND %s AND pipeline_name=%s', [args.dt_from, args.dt_to, args.profile_id])

sql = """
INSERT INTO pipeline_availability_day (
    dt, pipeline_name, entity_scope, processing_mode, runtime_mode,
    run_count, success_run_count, failed_run_count, partial_run_count, timeout_run_count,
    success_rate, no_data_interval_sec_sum, no_data_interval_sec_max,
    downtime_sec_sum, downtime_sec_max, recovery_sec_avg, recovery_sec_max,
    availability_ratio, zero_output_run_count, metric_version
)
SELECT
    dt, pipeline_name, entity_scope, processing_mode, runtime_mode,
    COUNT(*) AS run_count,
    SUM(CASE WHEN run_status='success' THEN 1 ELSE 0 END),
    SUM(CASE WHEN run_status='failed' THEN 1 ELSE 0 END),
    SUM(CASE WHEN run_status='partial' THEN 1 ELSE 0 END),
    SUM(CASE WHEN run_status='timeout' THEN 1 ELSE 0 END),
    AVG(CASE WHEN run_success_flag=1 THEN 1.0 ELSE 0.0 END) AS success_rate,
    SUM(COALESCE(no_data_interval_sec,0)), MAX(no_data_interval_sec),
    SUM(COALESCE(downtime_sec,0)), MAX(downtime_sec),
    AVG(recovery_sec), MAX(recovery_sec),
    GREATEST(0, 1 - (SUM(COALESCE(downtime_sec,0)) / 86400.0)) AS availability_ratio,
    SUM(CASE WHEN COALESCE(output_count,0)=0 THEN 1 ELSE 0 END),
    'v1'
FROM pipeline_availability_run
WHERE dt BETWEEN %s AND %s AND pipeline_name=%s
GROUP BY dt, pipeline_name, entity_scope, processing_mode, runtime_mode
ON DUPLICATE KEY UPDATE
    run_count=VALUES(run_count),
    success_run_count=VALUES(success_run_count),
    failed_run_count=VALUES(failed_run_count),
    partial_run_count=VALUES(partial_run_count),
    timeout_run_count=VALUES(timeout_run_count),
    success_rate=VALUES(success_rate),
    no_data_interval_sec_sum=VALUES(no_data_interval_sec_sum),
    no_data_interval_sec_max=VALUES(no_data_interval_sec_max),
    downtime_sec_sum=VALUES(downtime_sec_sum),
    downtime_sec_max=VALUES(downtime_sec_max),
    recovery_sec_avg=VALUES(recovery_sec_avg),
    recovery_sec_max=VALUES(recovery_sec_max),
    availability_ratio=VALUES(availability_ratio),
    zero_output_run_count=VALUES(zero_output_run_count),
    metric_version=VALUES(metric_version)
"""
execute(conn, sql, [args.dt_from, args.dt_to, args.profile_id])
conn.commit()
conn.close()
print('[DONE] pipeline_availability_day built')
