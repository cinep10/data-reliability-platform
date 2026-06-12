-- v0.5 Phase3-C Step3/4: Unified Risk Model = Likelihood x Impact
-- SQL role: extend Authority Risk Layer output contract.
-- Confidence is stored separately and must not be multiplied into risk.

ALTER TABLE unified_reliability_score_day_v05
  ADD COLUMN IF NOT EXISTS risk_model_version VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS authority_risk_input_version VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS risk_model_formula VARCHAR(128) NULL,
  ADD COLUMN IF NOT EXISTS likelihood_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS impact_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS unified_risk_model_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS statistical_likelihood_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS baseline_deviation_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS propagation_likelihood_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS multi_metric_co_movement_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS business_impact_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS kpi_distortion_impact_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS transaction_impact_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS affected_domain_impact_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS runtime_decision_impact_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS root_cause_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS reconciliation_confidence DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS confidence_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS confidence_level VARCHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS confidence_separate_from_risk TINYINT NULL,
  ADD COLUMN IF NOT EXISTS risk_classification VARCHAR(128) NULL;
