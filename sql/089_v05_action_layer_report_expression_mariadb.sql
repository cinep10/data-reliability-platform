-- CASE-OBS-001 Phase4-B Step6: Authority Action + OBS Reference Action report expression
-- Action remains Knowledge Base. Authority actions are selected by Authority Pattern.
-- OBS reference actions are supporting explanation/audit actions only and do not drive risk.

ALTER TABLE action_recommendation_day_v05
  ADD COLUMN IF NOT EXISTS action_layer VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS reference_action_source VARCHAR(80) NULL,
  ADD COLUMN IF NOT EXISTS reference_action_reason TEXT NULL,
  ADD COLUMN IF NOT EXISTS authority_action_rank INT NULL,
  ADD COLUMN IF NOT EXISTS reference_action_rank INT NULL;

ALTER TABLE action_recommendation_day_v05
  ADD INDEX IF NOT EXISTS idx_v05_action_layer_report (
    profile_id, target_date, scenario_name, run_id, source_gen_run_id, action_layer, action_rank
  );
