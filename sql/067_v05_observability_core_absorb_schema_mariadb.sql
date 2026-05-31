CREATE TABLE IF NOT EXISTS r_v05_observability_analysis_day (
  profile_id VARCHAR(128) NOT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  run_id BIGINT NOT NULL DEFAULT 0,
  source_gen_run_id BIGINT NOT NULL DEFAULT 0,
  collection_gap_rate DOUBLE DEFAULT 0,
  canonical_gap_rate DOUBLE DEFAULT 0,
  canonical_observability_gap_score DOUBLE DEFAULT 0,
  collection_completeness_score DOUBLE DEFAULT 0,
  baseline_delta_score DOUBLE DEFAULT 0,
  observability_score DOUBLE DEFAULT 0,
  observability_risk_level VARCHAR(32) DEFAULT 'low',
  recommended_semantic_risk VARCHAR(128) DEFAULT NULL,
  dominant_observability_signal VARCHAR(128) DEFAULT NULL,
  analysis_reason TEXT DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(profile_id,target_date,scenario_name,run_id,source_gen_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
ALTER TABLE r_v05_observability_analysis_day ADD COLUMN IF NOT EXISTS canonical_observability_gap_score DOUBLE DEFAULT 0;
ALTER TABLE r_v05_observability_analysis_day ADD COLUMN IF NOT EXISTS collection_completeness_score DOUBLE DEFAULT 0;
ALTER TABLE r_v05_observability_analysis_day ADD COLUMN IF NOT EXISTS baseline_delta_score DOUBLE DEFAULT 0;
