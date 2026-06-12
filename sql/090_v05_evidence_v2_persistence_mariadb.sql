ALTER TABLE reliability_analysis_result_day_v05
  ADD COLUMN IF NOT EXISTS event_criticality_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS conversion_criticality_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS revenue_criticality_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS traffic_preservation_score DOUBLE NULL,
  ADD COLUMN IF NOT EXISTS business_kpi_distortion_score DOUBLE NULL;
