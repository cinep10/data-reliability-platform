/*
Collection Reliability Evidence Query
- Edit the variables below before running.
- Usage:
  mysql -h 127.0.0.1 -P 3306 -u nethru -pnethru1234 weblog < scripts/query_collection_reliability_evidence.sql
*/

SET @profile_id := 'commerce_deliver';
SET @target_date := DATE('2026-05-18');
SET @scenario_name := 'baseline';
SET @run_id := NULL;              -- set to a numeric run_id when available
SET @source_gen_run_id := NULL;   -- set to a numeric source_gen_run_id when available

SELECT 'A_RUN_SCOPE' AS section,
       @profile_id AS profile_id,
       @target_date AS target_date,
       @scenario_name AS scenario_name,
       COALESCE(CAST(@run_id AS CHAR), 'ALL') AS run_id,
       COALESCE(CAST(@source_gen_run_id AS CHAR), 'ALL') AS source_gen_run_id;

/* 1) Source -> Stage -> Collector -> Raw -> Canonical count chain */
SELECT 'B_COUNT_CHAIN' AS section, 'raw_snapshot_manifest' AS asset, COUNT(*) AS cnt
FROM raw_snapshot_manifest
WHERE profile_id = @profile_id
  AND target_date = @target_date
  AND (@source_gen_run_id IS NULL OR source_gen_run_id = @source_gen_run_id)
UNION ALL
SELECT 'B_COUNT_CHAIN', 'stg_webserver_log_hit', COUNT(*)
FROM stg_webserver_log_hit
WHERE profile_id = @profile_id
  AND dt = @target_date
  AND (@source_gen_run_id IS NULL OR source_gen_run_id = @source_gen_run_id)
UNION ALL
SELECT 'B_COUNT_CHAIN', 'stg_wc_log_hit', COUNT(*)
FROM stg_wc_log_hit
WHERE profile_id = @profile_id
  AND dt = @target_date
  AND (@source_gen_run_id IS NULL OR source_gen_run_id = @source_gen_run_id)
UNION ALL
SELECT 'B_COUNT_CHAIN', 'event_log_raw', COUNT(*)
FROM event_log_raw
WHERE profile_id = @profile_id
  AND dt = @target_date
  AND (@source_gen_run_id IS NULL OR source_gen_run_id = @source_gen_run_id)
UNION ALL
SELECT 'B_COUNT_CHAIN', 'canonical_events', COUNT(*)
FROM canonical_events
WHERE profile_id = @profile_id
  AND target_date = @target_date
  AND (@run_id IS NULL OR run_id = @run_id)
  AND (@source_gen_run_id IS NULL OR source_gen_run_id = @source_gen_run_id)
UNION ALL
SELECT 'B_COUNT_CHAIN', 'measurement_batch_day', COUNT(*)
FROM measurement_batch_day
WHERE profile_id = @profile_id
  AND dt = @target_date
  AND (@run_id IS NULL OR run_id = CAST(@run_id AS CHAR))
UNION ALL
SELECT 'B_COUNT_CHAIN', 'measurement_stream_day', COUNT(*)
FROM measurement_stream_day
WHERE profile_id = @profile_id
  AND dt = @target_date
  AND (@run_id IS NULL OR run_id = CAST(@run_id AS CHAR))
UNION ALL
SELECT 'B_COUNT_CHAIN', 'measurement_operational_day', COUNT(*)
FROM measurement_operational_day
WHERE profile_id = @profile_id
  AND dt = @target_date
  AND (@run_id IS NULL OR run_id = CAST(@run_id AS CHAR))
UNION ALL
SELECT 'B_COUNT_CHAIN', 'measurement_realism_day', COUNT(*)
FROM measurement_realism_day
WHERE profile_id = @profile_id
  AND dt = @target_date
  AND (@run_id IS NULL OR run_id = CAST(@run_id AS CHAR));

