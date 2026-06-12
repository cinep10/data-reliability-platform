-- Active source_gen_run guard checks

SELECT
  dt,
  profile_id,
  scenario_id,
  scenario_name,
  source_generation_scenario,
  source_gen_run_id,
  COUNT(*) cnt
FROM stg_webserver_log_hit
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-21'
GROUP BY
  dt, profile_id, scenario_id, scenario_name, source_generation_scenario, source_gen_run_id
ORDER BY source_gen_run_id;

SELECT
  source_gen_run_id,
  COUNT(*) cnt
FROM stg_webserver_log_hit
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-21'
  AND scenario_name='source_identity_drift'
GROUP BY source_gen_run_id;

SELECT 'stg_webserver_log_hit' table_name, source_gen_run_id, COUNT(*) cnt
FROM stg_webserver_log_hit
WHERE profile_id='commerce_deliver' AND dt='2026-05-21'
GROUP BY source_gen_run_id
UNION ALL
SELECT 'stg_wc_log_hit', source_gen_run_id, COUNT(*) cnt
FROM stg_wc_log_hit
WHERE profile_id='commerce_deliver' AND dt='2026-05-21'
GROUP BY source_gen_run_id
UNION ALL
SELECT 'event_log_raw', source_gen_run_id, COUNT(*) cnt
FROM event_log_raw
WHERE profile_id='commerce_deliver' AND dt='2026-05-21'
GROUP BY source_gen_run_id
UNION ALL
SELECT 'canonical_events', source_gen_run_id, COUNT(*) cnt
FROM canonical_events
WHERE profile_id='commerce_deliver' AND dt='2026-05-21'
GROUP BY source_gen_run_id;
