-- v0.5 6-month backfill review SQL

-- 1. Artifact coverage in preserve mode: ML + AI score are required after cleanup.
SELECT
  c.target_date,
  c.scenario_name,
  COALESCE(ml.cnt,0) AS ml_rows,
  COALESCE(ai.cnt,0) AS ai_score_rows,
  CASE
    WHEN COALESCE(ml.cnt,0) > 0 AND COALESCE(ai.cnt,0) > 0 THEN 'PASS'
    ELSE 'FAIL'
  END AS preserve_artifact_result
FROM (
  SELECT target_date, scenario_name
  FROM v05_ml_feature_snapshot_day
  WHERE profile_id='commerce_deliver'
    AND target_date BETWEEN '2026-05-21' AND '2026-11-16'
  UNION
  SELECT target_date, scenario_name
  FROM v05_ai_reliability_score_day
  WHERE profile_id='commerce_deliver'
    AND target_date BETWEEN '2026-05-21' AND '2026-11-16'
) c
LEFT JOIN (
  SELECT target_date, scenario_name, COUNT(*) cnt
  FROM v05_ml_feature_snapshot_day
  WHERE profile_id='commerce_deliver'
    AND target_date BETWEEN '2026-05-21' AND '2026-11-16'
  GROUP BY target_date, scenario_name
) ml ON ml.target_date=c.target_date AND ml.scenario_name=c.scenario_name
LEFT JOIN (
  SELECT target_date, scenario_name, COUNT(*) cnt
  FROM v05_ai_reliability_score_day
  WHERE profile_id='commerce_deliver'
    AND target_date BETWEEN '2026-05-21' AND '2026-11-16'
  GROUP BY target_date, scenario_name
) ai ON ai.target_date=c.target_date AND ai.scenario_name=c.scenario_name
ORDER BY c.target_date, c.scenario_name;

-- 2. Calibration distribution.
SELECT
  scenario_name,
  final_risk_level,
  COALESCE(dominant_semantic_risk,'None') AS dominant_semantic_risk,
  COUNT(*) AS cnt,
  AVG(overall_risk_score) AS avg_risk_score
FROM v05_ml_feature_snapshot_day
WHERE profile_id='commerce_deliver'
  AND target_date BETWEEN '2026-05-21' AND '2026-11-16'
GROUP BY scenario_name, final_risk_level, COALESCE(dominant_semantic_risk,'None')
ORDER BY scenario_name, cnt DESC;

-- 3. AI PASS_WITH_REVIEW policy.
SELECT
  s.target_date,
  s.scenario_name,
  v.validation_status,
  s.ai_reliability_level,
  s.ai_reliability_score,
  CASE
    WHEN v.validation_status IN ('PASS','OK') THEN 'PASS'
    WHEN v.validation_status='FAIL' AND s.ai_reliability_level='review' THEN 'PASS_WITH_REVIEW'
    WHEN v.validation_status IS NULL AND s.ai_reliability_level IS NOT NULL THEN 'PASS_WITH_REVIEW'
    ELSE 'CHECK'
  END AS ai_policy_result
FROM v05_ai_reliability_score_day s
LEFT JOIN v05_ai_validation_result_day v
  ON v.profile_id=s.profile_id
 AND v.target_date=s.target_date
 AND v.scenario_name=s.scenario_name
WHERE s.profile_id='commerce_deliver'
  AND s.target_date BETWEEN '2026-05-21' AND '2026-11-16'
ORDER BY s.target_date, s.scenario_name;

-- 4. SourceGen accumulation guard: should return no rows.
SELECT
  dt,
  profile_id,
  scenario_name,
  COUNT(DISTINCT source_gen_run_id) AS source_gen_run_count,
  GROUP_CONCAT(DISTINCT source_gen_run_id ORDER BY source_gen_run_id) AS source_gen_run_ids,
  COUNT(*) AS rows_cnt
FROM stg_webserver_log_hit
WHERE profile_id='commerce_deliver'
  AND dt BETWEEN '2026-05-21' AND '2026-11-16'
GROUP BY dt, profile_id, scenario_name
HAVING COUNT(DISTINCT source_gen_run_id) > 1;
