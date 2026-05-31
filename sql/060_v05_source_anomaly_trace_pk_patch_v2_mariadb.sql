-- v0.5 Source Anomaly Trace PK Patch v2
-- Purpose:
--   Make v05_source_anomaly_trace_day support multiple source anomaly rows per pipeline run.
--   This version does NOT assume trace_id already exists.
--   It is defensive for partial/older schemas.
--
-- Target table:
--   v05_source_anomaly_trace_day
--
-- Final key model:
--   trace_id = execution/group identity
--   anomaly_seq = row identity within trace_id
--   PRIMARY KEY(trace_id, anomaly_seq)

CREATE TABLE IF NOT EXISTS v05_source_anomaly_trace_day (
  profile_id VARCHAR(128) NOT NULL,
  target_date DATE NOT NULL,
  run_id BIGINT NOT NULL,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  scenario_name VARCHAR(128) NOT NULL,
  trace_id VARCHAR(512) NOT NULL,
  anomaly_seq BIGINT NOT NULL DEFAULT 1,
  runtime_layer VARCHAR(64) NULL,
  anomaly_type VARCHAR(128) NULL,
  anomaly_mode VARCHAR(128) NULL,
  affected_rows BIGINT DEFAULT 0,
  evidence_count BIGINT DEFAULT 0,
  anomaly_score DECIMAL(18,10) DEFAULT 0,
  trace_json LONGTEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(trace_id, anomaly_seq)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Add required columns only when missing.
SET @db_name := DATABASE();
SET @tbl_name := 'v05_source_anomaly_trace_day';

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='profile_id'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN profile_id VARCHAR(128) NOT NULL DEFAULT '''''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='target_date'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN target_date DATE NOT NULL DEFAULT ''1970-01-01'''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='run_id'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN run_id BIGINT NOT NULL DEFAULT 0'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='source_gen_run_id'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN source_gen_run_id BIGINT NOT NULL DEFAULT 0'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='scenario_name'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN scenario_name VARCHAR(128) NOT NULL DEFAULT '''''
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='trace_id'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN trace_id VARCHAR(512) NULL'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='anomaly_seq'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_seq BIGINT NOT NULL DEFAULT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='runtime_layer'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN runtime_layer VARCHAR(64) NULL'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='anomaly_type'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_type VARCHAR(128) NULL'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='anomaly_mode'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_mode VARCHAR(128) NULL'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='affected_rows'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN affected_rows BIGINT DEFAULT 0'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='evidence_count'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN evidence_count BIGINT DEFAULT 0'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='anomaly_score'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_score DECIMAL(18,10) DEFAULT 0'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='trace_json'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN trace_json LONGTEXT NULL'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@db_name AND table_name=@tbl_name AND column_name='created_at'),
  'SELECT 1',
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Backfill trace_id when missing or blank.
UPDATE v05_source_anomaly_trace_day
SET trace_id = CONCAT(
  COALESCE(NULLIF(profile_id,''), 'unknown'), '-',
  COALESCE(CAST(target_date AS CHAR), '1970-01-01'), '-',
  COALESCE(CAST(run_id AS CHAR), '0'), '-',
  COALESCE(CAST(source_gen_run_id AS CHAR), '0'), '-',
  COALESCE(NULLIF(scenario_name,''), 'unknown')
)
WHERE trace_id IS NULL OR trace_id = '';

-- Make trace_id NOT NULL after backfill.
ALTER TABLE v05_source_anomaly_trace_day MODIFY COLUMN trace_id VARCHAR(512) NOT NULL;

-- Rebuild anomaly_seq deterministically per trace_id.
-- MariaDB user variables are used for compatibility.
SET @prev_trace_id := '';
SET @seq := 0;

UPDATE v05_source_anomaly_trace_day t
JOIN (
  SELECT
    x._row_id,
    x.trace_id,
    @seq := IF(@prev_trace_id = x.trace_id, @seq + 1, 1) AS new_seq,
    @prev_trace_id := x.trace_id AS _assign_trace
  FROM (
    SELECT
      trace_id,
      COALESCE(created_at, CURRENT_TIMESTAMP) AS sort_created_at,
      COALESCE(runtime_layer, '') AS sort_runtime_layer,
      COALESCE(anomaly_type, '') AS sort_anomaly_type,
      COALESCE(anomaly_mode, '') AS sort_anomaly_mode,
      ROW_NUMBER() OVER () AS _row_id
    FROM v05_source_anomaly_trace_day
    ORDER BY trace_id, sort_created_at, sort_runtime_layer, sort_anomaly_type, sort_anomaly_mode
  ) x
) s
ON s.trace_id = t.trace_id
AND COALESCE(s.sort_created_at, CURRENT_TIMESTAMP) = COALESCE(t.created_at, CURRENT_TIMESTAMP)
AND COALESCE(s.sort_runtime_layer, '') = COALESCE(t.runtime_layer, '')
AND COALESCE(s.sort_anomaly_type, '') = COALESCE(t.anomaly_type, '')
AND COALESCE(s.sort_anomaly_mode, '') = COALESCE(t.anomaly_mode, '')
SET t.anomaly_seq = s.new_seq;

-- If the above join was too broad/narrow in a legacy schema, normalize remaining invalid seq.
UPDATE v05_source_anomaly_trace_day
SET anomaly_seq = 1
WHERE anomaly_seq IS NULL OR anomaly_seq < 1;

-- Drop existing primary key if present.
SET @pk_exists := (
  SELECT COUNT(*)
  FROM information_schema.table_constraints
  WHERE table_schema=@db_name
    AND table_name=@tbl_name
    AND constraint_type='PRIMARY KEY'
);
SET @sql := IF(@pk_exists > 0,
  'ALTER TABLE v05_source_anomaly_trace_day DROP PRIMARY KEY',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Add final composite PK.
ALTER TABLE v05_source_anomaly_trace_day
  ADD PRIMARY KEY(trace_id, anomaly_seq);

-- Helpful lookup indexes. Ignore duplicate failures by only adding when missing.
SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema=@db_name AND table_name=@tbl_name AND index_name='idx_v05_src_trace_lookup'
);
SET @sql := IF(@idx_exists > 0,
  'SELECT 1',
  'CREATE INDEX idx_v05_src_trace_lookup ON v05_source_anomaly_trace_day(profile_id, target_date, scenario_name, run_id, source_gen_run_id)'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @idx_exists := (
  SELECT COUNT(*) FROM information_schema.statistics
  WHERE table_schema=@db_name AND table_name=@tbl_name AND index_name='idx_v05_src_trace_layer'
);
SET @sql := IF(@idx_exists > 0,
  'SELECT 1',
  'CREATE INDEX idx_v05_src_trace_layer ON v05_source_anomaly_trace_day(runtime_layer, anomaly_type)'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SELECT 'v05_source_anomaly_trace_day pk patch v2 applied' AS patch_status;
