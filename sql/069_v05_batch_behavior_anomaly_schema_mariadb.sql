-- v0.5 batch behavior anomaly schema
-- Purpose: R analytics output table for build_v05_batch_behavior_anomaly.R
-- This table is runtime evidence, not authoritative commerce risk by itself.

CREATE TABLE IF NOT EXISTS v05_batch_behavior_anomaly_day (
  profile_id VARCHAR(128) NOT NULL,
  dt DATE NOT NULL,
  run_id BIGINT NOT NULL,
  scenario_name VARCHAR(128) NOT NULL DEFAULT 'baseline',
  source_gen_run_id BIGINT DEFAULT NULL,

  anomaly_signal VARCHAR(128) DEFAULT 'none',
  anomaly_score DOUBLE DEFAULT 0,
  batch_distribution_risk_score DOUBLE DEFAULT 0,
  behavior_analysis_score DOUBLE DEFAULT 0,
  observability_collection_score DOUBLE DEFAULT 0,
  time_pattern_score DOUBLE DEFAULT 0,
  correlation_score DOUBLE DEFAULT 0,

  anomaly_status VARCHAR(64) DEFAULT 'PASS',
  baseline_mode VARCHAR(64) DEFAULT 'temporal_baseline',
  baseline_window VARCHAR(32) DEFAULT '30d',
  baseline_status VARCHAR(64) DEFAULT NULL,
  dominant_evidence_table VARCHAR(128) DEFAULT NULL,
  dominant_evidence_metric VARCHAR(128) DEFAULT NULL,
  evidence_summary VARCHAR(1024) DEFAULT NULL,
  payload_json JSON DEFAULT NULL,

  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (profile_id, dt, run_id, scenario_name),
  KEY idx_v05_bba_date (profile_id, dt),
  KEY idx_v05_bba_run (run_id),
  KEY idx_v05_bba_signal (anomaly_signal)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Compatibility ALTERs for older tables.
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS source_gen_run_id BIGINT DEFAULT NULL;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS batch_distribution_risk_score DOUBLE DEFAULT 0;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS behavior_analysis_score DOUBLE DEFAULT 0;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS observability_collection_score DOUBLE DEFAULT 0;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS time_pattern_score DOUBLE DEFAULT 0;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS correlation_score DOUBLE DEFAULT 0;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS baseline_mode VARCHAR(64) DEFAULT 'temporal_baseline';
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS baseline_window VARCHAR(32) DEFAULT '30d';
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS baseline_status VARCHAR(64) DEFAULT NULL;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS dominant_evidence_table VARCHAR(128) DEFAULT NULL;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS dominant_evidence_metric VARCHAR(128) DEFAULT NULL;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS evidence_summary VARCHAR(1024) DEFAULT NULL;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS payload_json JSON DEFAULT NULL;
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
