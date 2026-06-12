CREATE TABLE IF NOT EXISTS v05_observability_measurement_day (
  profile_id VARCHAR(128) NOT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  run_id BIGINT NOT NULL DEFAULT 0,
  web_hits BIGINT DEFAULT 0,
  wc_hits BIGINT DEFAULT 0,
  canonical_behavior_events BIGINT DEFAULT 0,
  collection_gap_count BIGINT DEFAULT 0,
  collection_gap_rate DOUBLE DEFAULT 0,
  canonical_gap_count BIGINT DEFAULT 0,
  canonical_gap_rate DOUBLE DEFAULT 0,
  web_to_canonical_gap_count BIGINT DEFAULT 0,
  web_to_canonical_gap_rate DOUBLE DEFAULT 0,
  web_uv_ip BIGINT DEFAULT 0,
  wc_uv_pcid BIGINT DEFAULT 0,
  uv_gap_rate DOUBLE DEFAULT 0,
  web_checkout_hits BIGINT DEFAULT 0,
  wc_checkout_hits BIGINT DEFAULT 0,
  checkout_missing_rate DOUBLE DEFAULT 0,
  web_product_hits BIGINT DEFAULT 0,
  wc_product_hits BIGINT DEFAULT 0,
  product_missing_rate DOUBLE DEFAULT 0,
  observability_signal_score DOUBLE DEFAULT 0,
  observability_risk_level VARCHAR(32) DEFAULT 'low',
  recommended_semantic_risk VARCHAR(128) DEFAULT NULL,
  dominant_observability_signal VARCHAR(128) DEFAULT NULL,
  suspected_root_cause VARCHAR(255) DEFAULT NULL,
  baseline_mode VARCHAR(64) DEFAULT 'same_run_evidence_baseline',
  delta_source_type VARCHAR(64) DEFAULT 'DIRECT_OBSERVABILITY_MEASUREMENT',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY(profile_id,target_date,scenario_name,source_gen_run_id,run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
ALTER TABLE v05_observability_measurement_day ADD COLUMN IF NOT EXISTS observability_signal_score DOUBLE DEFAULT 0;
ALTER TABLE v05_observability_measurement_day ADD COLUMN IF NOT EXISTS observability_risk_level VARCHAR(32) DEFAULT 'low';
ALTER TABLE v05_observability_measurement_day ADD COLUMN IF NOT EXISTS recommended_semantic_risk VARCHAR(128) DEFAULT NULL;
ALTER TABLE v05_observability_measurement_day ADD COLUMN IF NOT EXISTS dominant_observability_signal VARCHAR(128) DEFAULT NULL;
