-- CASE-OBS-001 Phase4-B Step3
-- Authority Risk Layer consumes Pattern Layer, not raw Evidence directly.

ALTER TABLE unified_reliability_score_day_v05
  ADD COLUMN IF NOT EXISTS risk_pattern VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS pattern_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS pattern_reason VARCHAR(1024) NULL,
  ADD COLUMN IF NOT EXISTS pattern_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL,
  ADD COLUMN IF NOT EXISTS pattern_is_risk_driver TINYINT NULL,
  ADD COLUMN IF NOT EXISTS evidence_direct_to_risk TINYINT NULL,
  ADD COLUMN IF NOT EXISTS concentration_likelihood_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS criticality_impact_score DOUBLE NULL;

CREATE INDEX IF NOT EXISTS idx_v05_unified_risk_pattern
  ON unified_reliability_score_day_v05 (profile_id, target_date, scenario_name, risk_pattern);
