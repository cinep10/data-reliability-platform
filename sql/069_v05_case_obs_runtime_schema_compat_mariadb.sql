
-- v0.5 CASE-OBS baseline/distribution schema compatibility patch.
-- Safe to run repeatedly.

CREATE TABLE IF NOT EXISTS v05_batch_behavior_distribution_compare_day (
  compare_id BIGINT NOT NULL AUTO_INCREMENT,
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  run_id BIGINT NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  baseline_mode VARCHAR(64) DEFAULT 'temporal_baseline',
  baseline_window VARCHAR(32) DEFAULT '30d',
  dimension_name VARCHAR(128) NOT NULL,
  dimension_value VARCHAR(255) NOT NULL,
  current_count BIGINT DEFAULT 0,
  current_ratio DOUBLE DEFAULT 0,
  baseline_count_avg DOUBLE DEFAULT NULL,
  baseline_ratio_avg DOUBLE DEFAULT NULL,
  baseline_ratio_std DOUBLE DEFAULT NULL,
  ratio_delta DOUBLE DEFAULT NULL,
  z_score DOUBLE DEFAULT NULL,
  distribution_shift_score DOUBLE DEFAULT 0,
  baseline_status VARCHAR(64) DEFAULT 'BASELINE_MISSING_REVIEW',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(compare_id),
  KEY idx_v05_dist_cmp_run(profile_id,dt,run_id,scenario_name),
  KEY idx_v05_dist_cmp_dim(profile_id,dt,baseline_window,dimension_name,dimension_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @db := DATABASE();
SET @tbl := 'v05_batch_behavior_distribution_compare_day';

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db AND table_name=@tbl AND column_name='baseline_ratio_std')=0,
  'ALTER TABLE v05_batch_behavior_distribution_compare_day ADD COLUMN baseline_ratio_std DOUBLE DEFAULT NULL AFTER baseline_ratio_avg',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db AND table_name=@tbl AND column_name='distribution_shift_score')=0,
  'ALTER TABLE v05_batch_behavior_distribution_compare_day ADD COLUMN distribution_shift_score DOUBLE DEFAULT 0 AFTER z_score',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db AND table_name=@tbl AND column_name='baseline_status')=0,
  'ALTER TABLE v05_batch_behavior_distribution_compare_day ADD COLUMN baseline_status VARCHAR(64) DEFAULT ''BASELINE_MISSING_REVIEW'' AFTER distribution_shift_score',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS r_metric_time_pattern_anomaly_day (
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  run_id VARCHAR(128) NOT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  metric_name VARCHAR(255) NOT NULL,
  grain VARCHAR(32) NOT NULL DEFAULT 'day',
  observed_value DOUBLE DEFAULT 0,
  baseline_value DOUBLE DEFAULT 0,
  baseline_sd DOUBLE DEFAULT 0,
  z_score DOUBLE DEFAULT 0,
  delta_value DOUBLE DEFAULT 0,
  delta_ratio DOUBLE DEFAULT 0,
  anomaly_score DOUBLE DEFAULT 0,
  anomaly_status VARCHAR(32) DEFAULT 'PASS',
  analysis_reason TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(profile_id,dt,run_id,metric_name,grain)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

