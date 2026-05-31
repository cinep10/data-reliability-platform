CREATE TABLE IF NOT EXISTS v05_batch_behavior_distribution_compare_day (
  profile_id VARCHAR(96) NOT NULL,
  dt DATE NOT NULL,
  run_id BIGINT NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  baseline_mode VARCHAR(48) NOT NULL DEFAULT 'temporal_baseline',
  baseline_window VARCHAR(24) NOT NULL DEFAULT '30d',
  dimension_name VARCHAR(96) NOT NULL,
  dimension_value VARCHAR(191) NOT NULL,
  current_count DOUBLE DEFAULT 0,
  current_ratio DOUBLE DEFAULT 0,
  baseline_count_avg DOUBLE DEFAULT NULL,
  baseline_ratio_avg DOUBLE DEFAULT NULL,
  baseline_ratio_std DOUBLE DEFAULT NULL,
  ratio_delta DOUBLE DEFAULT NULL,
  z_score DOUBLE DEFAULT NULL,
  distribution_shift_score DOUBLE DEFAULT NULL,
  baseline_status VARCHAR(64) DEFAULT 'unknown',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(profile_id,dt,run_id,scenario_name,dimension_name,dimension_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
ALTER TABLE v05_batch_behavior_distribution_compare_day ADD COLUMN IF NOT EXISTS baseline_ratio_std DOUBLE DEFAULT NULL;
