-- CASE-OBS-001 Phase2-C4: Baseline Science Statistical Evidence Interface
-- SQL = persistence only.
-- Purpose: expose baseline-aware statistical evidence to v0.4 batch analytics,
-- OBS analytics, and v0.5 reconciliation reliability analytics without coupling
-- those domains to each other.

CREATE TABLE IF NOT EXISTS v05_baseline_science_statistical_evidence_day (
  profile_id VARCHAR(64) NOT NULL,
  target_date DATE NOT NULL,
  dt DATE NULL,
  scenario_name VARCHAR(64) NOT NULL DEFAULT 'baseline',
  run_id BIGINT NOT NULL DEFAULT 0,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  baseline_window VARCHAR(32) NOT NULL DEFAULT '30d',
  baseline_scenario_name VARCHAR(64) NOT NULL DEFAULT 'baseline',

  evidence_domain VARCHAR(48) NOT NULL,
  evidence_source_table VARCHAR(128) NOT NULL,
  evidence_metric_name VARCHAR(96) NOT NULL,

  dimension_type VARCHAR(48) NOT NULL DEFAULT 'all',
  dimension_key VARCHAR(191) NOT NULL DEFAULT 'all',
  metric_name VARCHAR(96) NOT NULL,

  current_value DOUBLE NULL,
  baseline_mean DOUBLE NULL,
  baseline_sd DOUBLE NULL,
  baseline_delta DOUBLE NULL,
  baseline_delta_rate DOUBLE NULL,

  z_score DOUBLE NULL,
  historical_percentile DOUBLE NULL,
  control_limit_lower DOUBLE NULL,
  control_limit_upper DOUBLE NULL,
  control_limit_breach TINYINT NOT NULL DEFAULT 0,

  expected_value DOUBLE NULL,
  expected_delta DOUBLE NULL,
  expected_delta_rate DOUBLE NULL,
  watch_threshold DOUBLE NULL,
  warning_threshold DOUBLE NULL,
  critical_threshold DOUBLE NULL,
  threshold_band VARCHAR(32) NOT NULL DEFAULT 'none',

  affected_metrics INT NOT NULL DEFAULT 0,
  co_movement_score DOUBLE NOT NULL DEFAULT 0,
  co_movement_level VARCHAR(32) NOT NULL DEFAULT 'none',
  statistical_score DOUBLE NOT NULL DEFAULT 0,
  statistical_significance VARCHAR(32) NOT NULL DEFAULT 'stable',

  baseline_quality_score DOUBLE NOT NULL DEFAULT 0,
  sample_days INT NOT NULL DEFAULT 0,
  baseline_status VARCHAR(64) NOT NULL DEFAULT 'unknown',
  analysis_status VARCHAR(64) NOT NULL DEFAULT 'PASS',
  analysis_summary VARCHAR(1024) NULL,
  detail_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(detail_json)),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (
    profile_id, target_date, scenario_name, run_id, source_gen_run_id,
    baseline_window, evidence_domain, dimension_type, dimension_key, metric_name
  ),
  KEY idx_v05_bssed_domain (profile_id, target_date, scenario_name, evidence_domain),
  KEY idx_v05_bssed_metric (profile_id, target_date, dimension_type, metric_name),
  KEY idx_v05_bssed_score (profile_id, target_date, statistical_significance, statistical_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE v05_batch_metric_delta_day
  ADD COLUMN IF NOT EXISTS historical_percentile DOUBLE DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS control_limit_lower DOUBLE DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS control_limit_upper DOUBLE DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS control_limit_breach TINYINT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS statistical_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS statistical_significance VARCHAR(32) DEFAULT 'stable',
  ADD COLUMN IF NOT EXISTS baseline_quality_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS co_movement_score DOUBLE DEFAULT 0;

ALTER TABLE r_batch_behavior_analysis_day
  ADD COLUMN IF NOT EXISTS statistical_evidence_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_z_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_historical_percentile DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS control_limit_breach_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS co_movement_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS statistical_significance VARCHAR(32) DEFAULT 'stable';

ALTER TABLE r_batch_distribution_analysis_day
  ADD COLUMN IF NOT EXISTS statistical_evidence_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_z_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_historical_percentile DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS control_limit_breach_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS co_movement_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS statistical_significance VARCHAR(32) DEFAULT 'stable';

ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS statistical_evidence_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_z_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_historical_percentile DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS control_limit_breach_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS co_movement_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS statistical_significance VARCHAR(32) DEFAULT 'stable';

ALTER TABLE r_v05_observability_analysis_day
  ADD COLUMN IF NOT EXISTS statistical_evidence_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_z_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_historical_percentile DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS control_limit_breach_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS co_movement_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS statistical_significance VARCHAR(32) DEFAULT 'stable';

ALTER TABLE reliability_analysis_result_day_v05
  ADD COLUMN IF NOT EXISTS statistical_evidence_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_z_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_historical_percentile DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS control_limit_breach_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS co_movement_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS statistical_significance VARCHAR(32) DEFAULT 'stable';
