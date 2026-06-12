-- v0.5 behavior anomaly summary compatibility columns.
-- This file is intentionally additive and safe to apply repeatedly.
ALTER TABLE v05_batch_behavior_anomaly_day
  ADD COLUMN IF NOT EXISTS behavior_analysis_score DOUBLE DEFAULT 0 AFTER batch_distribution_risk_score,
  ADD COLUMN IF NOT EXISTS observability_collection_score DOUBLE DEFAULT 0 AFTER behavior_analysis_score,
  ADD COLUMN IF NOT EXISTS time_pattern_score DOUBLE DEFAULT 0 AFTER observability_collection_score,
  ADD COLUMN IF NOT EXISTS correlation_score DOUBLE DEFAULT 0 AFTER time_pattern_score,
  ADD COLUMN IF NOT EXISTS contribution_max_score DOUBLE DEFAULT 0,
  ADD COLUMN IF NOT EXISTS dominant_contribution_family VARCHAR(128) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS dominant_contribution_metric VARCHAR(128) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS baseline_mode VARCHAR(64) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS baseline_window VARCHAR(32) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS baseline_status VARCHAR(64) DEFAULT NULL;
