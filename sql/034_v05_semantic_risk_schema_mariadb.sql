-- v0.5 Phase 4: Semantic Risk and Operational Decision Persistence
-- SQL role: persistence of R/Python outputs only.

CREATE TABLE IF NOT EXISTS reliability_analysis_result_day_v05 (
  analysis_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  reconciliation_gap_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  propagation_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  amplification_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  distortion_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  baseline_delta DECIMAL(12,6) NOT NULL DEFAULT 0,
  transaction_loss_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  customer_impact_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  analysis_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(analysis_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (analysis_id),
  UNIQUE KEY uk_v05_analysis_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_analysis_date (profile_id, target_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS semantic_interpretation_day_v05 (
  semantic_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  behavior_transaction_consistency_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  transaction_state_integrity_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  order_lifecycle_consistency_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  payment_state_reconciliation_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  delivery_timeliness_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  coupon_attribution_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  customer_experience_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  dominant_semantic_risk VARCHAR(128) DEFAULT NULL,
  semantic_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(semantic_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (semantic_id),
  UNIQUE KEY uk_v05_semantic_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_semantic_date (profile_id, target_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS unified_reliability_score_day_v05 (
  score_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  semantic_base_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  amplification_weight DECIMAL(12,6) NOT NULL DEFAULT 0,
  distortion_penalty DECIMAL(12,6) NOT NULL DEFAULT 0,
  baseline_delta_penalty DECIMAL(12,6) NOT NULL DEFAULT 0,
  reconciliation_gap_weight DECIMAL(12,6) NOT NULL DEFAULT 0,
  customer_impact_weight DECIMAL(12,6) NOT NULL DEFAULT 0,
  transaction_loss_weight DECIMAL(12,6) NOT NULL DEFAULT 0,
  overall_risk_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  final_risk_level VARCHAR(64) NOT NULL DEFAULT 'normal',
  score_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(score_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (score_id),
  UNIQUE KEY uk_v05_score_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_score_date (profile_id, target_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS action_recommendation_day_v05 (
  action_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,
  action_rank INT NOT NULL DEFAULT 1,
  action_type VARCHAR(128) NOT NULL,
  recommended_action VARCHAR(512) NOT NULL,
  evidence_summary VARCHAR(1024) DEFAULT NULL,
  evidence_table VARCHAR(128) DEFAULT NULL,
  evidence_metric VARCHAR(128) DEFAULT NULL,
  evidence_value DECIMAL(18,6) DEFAULT NULL,
  action_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(action_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (action_id),
  KEY idx_v05_action_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_action_rank (action_rank)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
