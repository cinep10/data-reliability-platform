-- v0.5 Phase 5: ML Calibration & AI Reliability
-- SQL role: deterministic persistence only. No ML training, risk interpretation, or AI reasoning in SQL.

CREATE TABLE IF NOT EXISTS v05_ml_feature_snapshot_day (
  feature_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  reconciliation_gap DECIMAL(12,6) NOT NULL DEFAULT 0,
  orphan_ratio DECIMAL(12,6) NOT NULL DEFAULT 0,
  duplicate_ratio DECIMAL(12,6) NOT NULL DEFAULT 0,
  delivery_delay_ms BIGINT NOT NULL DEFAULT 0,
  payment_state_gap DECIMAL(12,6) NOT NULL DEFAULT 0,
  conversion_distortion DECIMAL(12,6) NOT NULL DEFAULT 0,
  transaction_without_state_ratio DECIMAL(12,6) NOT NULL DEFAULT 0,
  behavior_only_ratio DECIMAL(12,6) NOT NULL DEFAULT 0,
  transaction_only_ratio DECIMAL(12,6) NOT NULL DEFAULT 0,
  coupon_reconciliation_gap DECIMAL(12,6) NOT NULL DEFAULT 0,
  semantic_base_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  overall_risk_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  final_risk_level VARCHAR(64) NOT NULL DEFAULT 'unknown',
  dominant_semantic_risk VARCHAR(128) DEFAULT NULL,
  recommended_action VARCHAR(512) DEFAULT NULL,
  feature_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(feature_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (feature_id),
  UNIQUE KEY uk_v05_ml_feature_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_ml_feature_date (profile_id, target_date),
  KEY idx_v05_ml_feature_level (final_risk_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS v05_ml_calibration_result_day (
  calibration_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  predicted_risk_class VARCHAR(128) NOT NULL DEFAULT 'unknown',
  predicted_severity_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  reconciliation_failure_probability DECIMAL(12,6) NOT NULL DEFAULT 0,
  score_gap DECIMAL(12,6) NOT NULL DEFAULT 0,
  calibration_status VARCHAR(64) NOT NULL DEFAULT 'unknown',
  model_source VARCHAR(128) NOT NULL DEFAULT 'heuristic_interface',
  ml_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(ml_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (calibration_id),
  UNIQUE KEY uk_v05_ml_calib_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_ml_calib_date (profile_id, target_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS v05_ai_incident_context_day (
  context_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  evidence_count INT NOT NULL DEFAULT 0,
  evidence_missing_flag TINYINT NOT NULL DEFAULT 0,
  context_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(context_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (context_id),
  UNIQUE KEY uk_v05_ai_context_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_ai_context_date (profile_id, target_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS v05_ai_incident_summary_day (
  summary_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  incident_explanation TEXT,
  root_cause_summary TEXT,
  recommended_action_summary TEXT,
  output_source VARCHAR(64) NOT NULL DEFAULT 'deterministic_fallback',
  summary_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(summary_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (summary_id),
  UNIQUE KEY uk_v05_ai_summary_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_ai_summary_date (profile_id, target_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS v05_ai_validation_result_day (
  validation_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  missing_evidence_flag TINYINT NOT NULL DEFAULT 0,
  unsupported_explanation_flag TINYINT NOT NULL DEFAULT 0,
  hallucinated_reconciliation_flag TINYINT NOT NULL DEFAULT 0,
  wrong_operational_recommendation_flag TINYINT NOT NULL DEFAULT 0,
  validation_status VARCHAR(64) NOT NULL DEFAULT 'unknown',
  validation_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(validation_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (validation_id),
  UNIQUE KEY uk_v05_ai_validation_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_ai_validation_date (profile_id, target_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS v05_ai_reliability_score_day (
  ai_score_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  missing_evidence_risk DECIMAL(12,6) NOT NULL DEFAULT 0,
  unsupported_explanation_risk DECIMAL(12,6) NOT NULL DEFAULT 0,
  hallucination_risk DECIMAL(12,6) NOT NULL DEFAULT 0,
  wrong_action_risk DECIMAL(12,6) NOT NULL DEFAULT 0,
  overall_ai_risk_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  ai_reliability_level VARCHAR(64) NOT NULL DEFAULT 'unknown',
  ai_score_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(ai_score_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ai_score_id),
  UNIQUE KEY uk_v05_ai_score_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_ai_score_date (profile_id, target_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE OR REPLACE VIEW vw_v05_phase5_ml_ai_feature_dataset AS
SELECT f.*, c.predicted_risk_class, c.predicted_severity_score, c.reconciliation_failure_probability,
       v.validation_status, a.overall_ai_risk_score, a.ai_reliability_level
FROM v05_ml_feature_snapshot_day f
LEFT JOIN v05_ml_calibration_result_day c
  ON c.profile_id=f.profile_id AND c.target_date=f.target_date AND c.run_id=f.run_id
  AND COALESCE(c.source_gen_run_id, -1)=COALESCE(f.source_gen_run_id, -1)
LEFT JOIN v05_ai_validation_result_day v
  ON v.profile_id=f.profile_id AND v.target_date=f.target_date AND v.run_id=f.run_id
  AND COALESCE(v.source_gen_run_id, -1)=COALESCE(f.source_gen_run_id, -1)
LEFT JOIN v05_ai_reliability_score_day a
  ON a.profile_id=f.profile_id AND a.target_date=f.target_date AND a.run_id=f.run_id
  AND COALESCE(a.source_gen_run_id, -1)=COALESCE(f.source_gen_run_id, -1);

-- Optional model training registry for backfill-trained models.
CREATE TABLE IF NOT EXISTS v05_ml_training_run (
  training_run_id BIGINT NOT NULL AUTO_INCREMENT,
  profile_id VARCHAR(128) NOT NULL,
  dt_from DATE NOT NULL,
  dt_to DATE NOT NULL,
  row_count INT NOT NULL DEFAULT 0,
  label_distribution_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(label_distribution_json)),
  classifier_path VARCHAR(1024) DEFAULT NULL,
  regressor_path VARCHAR(1024) DEFAULT NULL,
  report_path VARCHAR(1024) DEFAULT NULL,
  metrics_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(metrics_json)),
  training_status VARCHAR(64) NOT NULL DEFAULT 'unknown',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(training_run_id),
  KEY idx_v05_ml_training_scope(profile_id, dt_from, dt_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
