-- v0.5 7-day calibration tuning review SQL

SELECT
  target_date,
  scenario_name,
  calibration_mode,
  calibration_result,
  expected_semantic_family,
  COALESCE(observed_semantic, observed_semantic_family, 'None') AS observed_semantic,
  expected_action,
  COALESCE(observed_action, 'None') AS observed_action,
  observed_risk_level,
  ROUND(observed_risk_score, 6) AS observed_risk_score,
  review_reason
FROM v05_semantic_action_calibration_review_day
WHERE profile_id='commerce_deliver'
  AND target_date BETWEEN '2026-05-21' AND '2026-05-27'
ORDER BY target_date, scenario_name;

SELECT
  scenario_name,
  calibration_result,
  COUNT(*) AS cnt
FROM v05_semantic_action_calibration_review_day
WHERE profile_id='commerce_deliver'
  AND target_date BETWEEN '2026-05-21' AND '2026-05-27'
GROUP BY scenario_name, calibration_result
ORDER BY scenario_name, calibration_result;

SELECT
  calibration_result,
  COUNT(*) AS cnt
FROM v05_semantic_action_calibration_review_day
WHERE profile_id='commerce_deliver'
  AND target_date BETWEEN '2026-05-21' AND '2026-05-27'
GROUP BY calibration_result
ORDER BY calibration_result;
