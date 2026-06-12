-- 055_v05_build_batch_behavior_distribution_measurement_mariadb.sql
-- This SQL expects session variables:
-- @profile_id, @dt, @run_id, @source_gen_run_id, @scenario_name
-- It materializes distribution measurement from stg_event_batch.
-- SQL responsibility: measurement materialization only.

DELETE FROM batch_behavior_distribution_day
WHERE profile_id=@profile_id
  AND dt=@dt
  AND run_id=@run_id
  AND scenario_name=@scenario_name;

INSERT INTO batch_behavior_distribution_day (
  profile_id, dt, run_id, source_gen_run_id, scenario_name,
  dimension_name, dimension_value, event_count, total_event_count, ratio_value
)
SELECT
  profile_id,
  dt,
  @run_id AS run_id,
  @source_gen_run_id AS source_gen_run_id,
  @scenario_name AS scenario_name,
  dimension_name,
  dimension_value,
  event_count,
  total_event_count,
  CASE WHEN total_event_count > 0 THEN event_count / total_event_count ELSE 0 END AS ratio_value
FROM (
  SELECT profile_id, dt, 'event_name' AS dimension_name,
         COALESCE(NULLIF(event_name,''), 'unknown') AS dimension_value,
         COUNT(*) AS event_count,
         SUM(COUNT(*)) OVER (PARTITION BY profile_id, dt) AS total_event_count
  FROM stg_event_batch
  WHERE profile_id=@profile_id AND dt=@dt
  GROUP BY profile_id, dt, COALESCE(NULLIF(event_name,''), 'unknown')

  UNION ALL

  SELECT profile_id, dt, 'page_type' AS dimension_name,
         COALESCE(NULLIF(page_type,''), 'unknown') AS dimension_value,
         COUNT(*) AS event_count,
         SUM(COUNT(*)) OVER (PARTITION BY profile_id, dt) AS total_event_count
  FROM stg_event_batch
  WHERE profile_id=@profile_id AND dt=@dt
  GROUP BY profile_id, dt, COALESCE(NULLIF(page_type,''), 'unknown')

  UNION ALL

  SELECT profile_id, dt, 'channel' AS dimension_name,
         COALESCE(NULLIF(channel,''), 'unknown') AS dimension_value,
         COUNT(*) AS event_count,
         SUM(COUNT(*)) OVER (PARTITION BY profile_id, dt) AS total_event_count
  FROM stg_event_batch
  WHERE profile_id=@profile_id AND dt=@dt
  GROUP BY profile_id, dt, COALESCE(NULLIF(channel,''), 'unknown')

  UNION ALL

  SELECT profile_id, dt, 'device_type' AS dimension_name,
         COALESCE(NULLIF(device_type,''), 'unknown') AS dimension_value,
         COUNT(*) AS event_count,
         SUM(COUNT(*)) OVER (PARTITION BY profile_id, dt) AS total_event_count
  FROM stg_event_batch
  WHERE profile_id=@profile_id AND dt=@dt
  GROUP BY profile_id, dt, COALESCE(NULLIF(device_type,''), 'unknown')

  UNION ALL

  SELECT profile_id, dt, 'hour' AS dimension_name,
         LPAD(CAST(HOUR(event_time) AS CHAR), 2, '0') AS dimension_value,
         COUNT(*) AS event_count,
         SUM(COUNT(*)) OVER (PARTITION BY profile_id, dt) AS total_event_count
  FROM stg_event_batch
  WHERE profile_id=@profile_id AND dt=@dt
  GROUP BY profile_id, dt, LPAD(CAST(HOUR(event_time) AS CHAR), 2, '0')
) d;

-- Bring v0.4 unmapped suggestions into v0.5 review workflow, without auto-approval.
INSERT INTO event_mapping_suggestion_review (
  profile_id, dt, suggestion_id, url_pattern, suggested_event_name,
  suggested_page_type, evidence_count, review_status, source_table
)
SELECT
  profile_id,
  dt,
  MD5(CONCAT(profile_id, '|', dt, '|', COALESCE(url_pattern,''), '|', COALESCE(suggested_event_name,''))) AS suggestion_id,
  url_pattern,
  suggested_event_name,
  suggested_page_type,
  COALESCE(evidence_count, 0) AS evidence_count,
  'pending' AS review_status,
  'event_mapping_suggestion' AS source_table
FROM event_mapping_suggestion
WHERE profile_id=@profile_id
  AND dt=@dt
ON DUPLICATE KEY UPDATE
  evidence_count=VALUES(evidence_count),
  suggested_event_name=VALUES(suggested_event_name),
  suggested_page_type=VALUES(suggested_page_type);
