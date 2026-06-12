-- v0.5 action baseline no-false-action review SQL

SELECT
  s.target_date,
  s.scenario_name,
  s.run_id,
  s.dominant_semantic_risk,
  u.final_risk_level,
  u.overall_risk_score,
  u.runtime_evidence_weight,
  COUNT(a.action_type) AS action_count,
  GROUP_CONCAT(a.recommended_action ORDER BY a.action_rank SEPARATOR ' | ') AS actions
FROM semantic_interpretation_day_v05 s
JOIN unified_reliability_score_day_v05 u
  ON u.profile_id=s.profile_id
 AND u.target_date=s.target_date
 AND u.scenario_name=s.scenario_name
 AND u.run_id=s.run_id
LEFT JOIN action_recommendation_day_v05 a
  ON a.profile_id=s.profile_id
 AND a.target_date=s.target_date
 AND a.scenario_name=s.scenario_name
 AND a.run_id=s.run_id
WHERE s.profile_id='commerce_deliver'
  AND s.target_date='2026-05-21'
  AND s.scenario_name='baseline'
GROUP BY
  s.target_date, s.scenario_name, s.run_id,
  s.dominant_semantic_risk, u.final_risk_level, u.overall_risk_score, u.runtime_evidence_weight
ORDER BY s.run_id DESC
LIMIT 10;
