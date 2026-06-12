-- v0.5 Phase3-C Step5-B: Semantic/Action Knowledge Base Explainability
-- Purpose: persist why a semantic classification and action catalog were selected.
-- This keeps Semantic/Action as Knowledge Base, not risk engine.

ALTER TABLE semantic_interpretation_day_v05
  ADD COLUMN IF NOT EXISTS evidence_signal VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS evidence_metric VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS evidence_value DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS evidence_threshold DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS mapping_rule_id VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS catalog_selection_reason TEXT NULL,
  ADD COLUMN IF NOT EXISTS catalog_selection_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL CHECK (json_valid(catalog_selection_payload_json));

ALTER TABLE action_recommendation_day_v05
  ADD COLUMN IF NOT EXISTS evidence_signal VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mapping_rule_id VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS catalog_selection_reason TEXT NULL;