/* 2) Collector loss/duplication indicators */
SELECT 'C_COLLECTOR_DELTA' AS section,
       src.stage_count,
       wc.collector_count,
       raw.raw_event_count,
       ce.canonical_event_count,
       (src.stage_count - wc.collector_count) AS stage_to_collector_delta,
       CASE WHEN src.stage_count = 0 THEN NULL ELSE ROUND((src.stage_count - wc.collector_count) / src.stage_count, 6) END AS estimated_collector_drop_rate,
       CASE WHEN src.stage_count = 0 THEN NULL ELSE ROUND((wc.collector_count - src.stage_count) / src.stage_count, 6) END AS estimated_collector_dup_rate
FROM
  (SELECT COUNT(*) AS stage_count FROM stg_webserver_log_hit WHERE profile_id=@profile_id AND dt=@target_date AND (@source_gen_run_id IS NULL OR source_gen_run_id=@source_gen_run_id)) src
CROSS JOIN
  (SELECT COUNT(*) AS collector_count FROM stg_wc_log_hit WHERE profile_id=@profile_id AND dt=@target_date AND (@source_gen_run_id IS NULL OR source_gen_run_id=@source_gen_run_id)) wc
CROSS JOIN
  (SELECT COUNT(*) AS raw_event_count FROM event_log_raw WHERE profile_id=@profile_id AND dt=@target_date AND (@source_gen_run_id IS NULL OR source_gen_run_id=@source_gen_run_id)) raw
CROSS JOIN
  (SELECT COUNT(*) AS canonical_event_count FROM canonical_events WHERE profile_id=@profile_id AND target_date=@target_date AND (@run_id IS NULL OR run_id=@run_id) AND (@source_gen_run_id IS NULL OR source_gen_run_id=@source_gen_run_id)) ce;

/* 3) Canonical coverage: schema and identity */
SELECT 'D_CANONICAL_COVERAGE' AS section,
       COUNT(*) AS canonical_event_count,
       ROUND(AVG(CASE WHEN uid IS NOT NULL AND uid <> '' THEN 1 ELSE 0 END), 6) AS uid_coverage,
       ROUND(AVG(CASE WHEN pcid IS NOT NULL AND pcid <> '' THEN 1 ELSE 0 END), 6) AS pcid_coverage,
       ROUND(AVG(CASE WHEN session_id IS NOT NULL AND session_id <> '' THEN 1 ELSE 0 END), 6) AS session_id_coverage,
       ROUND(AVG(CASE WHEN schema_version IS NOT NULL AND schema_version <> '' THEN 1 ELSE 0 END), 6) AS schema_version_coverage,
       SUM(CASE WHEN schema_flag IS NOT NULL AND schema_flag <> '' THEN 1 ELSE 0 END) AS schema_flag_count,
       SUM(CASE WHEN identity_flag IS NOT NULL AND identity_flag <> '' THEN 1 ELSE 0 END) AS identity_flag_count
FROM canonical_events
WHERE profile_id = @profile_id
  AND target_date = @target_date
  AND (@run_id IS NULL OR run_id = @run_id)
  AND (@source_gen_run_id IS NULL OR source_gen_run_id = @source_gen_run_id);

/* 4) Measurement day outputs */
SELECT 'E_BATCH_MEASUREMENT' AS section, profile_id, dt, run_id, scenario_name,
       event_count, session_count, semantic_event_count, semantic_event_coverage,
       schema_version_coverage, uid_coverage, pcid_coverage,
       funnel_start_count, funnel_submit_count, conversion_rate
FROM measurement_batch_day
WHERE profile_id = @profile_id AND dt = @target_date AND (@run_id IS NULL OR run_id = CAST(@run_id AS CHAR));

SELECT 'F_STREAM_MEASUREMENT' AS section, profile_id, dt, run_id, scenario_name,
       stream_event_count, duplicate_count, duplicate_rate,
       ordering_error_count, ordering_error_rate,
       latency_p50_ms, latency_p95_ms, latency_max_ms,
       completeness_rate, throughput_per_minute
