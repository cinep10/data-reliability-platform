-- v0.5 Phase4-B Step1: Authority Evidence Layer explicit contract
-- SQL role: make Reliability Analysis output distinguish Evidence from Risk.
-- Evidence groups are not risk scores. Pattern/Risk layers interpret them later.

ALTER TABLE reliability_analysis_result_day_v05
  ADD COLUMN IF NOT EXISTS evidence_layer_version VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS evidence_ready TINYINT NULL,
  ADD COLUMN IF NOT EXISTS baseline_evidence_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS statistical_evidence_group_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS propagation_evidence_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS impact_evidence_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS concentration_evidence_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS criticality_evidence_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS evidence_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(evidence_payload_json)),
  ADD COLUMN IF NOT EXISTS evidence_summary VARCHAR(512) NULL;
