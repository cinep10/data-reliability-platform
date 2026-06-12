-- v0.5 Phase3-C Step2: Reliability Analysis Risk Input Interface
-- SQL role: fix the authority analytics output contract consumed by Unified Risk.
-- No risk formula change. This only guarantees required columns exist.

ALTER TABLE reliability_analysis_result_day_v05
  ADD COLUMN IF NOT EXISTS statistical_evidence_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS statistical_evidence_raw_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS statistical_evidence_effective_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS statistical_evidence_reflected TINYINT NULL,
  ADD COLUMN IF NOT EXISTS statistical_evidence_row_count INT NULL,
  ADD COLUMN IF NOT EXISTS statistical_evidence_min_sample_days INT NULL,
  ADD COLUMN IF NOT EXISTS statistical_evidence_max_sample_days INT NULL,
  ADD COLUMN IF NOT EXISTS max_z_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS max_historical_percentile DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS control_limit_breach_count INT NULL,
  ADD COLUMN IF NOT EXISTS co_movement_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS statistical_significance VARCHAR(50) NULL,
  ADD COLUMN IF NOT EXISTS affected_domains LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(affected_domains)),
  ADD COLUMN IF NOT EXISTS affected_domain_count INT NULL,
  ADD COLUMN IF NOT EXISTS cross_domain_propagation_strength DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS cross_domain_propagation_level VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS reconciliation_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS dominant_propagation_path VARCHAR(512) NULL,
  ADD COLUMN IF NOT EXISTS authority_interface_version VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS risk_input_ready TINYINT NULL,
  ADD COLUMN IF NOT EXISTS authority_input_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(authority_input_payload_json));
