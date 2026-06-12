-- v0.5 source anomaly trace final compatibility patch
-- Purpose:
--   Ensure v05_source_anomaly_trace_day supports row-level source anomaly evidence.
--   Compatible with current table shown in DBeaver:
--   profile_id, target_date, dt, run_id, source_gen_run_id, scenario_name,
--   anomaly_mode, runtime_layer, source_layer, anomaly_type, ..., trace_id, anomaly_seq ...
--
-- Policy:
--   This is a measurement persistence table for source-level anomaly trace.
--   It is safe to truncate during test/runtime reset.

CREATE TABLE IF NOT EXISTS v05_source_anomaly_trace_day (
  profile_id VARCHAR(64) NOT NULL,
  target_date DATE NOT NULL,
  dt DATE NULL,
  run_id BIGINT NOT NULL DEFAULT 0,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  scenario_name VARCHAR(128) NOT NULL,
  anomaly_mode VARCHAR(128) NOT NULL,
  runtime_layer VARCHAR(64) NULL,
  source_layer VARCHAR(64) NULL,
  anomaly_type VARCHAR(128) NULL,
  affected_count BIGINT DEFAULT 0,
  total_count BIGINT DEFAULT 0,
  affected_ratio DECIMAL(18,10) DEFAULT 0,
  evidence_key VARCHAR(128) NULL,
  evidence_value VARCHAR(512) NULL,
  trace_file VARCHAR(1024) NULL,
  trace_json LONGTEXT NULL,
  behavior_log_path TEXT NULL,
  original_count BIGINT DEFAULT 0,
  final_count BIGINT DEFAULT 0,
  batch_marker_count BIGINT DEFAULT 0,
  stream_marker_count BIGINT DEFAULT 0,
  operational_marker_count BIGINT DEFAULT 0,
  shifted_hour_count BIGINT DEFAULT 0,
  promo_shadow_count BIGINT DEFAULT 0,
  duplicated_count BIGINT DEFAULT 0,
  dropped_count BIGINT DEFAULT 0,
  reordered_count BIGINT DEFAULT 0,
  stream_delay_marker_count BIGINT DEFAULT 0,
  operational_5xx_count BIGINT DEFAULT 0,
  operational_timeout_marker_count BIGINT DEFAULT 0,
  anomaly_trace_json LONGTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  trace_id VARCHAR(512) NOT NULL,
  anomaly_seq BIGINT NOT NULL DEFAULT 1,
  affected_rows BIGINT DEFAULT 0,
  evidence_count BIGINT DEFAULT 0,
  anomaly_score DECIMAL(18,10) DEFAULT 0,
  PRIMARY KEY (trace_id, anomaly_seq),
  KEY idx_v05_source_trace_lookup (profile_id, target_date, scenario_name, run_id, source_gen_run_id),
  KEY idx_v05_source_trace_layer (profile_id, target_date, scenario_name, runtime_layer)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @db := DATABASE();

-- Add missing columns defensively.
SET @sql := IF((SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='trace_id')=0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN trace_id VARCHAR(512) NULL',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='anomaly_seq')=0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_seq BIGINT NOT NULL DEFAULT 1',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='affected_rows')=0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN affected_rows BIGINT DEFAULT 0',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='evidence_count')=0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN evidence_count BIGINT DEFAULT 0',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='anomaly_score')=0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_score DECIMAL(18,10) DEFAULT 0',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='anomaly_trace_json')=0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_trace_json LONGTEXT NULL',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Current failed state has trace_id NOT NULL but loader did not populate it.
-- Normalize table as runtime evidence: truncate, backfill DDL, then enforce composite PK.
TRUNCATE TABLE v05_source_anomaly_trace_day;

-- Make trace_id nullable briefly to allow PK rebuild if needed.
ALTER TABLE v05_source_anomaly_trace_day MODIFY COLUMN trace_id VARCHAR(512) NULL;

-- Drop current primary key if any.
SET @pk_exists := (
  SELECT COUNT(*)
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA=@db
    AND TABLE_NAME='v05_source_anomaly_trace_day'
    AND CONSTRAINT_TYPE='PRIMARY KEY'
);
SET @sql := IF(@pk_exists > 0, 'ALTER TABLE v05_source_anomaly_trace_day DROP PRIMARY KEY', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Final desired nullability and PK.
ALTER TABLE v05_source_anomaly_trace_day MODIFY COLUMN trace_id VARCHAR(512) NOT NULL;
ALTER TABLE v05_source_anomaly_trace_day MODIFY COLUMN anomaly_seq BIGINT NOT NULL DEFAULT 1;
ALTER TABLE v05_source_anomaly_trace_day ADD PRIMARY KEY (trace_id, anomaly_seq);

-- Helpful indexes; ignore duplicate errors by checking first.
SET @idx_exists := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA=@db AND TABLE_NAME='v05_source_anomaly_trace_day' AND INDEX_NAME='idx_v05_source_trace_lookup'
);
SET @sql := IF(@idx_exists=0,
  'CREATE INDEX idx_v05_source_trace_lookup ON v05_source_anomaly_trace_day(profile_id, target_date, scenario_name, run_id, source_gen_run_id)',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx_exists := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA=@db AND TABLE_NAME='v05_source_anomaly_trace_day' AND INDEX_NAME='idx_v05_source_trace_layer'
);
SET @sql := IF(@idx_exists=0,
  'CREATE INDEX idx_v05_source_trace_layer ON v05_source_anomaly_trace_day(profile_id, target_date, scenario_name, runtime_layer)',
  'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SELECT 'OK v05_source_anomaly_trace_day final patch applied' AS status;
