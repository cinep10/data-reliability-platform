-- CASE-OBS-001 Phase4-D: Evidence Primitive + Failure Mechanism extension.
-- Pattern taxonomy remains small; concrete scenario differences are represented
-- by failure_mechanism/mechanism_source and evidence primitive scores.

ALTER TABLE reliability_analysis_result_day_v05
  ADD COLUMN IF NOT EXISTS identity_integrity_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS semantic_shift_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS visibility_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS failure_mechanism VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mechanism_source VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mechanism_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS evidence_primitive_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(evidence_primitive_payload_json));

ALTER TABLE unified_reliability_score_day_v05
  ADD COLUMN IF NOT EXISTS failure_mechanism VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mechanism_source VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mechanism_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS identity_integrity_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS semantic_shift_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS visibility_score DOUBLE NULL;

ALTER TABLE semantic_interpretation_day_v05
  ADD COLUMN IF NOT EXISTS failure_mechanism VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mechanism_source VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mechanism_confidence DOUBLE NULL;

ALTER TABLE action_recommendation_day_v05
  ADD COLUMN IF NOT EXISTS failure_mechanism VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mechanism_source VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS mechanism_confidence DOUBLE NULL;
