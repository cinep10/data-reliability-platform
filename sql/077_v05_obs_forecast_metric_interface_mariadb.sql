-- CASE-OBS-001 Phase2-C3-B: Forecast Interface
-- Interface-only table. Actual ML forecasting is intentionally deferred.

CREATE TABLE IF NOT EXISTS v05_obs_forecast_metric_day (
  profile_id VARCHAR(64) NOT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  run_id BIGINT NOT NULL,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  baseline_window VARCHAR(32) NOT NULL DEFAULT '30d',
  baseline_scenario VARCHAR(128) NOT NULL DEFAULT 'baseline',

  dimension_type VARCHAR(64) NOT NULL,
  dimension_key VARCHAR(191) NOT NULL DEFAULT 'all',
  metric_name VARCHAR(128) NOT NULL,

  forecast_model_name VARCHAR(128) NOT NULL DEFAULT 'interface_only',
  forecast_model_version VARCHAR(64) NOT NULL DEFAULT 'forecast_interface_v1',
  forecast_value DOUBLE NULL,
  forecast_lower DOUBLE NULL,
  forecast_upper DOUBLE NULL,
  forecast_confidence DOUBLE NOT NULL DEFAULT 0,

  training_window VARCHAR(32) NOT NULL DEFAULT 'none',
  training_sample_days INT NOT NULL DEFAULT 0,
  feature_window VARCHAR(32) NOT NULL DEFAULT 'none',

  model_status VARCHAR(64) NOT NULL DEFAULT 'interface_only',
  quality_status VARCHAR(64) NOT NULL DEFAULT 'not_trained',
  notes VARCHAR(512) NULL,

  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window, dimension_type, dimension_key, metric_name),
  KEY idx_v05_obs_forecast_lookup (profile_id, target_date, scenario_name, dimension_type, metric_name),
  KEY idx_v05_obs_forecast_status (profile_id, target_date, model_status, quality_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
