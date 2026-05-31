-- v0.5 source anomaly trace schema hotfix
CREATE TABLE IF NOT EXISTS v05_source_anomaly_trace_day (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  profile_id VARCHAR(128) NOT NULL,
  target_date DATE NOT NULL,
  dt DATE NULL,
  run_id BIGINT NULL,
  source_gen_run_id BIGINT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  anomaly_mode VARCHAR(128) NULL,
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
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='dt') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN dt DATE NULL AFTER target_date', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='runtime_layer') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN runtime_layer VARCHAR(64) NULL AFTER anomaly_mode', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='source_layer') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN source_layer VARCHAR(64) NULL AFTER runtime_layer', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='anomaly_type') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_type VARCHAR(128) NULL AFTER source_layer', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='affected_count') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN affected_count BIGINT DEFAULT 0 AFTER anomaly_type', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='total_count') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN total_count BIGINT DEFAULT 0 AFTER affected_count', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='affected_ratio') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN affected_ratio DECIMAL(18,10) DEFAULT 0 AFTER total_count', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='evidence_key') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN evidence_key VARCHAR(128) NULL AFTER affected_ratio', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='evidence_value') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN evidence_value VARCHAR(512) NULL AFTER evidence_key', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='trace_file') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN trace_file VARCHAR(1024) NULL AFTER evidence_value', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='v05_source_anomaly_trace_day' AND column_name='trace_json') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN trace_json LONGTEXT NULL AFTER trace_file', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
