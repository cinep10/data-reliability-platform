-- CASE-OBS-001 Phase4-D Hotfix 005
-- Widen source_table for merged OBS interpretation provenance.
-- Safe to run repeatedly.
ALTER TABLE r_v05_observability_interpretation_day
  MODIFY COLUMN source_table VARCHAR(512) DEFAULT NULL;
