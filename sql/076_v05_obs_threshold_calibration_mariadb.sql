-- CASE-OBS-001 Phase2-C3-A: Threshold Calibration
-- SQL = persistence only. R calculates calibration values.

CREATE TABLE IF NOT EXISTS v05_obs_threshold_calibration_day (
  profile_id VARCHAR(64) NOT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  run_id BIGINT NOT NULL,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  baseline_window VARCHAR(32) NOT NULL DEFAULT '30d',
  baseline_scenario VARCHAR(128) NOT NULL DEFAULT 'baseline',

  dimension_type VARCHAR(64) NOT NULL,
  metric_name VARCHAR(128) NOT NULL,

  sample_days INT NOT NULL DEFAULT 0,
  row_count INT NOT NULL DEFAULT 0,
  min_sample_count INT NOT NULL DEFAULT 0,
  quality_status VARCHAR(64) NOT NULL DEFAULT 'unknown',
  calibration_status VARCHAR(64) NOT NULL DEFAULT 'unknown',
  dimension_policy VARCHAR(64) NOT NULL DEFAULT 'default',

  mean_value DOUBLE NULL,
  sd_value DOUBLE NULL,
  p90_value DOUBLE NULL,
  p95_value DOUBLE NULL,
  p99_value DOUBLE NULL,

  watch_threshold DOUBLE NOT NULL DEFAULT 0,
  warning_threshold DOUBLE NOT NULL DEFAULT 0,
  critical_threshold DOUBLE NOT NULL DEFAULT 0,

  z_watch DOUBLE NOT NULL DEFAULT 2,
  z_warning DOUBLE NOT NULL DEFAULT 3,
  z_critical DOUBLE NOT NULL DEFAULT 5,

  delta_rate_watch DOUBLE NOT NULL DEFAULT 0.05,
  delta_rate_warning DOUBLE NOT NULL DEFAULT 0.10,
  delta_rate_critical DOUBLE NOT NULL DEFAULT 0.25,

  calibration_rule_version VARCHAR(64) NOT NULL DEFAULT 'obs_threshold_calibration_v1',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window, dimension_type, metric_name),
  KEY idx_v05_obs_threshold_lookup (profile_id, target_date, scenario_name, dimension_type, metric_name),
  KEY idx_v05_obs_threshold_status (profile_id, target_date, calibration_status, quality_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
