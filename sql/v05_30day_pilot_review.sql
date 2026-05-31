-- v0.5 30-day pilot calendar-aware review SQL
-- Adjust date range/profile as needed.

-- 1. Calendar table can be loaded from configs/commerce/v05_30day_pilot_scenario_calendar.csv if desired.
-- Recommended ad-hoc review joins are by profile_id + target_date/dt + scenario_name.

-- 2. Artifact coverage by scenario/date
SELECT
  c.target_date,
  c.scenario_name,
  COALESCE(si.cnt,0) AS semantic_rows,
  COALESCE(ur.cnt,0) AS risk_rows,
  COALESCE(ar.cnt,0) AS action_rows,
  COALESCE(ml.cnt,0) AS ml_rows,
  COALESCE(ai.cnt,0) AS ai_score_rows
FROM (
  SELECT '2026-05-21' AS target_date, 'baseline' AS scenario_name
  -- Replace this CTE with a loaded calendar table for full SQL-only review.
) c
LEFT JOIN (
  SELECT target_date, scenario_name, COUNT(*) cnt
  FROM semantic_interpretation_day_v05
  WHERE profile_id='commerce_deliver'
  GROUP BY target_date, scenario_name
) si ON si.target_date=c.target_date AND si.scenario_name=c.scenario_name
LEFT JOIN (
  SELECT target_date, scenario_name, COUNT(*) cnt
  FROM unified_reliability_score_day_v05
  WHERE profile_id='commerce_deliver'
  GROUP BY target_date, scenario_name
) ur ON ur.target_date=c.target_date AND ur.scenario_name=c.scenario_name
LEFT JOIN (
  SELECT target_date, scenario_name, COUNT(*) cnt
  FROM action_recommendation_day_v05
  WHERE profile_id='commerce_deliver'
  GROUP BY target_date, scenario_name
) ar ON ar.target_date=c.target_date AND ar.scenario_name=c.scenario_name
LEFT JOIN (
  SELECT target_date, scenario_name, COUNT(*) cnt
  FROM v05_ml_feature_snapshot_day
  WHERE profile_id='commerce_deliver'
  GROUP BY target_date, scenario_name
) ml ON ml.target_date=c.target_date AND ml.scenario_name=c.scenario_name
LEFT JOIN (
  SELECT target_date, scenario_name, COUNT(*) cnt
  FROM v05_ai_reliability_score_day
  WHERE profile_id='commerce_deliver'
  GROUP BY target_date, scenario_name
) ai ON ai.target_date=c.target_date AND ai.scenario_name=c.scenario_name;

-- 3. Risk/semantic/action distribution after pilot
SELECT
  s.target_date,
  s.scenario_name,
  s.final_risk_level,
  s.overall_risk_score,
  s.dominant_semantic_risk,
  a.recommended_action
FROM unified_reliability_score_day_v05 s
LEFT JOIN action_recommendation_day_v05 a
  ON a.profile_id=s.profile_id
 AND a.target_date=s.target_date
 AND a.scenario_name=s.scenario_name
WHERE s.profile_id='commerce_deliver'
  AND s.target_date BETWEEN '2026-05-21' AND '2026-06-19'
ORDER BY s.target_date, s.scenario_name;

-- 4. AI validation policy check
SELECT
  v.target_date,
  v.scenario_name,
  v.validation_status,
  r.ai_reliability_level,
  r.ai_reliability_score,
  CASE
    WHEN v.validation_status IN ('PASS','OK') THEN 'PASS'
    WHEN v.validation_status='FAIL' AND r.ai_reliability_level='review' THEN 'PASS_WITH_REVIEW'
    ELSE 'CHECK'
  END AS pilot_ai_policy_result
FROM v05_ai_validation_result_day v
LEFT JOIN v05_ai_reliability_score_day r
  ON r.profile_id=v.profile_id
 AND r.target_date=v.target_date
 AND r.scenario_name=v.scenario_name
WHERE v.profile_id='commerce_deliver'
  AND v.target_date BETWEEN '2026-05-21' AND '2026-06-19'
ORDER BY v.target_date, v.scenario_name;

-- 5. SourceGen active guard check
SELECT
  dt,
  profile_id,
  scenario_name,
  COUNT(DISTINCT source_gen_run_id) AS source_gen_run_count,
  GROUP_CONCAT(DISTINCT source_gen_run_id ORDER BY source_gen_run_id) AS source_gen_run_ids,
  COUNT(*) AS rows_cnt
FROM stg_webserver_log_hit
WHERE profile_id='commerce_deliver'
  AND dt BETWEEN '2026-05-21' AND '2026-06-19'
GROUP BY dt, profile_id, scenario_name
HAVING COUNT(DISTINCT source_gen_run_id) > 1;
