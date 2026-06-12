-- CASE-OBS-001 Phase2-C2 Expected Metric Model v1
-- SQL persistence only. R computes expected values and quality fields.

CREATE TABLE IF NOT EXISTS v05_obs_expected_metric_day (
  profile_id VARCHAR(64) NOT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  run_id BIGINT NOT NULL DEFAULT 0,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  baseline_window VARCHAR(32) NOT NULL DEFAULT '30d',
  baseline_scenario_name VARCHAR(128) NOT NULL DEFAULT 'baseline',

  dimension_type VARCHAR(64) NOT NULL,
  dimension_key VARCHAR(191) NOT NULL,
  metric_name VARCHAR(96) NOT NULL,

  current_value DOUBLE NULL,
  rolling_mean DOUBLE NULL,
  weekday_mean DOUBLE NULL,
  recent_7d_mean DOUBLE NULL,
  selected_baseline_mean DOUBLE NULL,

  expected_value DOUBLE NULL,
  expected_lower DOUBLE NULL,
  expected_upper DOUBLE NULL,
  expected_delta DOUBLE NULL,
  expected_delta_rate DOUBLE NULL,
  expected_breach TINYINT NOT NULL DEFAULT 0,

  rolling_sample_days INT NOT NULL DEFAULT 0,
  weekday_sample_days INT NOT NULL DEFAULT 0,
  recent_sample_days INT NOT NULL DEFAULT 0,
  selected_sample_days INT NOT NULL DEFAULT 0,

  baseline_quality_score DOUBLE NOT NULL DEFAULT 0,
  expected_confidence DOUBLE NOT NULL DEFAULT 0,
  model_status VARCHAR(32) NOT NULL DEFAULT 'unknown',
  quality_status VARCHAR(32) NOT NULL DEFAULT 'unknown',
  dimension_quality_status VARCHAR(32) NOT NULL DEFAULT 'unknown',

  expected_model_name VARCHAR(96) NOT NULL DEFAULT 'hybrid_expected_v1',
  expected_model_version VARCHAR(32) NOT NULL DEFAULT 'v1',
  source_table VARCHAR(128) NULL,
  detail_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (
    profile_id, target_date, scenario_name, run_id, source_gen_run_id,
    baseline_window, dimension_type, dimension_key, metric_name
  ),
  KEY idx_v05_obs_expected_lookup (profile_id, target_date, scenario_name, run_id, source_gen_run_id),
  KEY idx_v05_obs_expected_dim (profile_id, target_date, dimension_type, metric_name),
  KEY idx_v05_obs_expected_status (profile_id, target_date, model_status, quality_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