FROM measurement_stream_day
WHERE profile_id = @profile_id AND dt = @target_date AND (@run_id IS NULL OR run_id = CAST(@run_id AS CHAR));

SELECT 'G_OPERATIONAL_MEASUREMENT' AS section, profile_id, dt, run_id, scenario_name,
       processed_count, throughput_per_minute,
       lag_p50_ms, lag_p95_ms, lag_max_ms,
       availability_ratio, no_data_gap_minutes, timeout_count, retry_count
FROM measurement_operational_day
WHERE profile_id = @profile_id AND dt = @target_date AND (@run_id IS NULL OR run_id = CAST(@run_id AS CHAR));

SELECT 'H_REALISM_MEASUREMENT' AS section, profile_id, dt, run_id, scenario_name,
       source_event_count, canonical_event_count, batch_event_count, stream_event_count, replay_event_count,
       source_to_canonical_drop_ratio, canonical_to_batch_drop_ratio, canonical_to_stream_drop_ratio,
       canonical_to_replay_drop_ratio,
       direct_completeness_delta, direct_timeliness_delta, direct_availability_delta, direct_integrity_delta,
       measurement_realism_status, realism_reason
FROM measurement_realism_day
WHERE profile_id = @profile_id AND dt = @target_date AND (@run_id IS NULL OR run_id = CAST(@run_id AS CHAR));

/* 5) Stream primitive detail */
SELECT 'I_STREAM_DUPLICATE_DETAIL' AS section,
       COUNT(*) AS minute_rows,
       SUM(total_count) AS total_count,
       SUM(duplicate_count) AS duplicate_count,
       CASE WHEN SUM(total_count)=0 THEN NULL ELSE ROUND(SUM(duplicate_count)/SUM(total_count), 6) END AS weighted_duplicate_ratio
FROM stream_duplicate_result
WHERE profile_id = @profile_id AND DATE(metric_minute) = @target_date;

SELECT 'J_STREAM_LATENCY_DETAIL' AS section,
       COUNT(*) AS minute_rows,
       ROUND(AVG(avg_event_delay_ms), 3) AS avg_delay_ms,
       ROUND(MAX(p95_event_delay_ms), 3) AS max_p95_delay_ms,
       SUM(sla_breach_count) AS sla_breach_count
FROM stream_latency_result
WHERE profile_id = @profile_id AND DATE(metric_minute) = @target_date;

SELECT 'K_STREAM_COMPLETENESS_DETAIL' AS section,
       COUNT(*) AS minute_rows,
       SUM(expected_count) AS expected_count,
       SUM(actual_count) AS actual_count,
       SUM(missing_count) AS missing_count,
       CASE WHEN SUM(expected_count)=0 THEN NULL ELSE ROUND(SUM(missing_count)/SUM(expected_count), 6) END AS weighted_missing_rate
FROM stream_completeness_result
WHERE profile_id = @profile_id AND DATE(metric_minute) = @target_date;

/* 6) Scenario/anomaly traceability */
SELECT 'L_ANOMALY_TRACE' AS section,
       COALESCE(anomaly_type, 'NULL') AS anomaly_type,
       COALESCE(schema_flag, 'NULL') AS schema_flag,
       COALESCE(identity_flag, 'NULL') AS identity_flag,
       COUNT(*) AS canonical_event_count
FROM canonical_events
WHERE profile_id = @profile_id
  AND target_date = @target_date
  AND (@run_id IS NULL OR run_id = @run_id)
  AND (@source_gen_run_id IS NULL OR source_gen_run_id = @source_gen_run_id)
GROUP BY COALESCE(anomaly_type, 'NULL'), COALESCE(schema_flag, 'NULL'), COALESCE(identity_flag, 'NULL')
ORDER BY canonical_event_count DESC;
