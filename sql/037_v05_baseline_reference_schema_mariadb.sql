-- v0.5 Baseline Reference Layer
-- IMPORTANT: reset scripts must preserve these baseline reference tables by default.

CREATE TABLE IF NOT EXISTS v05_baseline_metric_snapshot_day (
  profile_id VARCHAR(100) NOT NULL,
  target_date DATE NOT NULL,
  baseline_window VARCHAR(20) NOT NULL DEFAULT '30d',
  baseline_type VARCHAR(50) NOT NULL DEFAULT 'calendar_baseline',
  metric_scope VARCHAR(100) NOT NULL,
  metric_name VARCHAR(100) NOT NULL,
  dimension_key VARCHAR(100) NOT NULL DEFAULT 'all',
  dimension_value VARCHAR(255) NOT NULL DEFAULT 'all',
  metric_value_avg DECIMAL(24,10) NULL,
  metric_value_std DECIMAL(24,10) NULL,
  metric_value_p50 DECIMAL(24,10) NULL,
  metric_value_p95 DECIMAL(24,10) NULL,
  metric_value_p99 DECIMAL(24,10) NULL,
  sample_days INT NOT NULL DEFAULT 0,
  source_scenario VARCHAR(100) NOT NULL DEFAULT 'baseline',
  baseline_status VARCHAR(50) NOT NULL DEFAULT 'READY',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (profile_id,target_date,baseline_window,baseline_type,metric_scope,metric_name,dimension_key,dimension_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS v05_baseline_reference_resolution_day (
  profile_id VARCHAR(100) NOT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(100) NOT NULL,
  run_id BIGINT NOT NULL DEFAULT 0,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  baseline_mode VARCHAR(50) NOT NULL,
  baseline_window VARCHAR(20) NOT NULL DEFAULT '30d',
  baseline_type VARCHAR(50) NOT NULL,
  baseline_available TINYINT NOT NULL DEFAULT 0,
  baseline_snapshot_date DATE NULL,
  fallback_policy VARCHAR(100) NOT NULL DEFAULT 'NO_CURRENT_FALLBACK_FOR_CASE_STUDY',
  resolution_status VARCHAR(50) NOT NULL DEFAULT 'BASELINE_MISSING_REVIEW',
  reason VARCHAR(1000) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (profile_id,target_date,scenario_name,run_id,source_gen_run_id,baseline_mode,baseline_window)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
