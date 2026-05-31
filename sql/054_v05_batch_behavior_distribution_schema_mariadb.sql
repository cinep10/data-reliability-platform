-- v0.5 batch distribution/anomaly schema fix v2
-- Purpose: make existing partial tables compatible with v0.5 batch currentization.
-- Language responsibility: SQL = persistence/schema only.

CREATE TABLE IF NOT EXISTS batch_behavior_distribution_day (
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  run_id BIGINT NOT NULL,
  source_gen_run_id BIGINT NULL,
  scenario_name VARCHAR(128) NULL,
  dimension_name VARCHAR(64) NOT NULL,
  dimension_value VARCHAR(255) NOT NULL,
  event_count BIGINT NOT NULL DEFAULT 0,
  total_event_count BIGINT NOT NULL DEFAULT 0,
  ratio_value DECIMAL(18,10) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (profile_id, dt, run_id, dimension_name, dimension_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE batch_behavior_distribution_day ADD COLUMN IF NOT EXISTS source_gen_run_id BIGINT NULL AFTER run_id;
ALTER TABLE batch_behavior_distribution_day ADD COLUMN IF NOT EXISTS scenario_name VARCHAR(128) NULL AFTER source_gen_run_id;
ALTER TABLE batch_behavior_distribution_day ADD COLUMN IF NOT EXISTS event_count BIGINT NOT NULL DEFAULT 0 AFTER dimension_value;
ALTER TABLE batch_behavior_distribution_day ADD COLUMN IF NOT EXISTS total_event_count BIGINT NOT NULL DEFAULT 0 AFTER event_count;
ALTER TABLE batch_behavior_distribution_day ADD COLUMN IF NOT EXISTS ratio_value DECIMAL(18,10) NOT NULL DEFAULT 0 AFTER total_event_count;
ALTER TABLE batch_behavior_distribution_day ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS r_batch_distribution_analysis_day (
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  run_id BIGINT NOT NULL,
  source_gen_run_id BIGINT NULL,
  scenario_name VARCHAR(128) NULL,
  dimension_name VARCHAR(64) NOT NULL,
  js_divergence DECIMAL(18,10) NOT NULL DEFAULT 0,
  kl_divergence DECIMAL(18,10) NOT NULL DEFAULT 0,
  entropy_delta DECIMAL(18,10) NOT NULL DEFAULT 0,
  max_ratio_delta DECIMAL(18,10) NOT NULL DEFAULT 0,
  dominant_distribution_value VARCHAR(255) NULL,
  distribution_risk_score DECIMAL(18,10) NOT NULL DEFAULT 0,
  analysis_status VARCHAR(32) NOT NULL DEFAULT 'PASS',
  analysis_reason TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (profile_id, dt, run_id, dimension_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS source_gen_run_id BIGINT NULL AFTER run_id;
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS scenario_name VARCHAR(128) NULL AFTER source_gen_run_id;
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS js_divergence DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS kl_divergence DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS entropy_delta DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS max_ratio_delta DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS dominant_distribution_value VARCHAR(255) NULL;
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS distribution_risk_score DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS analysis_status VARCHAR(32) NOT NULL DEFAULT 'PASS';
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS analysis_reason TEXT NULL;
ALTER TABLE r_batch_distribution_analysis_day ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS batch_behavior_anomaly_day (
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  run_id BIGINT NOT NULL,
  source_gen_run_id BIGINT NULL,
  scenario_name VARCHAR(128) NULL,
  traffic_pattern_score DECIMAL(18,10) NOT NULL DEFAULT 0,
  channel_imbalance_score DECIMAL(18,10) NOT NULL DEFAULT 0,
  session_fragmentation_score DECIMAL(18,10) NOT NULL DEFAULT 0,
  identity_anomaly_score DECIMAL(18,10) NOT NULL DEFAULT 0,
  conversion_distortion_score DECIMAL(18,10) NOT NULL DEFAULT 0,
  mapping_anomaly_score DECIMAL(18,10) NOT NULL DEFAULT 0,
  distribution_distortion_score DECIMAL(18,10) NOT NULL DEFAULT 0,
  dominant_batch_anomaly VARCHAR(128) NULL,
  batch_anomaly_score DECIMAL(18,10) NOT NULL DEFAULT 0,
  anomaly_status VARCHAR(32) NOT NULL DEFAULT 'PASS',
  anomaly_reason TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (profile_id, dt, run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS source_gen_run_id BIGINT NULL AFTER run_id;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS scenario_name VARCHAR(128) NULL AFTER source_gen_run_id;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS traffic_pattern_score DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS channel_imbalance_score DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS session_fragmentation_score DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS identity_anomaly_score DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS conversion_distortion_score DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS mapping_anomaly_score DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS distribution_distortion_score DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS dominant_batch_anomaly VARCHAR(128) NULL;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS batch_anomaly_score DECIMAL(18,10) NOT NULL DEFAULT 0;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS anomaly_status VARCHAR(32) NOT NULL DEFAULT 'PASS';
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS anomaly_reason TEXT NULL;
ALTER TABLE batch_behavior_anomaly_day ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS event_mapping_suggestion_review (
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  suggestion_key VARCHAR(255) NOT NULL,
  suggestion_value VARCHAR(255) NULL,
  review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  reviewer VARCHAR(128) NULL,
  reviewed_at TIMESTAMP NULL,
  review_note TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (profile_id, dt, suggestion_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
