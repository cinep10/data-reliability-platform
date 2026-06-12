-- CASE-OBS-001 Phase3-B: v0.5 Cross-domain Propagation Evidence
-- SQL role: persistence only. R calculates propagation semantics from measurement outputs.

CREATE TABLE IF NOT EXISTS v05_cross_domain_propagation_evidence_day (
  evidence_id BIGINT NOT NULL AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT DEFAULT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) DEFAULT NULL,

  affected_domains LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(affected_domains)),
  affected_domain_count INT NOT NULL DEFAULT 0,

  behavior_impact_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  transaction_impact_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  state_impact_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  conversion_impact_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  attribution_impact_score DECIMAL(12,6) NOT NULL DEFAULT 0,

  propagation_strength DECIMAL(12,6) NOT NULL DEFAULT 0,
  propagation_level VARCHAR(64) NOT NULL DEFAULT 'stable',

  mapping_coverage DECIMAL(12,6) NOT NULL DEFAULT 0,
  sample_size_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  reconciliation_quality_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  baseline_quality_score DECIMAL(12,6) NOT NULL DEFAULT 0,
  reconciliation_confidence DECIMAL(12,6) NOT NULL DEFAULT 0,

  dominant_propagation_path VARCHAR(512) DEFAULT NULL,
  evidence_summary VARCHAR(1024) DEFAULT NULL,
  evidence_payload_json LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(evidence_payload_json)),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (evidence_id),
  UNIQUE KEY uk_v05_cross_domain_prop_scope (profile_id, target_date, run_id, source_gen_run_id),
  KEY idx_v05_cross_domain_prop_date (profile_id, target_date),
  KEY idx_v05_cross_domain_prop_scenario (profile_id, target_date, scenario_name),
  KEY idx_v05_cross_domain_prop_level (propagation_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE OR REPLACE VIEW vw_v05_cross_domain_propagation_evidence_day AS
SELECT * FROM v05_cross_domain_propagation_evidence_day;
