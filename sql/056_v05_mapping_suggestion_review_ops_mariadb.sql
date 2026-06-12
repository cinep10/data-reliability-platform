-- 056_v05_mapping_suggestion_review_ops_mariadb.sql
-- Mapping suggestion review workflow schema/ops placeholder.
-- No automatic approval or event_mapping mutation is performed here.
-- Operators should update review_status manually after inspection.

CREATE TABLE IF NOT EXISTS event_mapping_suggestion_review (
  profile_id VARCHAR(64) NOT NULL,
  dt DATE NOT NULL,
  suggestion_id VARCHAR(128) NOT NULL,
  url_pattern VARCHAR(512) NULL,
  suggested_event_name VARCHAR(255) NULL,
  suggested_page_type VARCHAR(255) NULL,
  evidence_count BIGINT NOT NULL DEFAULT 0,
  review_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  reviewer VARCHAR(128) NULL,
  review_comment TEXT NULL,
  source_table VARCHAR(128) NOT NULL DEFAULT 'event_mapping_suggestion',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY (profile_id, dt, suggestion_id),
  KEY idx_emsr_status (profile_id, dt, review_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Example manual review SQL:
-- UPDATE event_mapping_suggestion_review
-- SET review_status='approved', reviewer='operator', review_comment='approved after URL inspection', reviewed_at=NOW()
-- WHERE profile_id='commerce_deliver' AND dt='2026-05-14' AND suggestion_id='<id>';
