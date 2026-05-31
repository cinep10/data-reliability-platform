-- v0.5 Phase 3: Reconciliation Measurement Architecture
-- SQL role: deterministic measurement materialization only. No risk interpretation here.

CREATE TABLE IF NOT EXISTS v05_reconciliation_measurement_day (
  measurement_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,

  behavior_event_count BIGINT NOT NULL DEFAULT 0,
  transaction_event_count BIGINT NOT NULL DEFAULT 0,
  state_event_count BIGINT NOT NULL DEFAULT 0,

  behavior_transaction_total_count BIGINT NOT NULL DEFAULT 0,
  behavior_transaction_matched_count BIGINT NOT NULL DEFAULT 0,
  behavior_only_count BIGINT NOT NULL DEFAULT 0,
  transaction_only_count BIGINT NOT NULL DEFAULT 0,
  behavior_transaction_match_rate DECIMAL(12,6) NOT NULL DEFAULT 0,
  conversion_gap DECIMAL(12,6) NOT NULL DEFAULT 0,

  transaction_state_total_count BIGINT NOT NULL DEFAULT 0,
  transaction_state_matched_count BIGINT NOT NULL DEFAULT 0,
  orphan_state_count BIGINT NOT NULL DEFAULT 0,
  transaction_without_state_count BIGINT NOT NULL DEFAULT 0,
  transaction_state_match_rate DECIMAL(12,6) NOT NULL DEFAULT 0,
  payment_order_gap DECIMAL(12,6) NOT NULL DEFAULT 0,
  refund_transition_gap DECIMAL(12,6) NOT NULL DEFAULT 0,

  avg_behavior_transaction_gap_ms BIGINT DEFAULT NULL,
  p95_behavior_transaction_gap_ms BIGINT DEFAULT NULL,
  avg_transaction_state_gap_ms BIGINT DEFAULT NULL,
  p95_transaction_state_gap_ms BIGINT DEFAULT NULL,
  payment_processing_delay_ms BIGINT DEFAULT NULL,
  delivery_state_delay_ms BIGINT DEFAULT NULL,
  refund_delay_ms BIGINT DEFAULT NULL,

  duplicate_order_count BIGINT NOT NULL DEFAULT 0,
  duplicate_payment_count BIGINT NOT NULL DEFAULT 0,
  coupon_reconciliation_gap DECIMAL(12,6) NOT NULL DEFAULT 0,

  propagation_distortion_count BIGINT NOT NULL DEFAULT 0,
  measurement_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(measurement_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (measurement_id),
  UNIQUE KEY uk_v05_recon_measure_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_recon_measure_date (profile_id, target_date),
  KEY idx_v05_recon_measure_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE OR REPLACE VIEW vw_v05_reconciliation_measurement_day AS
SELECT * FROM v05_reconciliation_measurement_day;
