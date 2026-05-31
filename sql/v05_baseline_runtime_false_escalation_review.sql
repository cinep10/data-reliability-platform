-- v0.5 baseline runtime false escalation review SQL

SELECT
  target_date,
  scenario_name,
  run_id,
  source_gen_run_id,
  dominant_semantic_risk,
  runtime_semantic_score,
  dominant_runtime_signal,
  JSON_UNQUOTE(JSON_EXTRACT(semantic_payload_json, '$.runtime_evidence_interface.runtime_evidence_score')) AS payload_runtime_evidence_score
FROM semantic_interpretation_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-21'
  AND scenario_name='baseline'
ORDER BY run_id DESC
LIMIT 10;

SELECT
  target_date,
  scenario_name,
  run_id,
  overall_risk_score,
  final_risk_level,
  runtime_evidence_weight,
  dominant_runtime_signal
FROM unified_reliability_score_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-21'
  AND scenario_name='baseline'
ORDER BY run_id DESC
LIMIT 10;

SELECT
  target_date,
  scenario_name,
  run_id,
  recommended_action,
  action_priority
FROM action_recommendation_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-21'
  AND scenario_name='baseline'
ORDER BY run_id DESC, action_priority DESC
LIMIT 10;
