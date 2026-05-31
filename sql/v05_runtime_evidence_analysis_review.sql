-- v0.5 runtime evidence interface review SQL

-- 1. Check new columns exist.
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema=DATABASE()
  AND table_name='reliability_analysis_result_day_v05'
  AND column_name IN (
    'runtime_evidence_score',
    'batch_evidence_score',
    'stream_evidence_score',
    'operational_evidence_score',
    'realism_evidence_score',
    'dominant_runtime_signal'
  )
ORDER BY column_name;

-- 2. Check latest analysis result with runtime evidence scores.
SELECT
  target_date,
  scenario_name,
  run_id,
  source_gen_run_id,
  ROUND(reconciliation_gap_score,6) AS reconciliation_gap_score,
  ROUND(runtime_evidence_score,6) AS runtime_evidence_score,
  ROUND(batch_evidence_score,6) AS batch_evidence_score,
  ROUND(stream_evidence_score,6) AS stream_evidence_score,
  ROUND(operational_evidence_score,6) AS operational_evidence_score,
  ROUND(realism_evidence_score,6) AS realism_evidence_score,
  dominant_runtime_signal,
  ROUND(baseline_delta,6) AS baseline_delta
FROM reliability_analysis_result_day_v05
WHERE profile_id='commerce_deliver'
ORDER BY target_date DESC, run_id DESC
LIMIT 20;

-- 3. Check runtime interface payload status.
SELECT
  target_date,
  scenario_name,
  JSON_UNQUOTE(JSON_EXTRACT(analysis_payload_json, '$.runtime_evidence_interface.status')) AS runtime_status,
  JSON_EXTRACT(analysis_payload_json, '$.runtime_evidence_interface.runtime_evidence_score') AS runtime_evidence_score,
  JSON_UNQUOTE(JSON_EXTRACT(analysis_payload_json, '$.runtime_evidence_interface.dominant_runtime_signal')) AS dominant_runtime_signal
FROM reliability_analysis_result_day_v05
WHERE profile_id='commerce_deliver'
ORDER BY target_date DESC, run_id DESC
LIMIT 20;
