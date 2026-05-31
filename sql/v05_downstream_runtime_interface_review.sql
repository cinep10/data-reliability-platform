-- v0.5 downstream runtime interface review SQL

SELECT column_name, column_type
FROM information_schema.columns
WHERE table_schema=DATABASE()
  AND table_name='semantic_interpretation_day_v05'
  AND column_name IN ('runtime_semantic_score','dominant_runtime_signal');

SELECT column_name, column_type
FROM information_schema.columns
WHERE table_schema=DATABASE()
  AND table_name='unified_reliability_score_day_v05'
  AND column_name IN ('runtime_evidence_weight','dominant_runtime_signal');

SELECT
  s.target_date,
  s.scenario_name,
  s.dominant_semantic_risk,
  s.runtime_semantic_score,
  s.dominant_runtime_signal AS semantic_runtime_signal,
  u.runtime_evidence_weight,
  u.dominant_runtime_signal AS score_runtime_signal,
  u.overall_risk_score,
  u.final_risk_level
FROM semantic_interpretation_day_v05 s
JOIN unified_reliability_score_day_v05 u
  ON u.profile_id=s.profile_id
 AND u.target_date=s.target_date
 AND u.scenario_name=s.scenario_name
 AND u.run_id=s.run_id
WHERE s.profile_id='commerce_deliver'
ORDER BY s.target_date DESC, s.run_id DESC
LIMIT 20;
