SELECT target_date, scenario_name, review_status, expected_semantic_family, observed_semantic_family, expected_action, observed_action, observed_risk_level
FROM v05_semantic_action_calibration_review_day
WHERE profile_id='commerce_deliver'
ORDER BY target_date DESC, scenario_name
LIMIT 100;

SELECT review_status, COUNT(*) cnt
FROM v05_semantic_action_calibration_review_day
WHERE profile_id='commerce_deliver'
GROUP BY review_status;
