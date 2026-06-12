-- v0.5 semantic/action calibration review table
CREATE TABLE IF NOT EXISTS v05_semantic_action_calibration_review_day (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  profile_id VARCHAR(100) NOT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(100) NOT NULL,
  run_id BIGINT NULL,
  source_gen_run_id BIGINT NULL,

  expected_semantic_family VARCHAR(255) NULL,
  observed_semantic VARCHAR(255) NULL,
  observed_semantic_family VARCHAR(255) NULL,

  expected_action VARCHAR(500) NULL,
  observed_action VARCHAR(500) NULL,

  expected_escalation VARCHAR(100) NULL,
  observed_risk_level VARCHAR(100) NULL,
  observed_risk_score DOUBLE NULL,

  calibration_mode VARCHAR(50) NOT NULL DEFAULT 'review',
  calibration_result VARCHAR(50) NOT NULL,
  review_reason TEXT NULL,

  semantic_match_flag TINYINT(1) NOT NULL DEFAULT 0,
  action_match_flag TINYINT(1) NOT NULL DEFAULT 0,
  artifact_missing_flag TINYINT(1) NOT NULL DEFAULT 0,

  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  KEY idx_v05_cal_review_date (profile_id, target_date),
  KEY idx_v05_cal_review_scenario (profile_id, scenario_name),
  KEY idx_v05_cal_review_result (calibration_result),
  KEY idx_v05_cal_review_run (profile_id, target_date, scenario_name, run_id, source_gen_run_id)
);
