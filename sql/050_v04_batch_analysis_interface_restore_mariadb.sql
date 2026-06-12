-- v0.4 Batch Data Analysis Interface Restore
-- Purpose: restore v0.1 batch log-analysis assets into v0.4 Measurement -> R Analytics -> Risk/Action flow.

CREATE TABLE IF NOT EXISTS stg_ds_metric_hh (
  profile_id VARCHAR(64) NOT NULL,
  dt DATE NOT NULL,
  hh TINYINT NOT NULL,
  metric_nm VARCHAR(100) NOT NULL,
  metric_val DECIMAL(18,6) NOT NULL DEFAULT 0,
  note VARCHAR(255) NULL,
  PRIMARY KEY (profile_id, dt, hh, metric_nm),
  KEY idx_sdmh_profile_dt (profile_id, dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS stg_ds_metric_hh_wide (
  profile_id VARCHAR(64) NOT NULL,
  dt DATE NOT NULL,
  hh TINYINT NOT NULL,
  visit DECIMAL(18,6) NOT NULL DEFAULT 0,
  uv DECIMAL(18,6) NOT NULL DEFAULT 0,
  pageview DECIMAL(18,6) NOT NULL DEFAULT 0,
  note VARCHAR(255) NULL,
  PRIMARY KEY (profile_id, dt, hh),
  KEY idx_sdmhw_profile_dt (profile_id, dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS metric_value_hh (
  profile_id VARCHAR(64) NOT NULL,
  dt DATE NOT NULL,
  hh TINYINT NOT NULL,
  metric_name VARCHAR(100) NOT NULL,
  metric_group VARCHAR(50) NOT NULL,
  source_layer VARCHAR(50) NOT NULL,
  metric_value DECIMAL(18,6) NOT NULL DEFAULT 0,
  numerator_value DECIMAL(18,6) NULL,
  denominator_value DECIMAL(18,6) NULL,
  run_id VARCHAR(64) NULL,
  note VARCHAR(255) NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (profile_id, dt, hh, metric_name),
  KEY idx_mvh_profile_dt (profile_id, dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS metric_value_day (
  profile_id VARCHAR(64) NOT NULL,
  dt DATE NOT NULL,
  metric_name VARCHAR(100) NOT NULL,
  metric_group VARCHAR(50) NOT NULL,
  source_layer VARCHAR(50) NOT NULL,
  metric_value DECIMAL(18,6) NOT NULL DEFAULT 0,
  numerator_value DECIMAL(18,6) NULL,
  denominator_value DECIMAL(18,6) NULL,
  run_id VARCHAR(64) NULL,
  note VARCHAR(255) NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (profile_id, dt, metric_name),
  KEY idx_mvd_profile_dt (profile_id, dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS event_mapping_suggestion (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  profile_id VARCHAR(128) NOT NULL DEFAULT '',
  dt DATE NULL,
  suggested_pattern VARCHAR(500) NOT NULL,
  suggested_event_name VARCHAR(100) NOT NULL,
  suggested_event_type VARCHAR(50) DEFAULT 'page',
  suggested_funnel_stage VARCHAR(50) DEFAULT 'view',
  suggested_funnel_order INT DEFAULT 0,
  total_hits BIGINT DEFAULT 0,
  url_count BIGINT DEFAULT 0,
  review_status VARCHAR(20) DEFAULT 'pending',
  reviewed_by VARCHAR(100) DEFAULT NULL,
  reviewed_at TIMESTAMP NULL DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_ems_profile_dt_pattern (profile_id, dt, suggested_pattern),
  KEY idx_ems_review (review_status, total_hits)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS batch_behavior_measurement_day (
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  run_id VARCHAR(128) NOT NULL DEFAULT '',
  scenario_name VARCHAR(128) NOT NULL DEFAULT '',
  -- canonical wide interface from stg_ds_metric_hh_wide
  visit DOUBLE DEFAULT 0,
  uv DOUBLE DEFAULT 0,
  pv DOUBLE DEFAULT 0,
  pageview DOUBLE DEFAULT 0,
  -- raw metric interface from metric_value_day and stg_ds_metric_hh
  event_count BIGINT DEFAULT 0,
  batch_event_count BIGINT DEFAULT 0,
  raw_event_count BIGINT DEFAULT 0,
  collector_event_count BIGINT DEFAULT 0,
  estimated_missing_rate DOUBLE DEFAULT 0,
  avg_session_duration_sec DOUBLE DEFAULT 0,
  new_user_ratio DOUBLE DEFAULT 0,
  session_count BIGINT DEFAULT 0,
  -- generic behavior/funnel interface
  funnel_start_count BIGINT DEFAULT 0,
  funnel_submit_count BIGINT DEFAULT 0,
  conversion_rate DOUBLE DEFAULT 0,
  auth_attempt_count BIGINT DEFAULT 0,
  auth_success_count BIGINT DEFAULT 0,
  auth_fail_count BIGINT DEFAULT 0,
  auth_success_rate DOUBLE DEFAULT 0,
  auth_fail_rate DOUBLE DEFAULT 0,
  -- quality/mapping interface
  mapping_coverage DOUBLE DEFAULT 0,
  unmapped_event_count BIGINT DEFAULT 0,
  mapping_suggestion_count BIGINT DEFAULT 0,
  validation_fail_count BIGINT DEFAULT 0,
  quality_issue_count BIGINT DEFAULT 0,
  other_event_count BIGINT DEFAULT 0,
  -- derived normalized indicators for R
  pv_per_uv DOUBLE DEFAULT 0,
  visit_per_uv DOUBLE DEFAULT 0,
  pv_per_visit DOUBLE DEFAULT 0,
  session_fragmentation_ratio DOUBLE DEFAULT 0,
  collector_capture_rate DOUBLE DEFAULT 0,
  metric_json JSON NULL,
  quality_json JSON NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY(profile_id, dt, run_id),
  KEY idx_bbm_profile_dt (profile_id, dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS r_batch_behavior_analysis_day (
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  run_id VARCHAR(128) NOT NULL DEFAULT '',
  scenario_name VARCHAR(128) NOT NULL DEFAULT '',
  behavior_distortion_score DOUBLE DEFAULT 0,
  channel_imbalance_score DOUBLE DEFAULT 0,
  session_fragmentation_score DOUBLE DEFAULT 0,
  conversion_distortion_score DOUBLE DEFAULT 0,
  identity_anomaly_score DOUBLE DEFAULT 0,
  mapping_risk_score DOUBLE DEFAULT 0,
  batch_quality_risk_score DOUBLE DEFAULT 0,
  batch_overall_analysis_score DOUBLE DEFAULT 0,
  dominant_batch_signal VARCHAR(128) DEFAULT 'none',
  analysis_status VARCHAR(32) DEFAULT 'PASS',
  analysis_reason TEXT,
  detail_json JSON NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY(profile_id, dt, run_id),
  KEY idx_rbba_profile_dt (profile_id, dt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Extend v0.4 Phase3 measurement interface while preserving original columns.
ALTER TABLE measurement_batch_day
  ADD COLUMN IF NOT EXISTS uv_count BIGINT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS pv_count BIGINT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS visit_count BIGINT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS pageview_count BIGINT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS mapping_coverage DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS unmapped_event_count BIGINT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS validation_fail_count BIGINT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS quality_issue_count BIGINT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS estimated_missing_rate DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS collector_capture_rate DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS batch_measurement_source VARCHAR(128) DEFAULT 'stg_ds_metric_hh_wide';
