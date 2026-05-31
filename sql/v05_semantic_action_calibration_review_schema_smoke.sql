-- v0.5 semantic/action calibration review table schema smoke

SHOW COLUMNS FROM v05_semantic_action_calibration_review_day;

SELECT
  target_date,
  review_status,
  calibration_result,
  COUNT(*) AS cnt
FROM v05_semantic_action_calibration_review_day
WHERE profile_id='commerce_deliver'
GROUP BY target_date, review_status, calibration_result
ORDER BY target_date DESC, review_status;
