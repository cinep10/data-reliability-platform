-- Scenario identity audit SQL examples

SELECT dt, profile_id, scenario_id, scenario_name, source_generation_scenario, source_gen_run_id, COUNT(*) AS cnt
FROM stg_webserver_log_hit
WHERE profile_id='commerce_deliver' AND dt='2026-05-21'
GROUP BY dt, profile_id, scenario_id, scenario_name, source_generation_scenario, source_gen_run_id;

-- SET @source_gen_run_id = 123;
-- SET @requested_scenario = 'source_identity_drift';
SELECT 'stg_webserver_log_hit' AS table_name, COUNT(*) AS mismatch_rows
FROM stg_webserver_log_hit
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-21'
  AND source_gen_run_id = @source_gen_run_id
  AND (scenario_name <> @requested_scenario OR scenario_id <> @requested_scenario);

SELECT 'canonical_events' AS table_name, scenario_name, source_gen_run_id, COUNT(*) cnt
FROM canonical_events
WHERE profile_id='commerce_deliver' AND dt='2026-05-21'
GROUP BY scenario_name, source_gen_run_id;

SELECT 'canonical_behavior_events' AS table_name, scenario_name, source_gen_run_id, COUNT(*) cnt
FROM canonical_behavior_events
WHERE profile_id='commerce_deliver' AND target_date='2026-05-21'
GROUP BY scenario_name, source_gen_run_id;
