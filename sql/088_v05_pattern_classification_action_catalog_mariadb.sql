-- CASE-OBS-001 Phase4-B Step4/5: Pattern-driven Classification and Action Catalog
-- Semantic/Action are Knowledge Base layers. They consume Authority Risk + Risk Pattern.
-- They do not compute risk.

ALTER TABLE semantic_interpretation_day_v05
  ADD COLUMN IF NOT EXISTS classification_layer_version VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS classification_role VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS classification_source VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS risk_pattern VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS pattern_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS pattern_reason VARCHAR(1024) NULL,
  ADD COLUMN IF NOT EXISTS classification_is_risk_engine TINYINT NULL,
  ADD COLUMN IF NOT EXISTS pattern_to_classification_rule_id VARCHAR(128) NULL;

ALTER TABLE action_recommendation_day_v05
  ADD COLUMN IF NOT EXISTS action_catalog_mode VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS action_catalog_source VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS risk_pattern VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS pattern_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS pattern_action_rule_id VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS pattern_action_reason TEXT NULL;
