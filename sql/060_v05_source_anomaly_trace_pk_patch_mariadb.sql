-- 060_v05_source_anomaly_trace_pk_patch_mariadb.sql
-- v0.5 source anomaly trace PK patch
-- Purpose:
--   v05_source_anomaly_trace_day currently may use trace_id as a single-row PK.
--   Source anomaly trace is row-level evidence, so multiple rows can share one trace_id.
--   This patch changes row identity to (trace_id, anomaly_seq).
--
-- Safe to run multiple times on MariaDB.

-- 1) Ensure table exists with the expected baseline structure.
CREATE TABLE IF NOT EXISTS v05_source_anomaly_trace_day (
  profile_id VARCHAR(128) NOT NULL,
  target_date DATE NOT NULL,
  dt DATE NULL,
  run_id BIGINT NOT NULL DEFAULT 0,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  scenario_name VARCHAR(128) NOT NULL,
  trace_id VARCHAR(512) NOT NULL,
  anomaly_seq BIGINT NOT NULL DEFAULT 1,
  anomaly_mode VARCHAR(128) NULL,
  runtime_layer VARCHAR(64) NULL,
  anomaly_type VARCHAR(128) NULL,
  affected_rows BIGINT NULL DEFAULT 0,
  injected_rows BIGINT NULL DEFAULT 0,
  source_file VARCHAR(1024) NULL,
  trace_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (trace_id, anomaly_seq),
  KEY idx_v05_src_trace_lookup (profile_id, target_date, scenario_name, run_id, source_gen_run_id),
  KEY idx_v05_src_trace_layer (profile_id, target_date, scenario_name, runtime_layer)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) Add missing columns if the table already existed as a narrower schema.
SET @db_name := DATABASE();

SET @sql := IF(
  NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='anomaly_seq'
  ),
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_seq BIGINT NOT NULL DEFAULT 1 AFTER trace_id',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='dt'
  ),
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN dt DATE NULL AFTER target_date',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='runtime_layer'
  ),
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN runtime_layer VARCHAR(64) NULL AFTER anomaly_mode',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='anomaly_type'
  ),
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_type VARCHAR(128) NULL AFTER runtime_layer',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='affected_rows'
  ),
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN affected_rows BIGINT NULL DEFAULT 0 AFTER anomaly_type',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='injected_rows'
  ),
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN injected_rows BIGINT NULL DEFAULT 0 AFTER affected_rows',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='source_file'
  ),
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN source_file VARCHAR(1024) NULL AFTER injected_rows',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND COLUMN_NAME='trace_json'
  ),
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN trace_json JSON NULL AFTER source_file',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3) Backfill anomaly_seq for existing duplicate trace_id rows.
-- MariaDB supports user variables for deterministic sequence assignment.
SET @prev_trace_id := '';
SET @seq := 0;
UPDATE v05_source_anomaly_trace_day t
JOIN (
  SELECT
    trace_id,
    run_id,
    source_gen_run_id,
    scenario_name,
    @seq := IF(@prev_trace_id = trace_id, @seq + 1, 1) AS new_seq,
    @prev_trace_id := trace_id AS _assign_trace
  FROM v05_source_anomaly_trace_day
  ORDER BY trace_id, run_id, source_gen_run_id, scenario_name
) s
  ON t.trace_id = s.trace_id
 AND t.run_id = s.run_id
 AND t.source_gen_run_id = s.source_gen_run_id
 AND t.scenario_name = s.scenario_name
SET t.anomaly_seq = s.new_seq;

-- 4) Replace single-column trace_id PK with composite PK if needed.
-- Drop current PRIMARY KEY if it is not already (trace_id, anomaly_seq).
SET @pk_cols := (
  SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA=@db_name
    AND TABLE_NAME='v05_source_anomaly_trace_day'
    AND INDEX_NAME='PRIMARY'
);

SET @sql := IF(
  @pk_cols IS NOT NULL AND @pk_cols <> 'trace_id,anomaly_seq',
  'ALTER TABLE v05_source_anomaly_trace_day DROP PRIMARY KEY',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @pk_cols := (
  SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA=@db_name
    AND TABLE_NAME='v05_source_anomaly_trace_day'
    AND INDEX_NAME='PRIMARY'
);

SET @sql := IF(
  @pk_cols IS NULL,
  'ALTER TABLE v05_source_anomaly_trace_day ADD PRIMARY KEY (trace_id, anomaly_seq)',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 5) Add useful secondary indexes if missing.
SET @idx_exists := EXISTS (
  SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND INDEX_NAME='idx_v05_src_trace_lookup'
);
SET @sql := IF(
  NOT @idx_exists,
  'ALTER TABLE v05_source_anomaly_trace_day ADD KEY idx_v05_src_trace_lookup (profile_id, target_date, scenario_name, run_id, source_gen_run_id)',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx_exists := EXISTS (
  SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA=@db_name AND TABLE_NAME='v05_source_anomaly_trace_day' AND INDEX_NAME='idx_v05_src_trace_layer'
);
SET @sql := IF(
  NOT @idx_exists,
  'ALTER TABLE v05_source_anomaly_trace_day ADD KEY idx_v05_src_trace_layer (profile_id, target_date, scenario_name, runtime_layer)',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 6) Verify final PK.
SELECT
  TABLE_NAME,
  INDEX_NAME,
  GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',') AS pk_columns
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA=@db_name
  AND TABLE_NAME='v05_source_anomaly_trace_day'
  AND INDEX_NAME='PRIMARY'
GROUP BY TABLE_NAME, INDEX_NAME;
