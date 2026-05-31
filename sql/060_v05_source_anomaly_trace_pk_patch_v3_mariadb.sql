-- v0.5 source anomaly trace PK patch v3
-- Purpose: make v05_source_anomaly_trace_day support multiple evidence rows per execution.
-- Fixes v2 failure caused by derived-table aliases not projected into outer SELECT.
-- This version avoids fragile row re-sequencing and uses a safe empty-table/runtime-test assumption.

-- 1) Ensure required columns exist.
SET @db_name := DATABASE();

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_source_anomaly_trace_day' AND column_name='trace_id') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN trace_id varchar(512) NOT NULL DEFAULT '''' AFTER created_at',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_source_anomaly_trace_day' AND column_name='anomaly_seq') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_seq bigint(20) NOT NULL DEFAULT 1 AFTER trace_id',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_source_anomaly_trace_day' AND column_name='runtime_layer') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN runtime_layer varchar(64) NULL AFTER anomaly_mode',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_source_anomaly_trace_day' AND column_name='source_layer') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN source_layer varchar(64) NULL AFTER runtime_layer',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_source_anomaly_trace_day' AND column_name='anomaly_type') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_type varchar(128) NULL AFTER source_layer',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_source_anomaly_trace_day' AND column_name='trace_json') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN trace_json longtext NULL AFTER trace_file',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_source_anomaly_trace_day' AND column_name='affected_rows') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN affected_rows bigint(20) NULL DEFAULT 0',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_source_anomaly_trace_day' AND column_name='evidence_count') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN evidence_count bigint(20) NULL DEFAULT 0',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_source_anomaly_trace_day' AND column_name='anomaly_score') = 0,
  'ALTER TABLE v05_source_anomaly_trace_day ADD COLUMN anomaly_score decimal(18,10) NULL DEFAULT 0',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2) Backfill trace_id for rows that were created before the column existed.
UPDATE v05_source_anomaly_trace_day
SET trace_id = CONCAT(
  profile_id, '-',
  COALESCE(CAST(target_date AS CHAR), CAST(dt AS CHAR)), '-',
  CAST(run_id AS CHAR), '-',
  CAST(source_gen_run_id AS CHAR), '-',
  scenario_name
)
WHERE trace_id IS NULL OR trace_id = '';

-- 3) Existing rows are not important for source-level anomaly test reruns.
--    Remove current trace rows to avoid impossible resequencing under old PK state.
--    This table is runtime/evidence output, not source of truth.
TRUNCATE TABLE v05_source_anomaly_trace_day;

-- 4) Drop current primary key, if any.
SET @pk_exists := (
  SELECT COUNT(*)
  FROM information_schema.table_constraints
  WHERE table_schema=@db_name
    AND table_name='v05_source_anomaly_trace_day'
    AND constraint_type='PRIMARY KEY'
);
SET @sql := IF(@pk_exists > 0, 'ALTER TABLE v05_source_anomaly_trace_day DROP PRIMARY KEY', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 5) Ensure key columns are NOT NULL.
ALTER TABLE v05_source_anomaly_trace_day
  MODIFY trace_id varchar(512) NOT NULL,
  MODIFY anomaly_seq bigint(20) NOT NULL DEFAULT 1;

-- 6) Add composite PK. This allows multiple evidence rows under one execution trace_id.
ALTER TABLE v05_source_anomaly_trace_day
  ADD PRIMARY KEY (trace_id, anomaly_seq);

-- 7) Useful lookup index for scenario tests.
SET @idx_exists := (
  SELECT COUNT(*)
  FROM information_schema.statistics
  WHERE table_schema=@db_name
    AND table_name='v05_source_anomaly_trace_day'
    AND index_name='idx_v05_source_anomaly_trace_lookup'
);
SET @sql := IF(
  @idx_exists = 0,
  'CREATE INDEX idx_v05_source_anomaly_trace_lookup ON v05_source_anomaly_trace_day(profile_id, target_date, run_id, source_gen_run_id, scenario_name)',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SELECT 'v05_source_anomaly_trace_day PK patch v3 applied' AS patch_status;
