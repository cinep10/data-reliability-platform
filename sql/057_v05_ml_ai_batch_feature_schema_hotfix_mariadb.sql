-- v0.5 ML/AI batch-feature interface hotfix
-- Purpose: include batch distribution/anomaly reliability signals in ML/AI interface.
-- Language responsibility: SQL = persistence/schema only.

SET @db_name := DATABASE();

-- v05_ml_feature_snapshot_day: add batch reliability feature columns when missing.
SET @sql := IF(
  (SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_behavior_overall_score') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_behavior_overall_score DECIMAL(18,10) NOT NULL DEFAULT 0 AFTER recommended_action',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_distribution_risk_score') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_distribution_risk_score DECIMAL(18,10) NOT NULL DEFAULT 0 AFTER batch_behavior_overall_score','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_js_divergence') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_js_divergence DECIMAL(18,10) NOT NULL DEFAULT 0 AFTER batch_distribution_risk_score','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_kl_divergence') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_kl_divergence DECIMAL(18,10) NOT NULL DEFAULT 0 AFTER batch_js_divergence','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_entropy_delta') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_entropy_delta DECIMAL(18,10) NOT NULL DEFAULT 0 AFTER batch_kl_divergence','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_max_ratio_delta') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_max_ratio_delta DECIMAL(18,10) NOT NULL DEFAULT 0 AFTER batch_entropy_delta','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_anomaly_score') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_anomaly_score DECIMAL(18,10) NOT NULL DEFAULT 0 AFTER batch_max_ratio_delta','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_anomaly_signal') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_anomaly_signal VARCHAR(128) NOT NULL DEFAULT ''none'' AFTER batch_anomaly_score','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_distribution_status') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_distribution_status VARCHAR(32) NOT NULL DEFAULT ''PASS'' AFTER batch_anomaly_signal','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ml_feature_snapshot_day' AND column_name='batch_feature_json') = 0,
  'ALTER TABLE v05_ml_feature_snapshot_day ADD COLUMN batch_feature_json LONGTEXT NULL AFTER batch_distribution_status','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- AI incident context: allow evidence-constrained summaries to cite batch reliability features.
SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ai_incident_context_day' AND column_name='batch_context_json') = 0,
  'ALTER TABLE v05_ai_incident_context_day ADD COLUMN batch_context_json LONGTEXT NULL','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ai_incident_context_day' AND column_name='batch_anomaly_signal') = 0,
  'ALTER TABLE v05_ai_incident_context_day ADD COLUMN batch_anomaly_signal VARCHAR(128) NOT NULL DEFAULT ''none''','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ai_incident_context_day' AND column_name='batch_anomaly_score') = 0,
  'ALTER TABLE v05_ai_incident_context_day ADD COLUMN batch_anomaly_score DECIMAL(18,10) NOT NULL DEFAULT 0','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=@db_name AND table_name='v05_ai_incident_context_day' AND column_name='batch_distribution_risk_score') = 0,
  'ALTER TABLE v05_ai_incident_context_day ADD COLUMN batch_distribution_risk_score DECIMAL(18,10) NOT NULL DEFAULT 0','SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
