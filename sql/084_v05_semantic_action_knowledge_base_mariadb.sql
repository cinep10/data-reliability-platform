-- v0.5 Phase3-C Step5: Semantic / Action Knowledge Base
-- SQL role: extend persistence for classification, narrative, and action catalog.
-- Risk remains owned by unified_reliability_score_day_v05.
-- Semantic/Action are Knowledge Base consumers of authority risk output.

ALTER TABLE semantic_interpretation_day_v05
  ADD COLUMN IF NOT EXISTS semantic_kb_version VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS semantic_role VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS semantic_is_risk_driver TINYINT NULL,
  ADD COLUMN IF NOT EXISTS risk_classification VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS narrative_template_id VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS risk_narrative TEXT NULL,
  ADD COLUMN IF NOT EXISTS likelihood_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS likelihood_level VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS impact_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS impact_level VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS authority_risk_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS authority_risk_level VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS root_cause_candidate VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS root_cause_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS confidence_level VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS action_catalog_key VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS evidence_signal VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS evidence_metric VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS evidence_value DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS evidence_threshold DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS mapping_rule_id VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS catalog_selection_reason TEXT NULL,
  ADD COLUMN IF NOT EXISTS catalog_selection_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL CHECK (json_valid(catalog_selection_payload_json));

ALTER TABLE action_recommendation_day_v05
  ADD COLUMN IF NOT EXISTS action_catalog_version VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS action_catalog_key VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS risk_classification VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS authority_risk_level VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS confidence_level VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS root_cause_candidate VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS action_is_risk_engine TINYINT NULL,
  ADD COLUMN IF NOT EXISTS evidence_signal VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mapping_rule_id VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS catalog_selection_reason TEXT NULL;
