-- v0.5 Phase4-B Step2: Authority Pattern Layer explicit contract
-- SQL role: add generic risk pattern fields after Evidence and before Risk.
-- Pattern is not risk. Case-specific segment names remain measurement/reference evidence.

ALTER TABLE reliability_analysis_result_day_v05
  ADD COLUMN IF NOT EXISTS pattern_layer_version VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS pattern_ready TINYINT NULL,
  ADD COLUMN IF NOT EXISTS risk_pattern VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS pattern_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS pattern_reason VARCHAR(512) NULL,
  ADD COLUMN IF NOT EXISTS pattern_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(pattern_payload_json));
