CREATE TABLE IF NOT EXISTS v05_batch_metric_delta_day (
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  run_id BIGINT NOT NULL DEFAULT 0,
  source_gen_run_id BIGINT DEFAULT NULL,
  scenario_name VARCHAR(128) NOT NULL DEFAULT 'baseline',
  baseline_mode VARCHAR(64) NOT NULL DEFAULT 'temporal_baseline',
  baseline_window VARCHAR(32) NOT NULL DEFAULT '30d',
  metric_scope VARCHAR(128) NOT NULL,
  metric_name VARCHAR(128) NOT NULL,
  current_value DOUBLE DEFAULT NULL,
  baseline_value_avg DOUBLE DEFAULT NULL,
  baseline_value_std DOUBLE DEFAULT NULL,
  absolute_delta DOUBLE DEFAULT NULL,
  delta_rate DOUBLE DEFAULT NULL,
  z_score DOUBLE DEFAULT NULL,
  risk_score DOUBLE DEFAULT NULL,
  risk_status VARCHAR(64) DEFAULT 'PASS',
  baseline_status VARCHAR(64) DEFAULT 'baseline_available',
  source_table VARCHAR(128) DEFAULT NULL,
  analysis_reason VARCHAR(1024) DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY(profile_id, dt, run_id, scenario_name, metric_scope, metric_name),
  KEY idx_v05_bmd_scenario(profile_id, dt, scenario_name),
  KEY idx_v05_bmd_run(profile_id, dt, run_id, source_gen_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE measurement_batch_day ADD COLUMN IF NOT EXISTS web_event_count BIGINT DEFAULT NULL;
ALTER TABLE measurement_batch_day ADD COLUMN IF NOT EXISTS wc_event_count BIGINT DEFAULT NULL;
ALTER TABLE measurement_batch_day ADD COLUMN IF NOT EXISTS canonical_event_count BIGINT DEFAULT NULL;
ALTER TABLE measurement_batch_day ADD COLUMN IF NOT EXISTS wc_missing_count BIGINT DEFAULT NULL;
ALTER TABLE measurement_batch_day ADD COLUMN IF NOT EXISTS wc_missing_rate DOUBLE DEFAULT NULL;
ALTER TABLE measurement_batch_day ADD COLUMN IF NOT EXISTS canonical_missing_count BIGINT DEFAULT NULL;
ALTER TABLE measurement_batch_day ADD COLUMN IF NOT EXISTS canonical_missing_rate DOUBLE DEFAULT NULL;
ALTER TABLE batch_behavior_measurement_day ADD COLUMN IF NOT EXISTS web_event_count BIGINT DEFAULT NULL;
ALTER TABLE batch_behavior_measurement_day ADD COLUMN IF NOT EXISTS wc_event_count BIGINT DEFAULT NULL;
ALTER TABLE batch_behavior_measurement_day ADD COLUMN IF NOT EXISTS canonical_event_count BIGINT DEFAULT NULL;
ALTER TABLE batch_behavior_measurement_day ADD COLUMN IF NOT EXISTS wc_missing_count BIGINT DEFAULT NULL;
ALTER TABLE batch_behavior_measurement_day ADD COLUMN IF NOT EXISTS wc_missing_rate DOUBLE DEFAULT NULL;
ALTER TABLE batch_behavior_measurement_day ADD COLUMN IF NOT EXISTS canonical_missing_count BIGINT DEFAULT NULL;
ALTER TABLE batch_behavior_measurement_day ADD COLUMN IF NOT EXISTS canonical_missing_rate DOUBLE DEFAULT NULL;
