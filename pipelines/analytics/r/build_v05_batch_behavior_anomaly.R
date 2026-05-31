#!/usr/bin/env Rscript

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))

# ------------------------------------------------------------------
# Arguments
# ------------------------------------------------------------------

args <- commandArgs(trailingOnly = TRUE)

profile_id <- arg_value(args, "--profile-id")
dt <- arg_value(args, "--dt")

run_id <- as.integer(
  arg_value(args, "--run-id", "0")
)

scenario_name <- arg_value(
  args,
  "--scenario-name",
  "baseline"
)

# ------------------------------------------------------------------
# Database Connection
# ------------------------------------------------------------------

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

# ------------------------------------------------------------------
# Load Data
# ------------------------------------------------------------------

batch_analysis <- read_first_scoped_row(
  con,
  "r_batch_behavior_analysis_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

distribution_analysis <- read_first_scoped_row(
  con,
  "r_batch_distribution_analysis_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

metric_delta <- read_scoped_table(
  con,
  "v05_batch_metric_delta_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

observability <- read_first_scoped_row(
  con,
  "v05_observability_measurement_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

# ------------------------------------------------------------------
# Analysis
# ------------------------------------------------------------------

max_metric_score <- 0

if (nrow(metric_delta) > 0 && "risk_score" %in% names(metric_delta)) {
  max_metric_score <- max(safe_number(metric_delta$risk_score), na.rm = TRUE)
  max_metric_score <- ifelse(is.finite(max_metric_score), max_metric_score, 0)
}

collection_score <- clamp01(
  max(
    pick_number(observability, "collection_gap_rate") * 3,
    pick_number(observability, "canonical_gap_rate") * 3,
    pick_number(observability, "web_to_canonical_gap_rate") * 3,
    pick_number(observability, "checkout_missing_rate") * 2,
    pick_number(observability, "product_missing_rate") * 2,
    pick_number(observability, "uv_gap_rate") * 2,
    max_metric_score
  )
)

batch_score <- clamp01(
  max(
    pick_number(batch_analysis, "overall_batch_behavior_score"),
    pick_number(batch_analysis, "behavior_distortion_score"),
    pick_number(batch_analysis, "conversion_distortion_score"),
    pick_number(batch_analysis, "session_fragmentation_score"),
    pick_number(distribution_analysis, "batch_distribution_score"),
    pick_number(distribution_analysis, "batch_distribution_risk_score")
  )
)

overall_score <- clamp01(
  max(
    batch_score,
    collection_score
  )
)

anomaly_signal <- if (collection_score >= 0.20) {
  "observability_collection_anomaly"
} else if (batch_score >= 0.20) {
  "batch_behavior_distribution_anomaly"
} else {
  "none"
}

anomaly_status <- score_status(
  overall_score,
  warn = 0.20,
  high = 0.60
)

analysis_reason <- paste0(
  "signal=", anomaly_signal,
  ";collection_score=", round(collection_score, 6),
  ";batch_score=", round(batch_score, 6),
  ";metric_delta_score=", round(max_metric_score, 6)
)

# ------------------------------------------------------------------
# Save Result
# ------------------------------------------------------------------

delete_scoped_rows(
  con,
  "v05_batch_behavior_anomaly_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

insert_schema_aware(
  con,
  "v05_batch_behavior_anomaly_day",
  list(
    profile_id = profile_id,
    dt = dt,
    run_id = run_id,
    scenario_name = scenario_name,
    anomaly_signal = anomaly_signal,
    anomaly_score = overall_score,
    batch_distribution_risk_score = batch_score,
    observability_collection_score = collection_score,
    anomaly_status = anomaly_status,
    analysis_reason = analysis_reason
  )
)

# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(
  sprintf(
    "[OK] build_v05_batch_behavior_anomaly scenario=%s signal=%s score=%.6f batch_score=%.6f collection_score=%.6f status=%s\n",
    scenario_name,
    anomaly_signal,
    overall_score,
    batch_score,
    collection_score,
    anomaly_status
  )
)
