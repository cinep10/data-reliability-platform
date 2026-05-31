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

baseline_window <- arg_value(
  args,
  "--baseline-window",
  "30d"
)

# ------------------------------------------------------------------
# Database Connection
# ------------------------------------------------------------------

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

# ------------------------------------------------------------------
# Load Data
# ------------------------------------------------------------------

batch_measurement <- read_first_scoped_row(
  con,
  "measurement_batch_day",
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

distribution_compare <- read_scoped_table(
  con,
  "v05_batch_behavior_distribution_compare_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

# ------------------------------------------------------------------
# Analysis
# ------------------------------------------------------------------

score_from_metric <- function(scope, metric_names) {
  if (nrow(metric_delta) < 1 || !"risk_score" %in% names(metric_delta)) {
    return(0)
  }

  rows <- metric_delta[
    metric_delta$metric_scope %in% scope &
      metric_delta$metric_name %in% metric_names,
  ]

  if (nrow(rows) < 1) {
    return(0)
  }

  score <- max(safe_number(rows$risk_score), na.rm = TRUE)

  ifelse(is.finite(score), score, 0)
}

behavior_volume_score <- score_from_metric(
  "behavior_volume",
  c("event_count", "pv", "uv", "visit")
)

collection_score <- score_from_metric(
  "observability",
  c(
    "collection_gap_rate",
    "canonical_gap_rate",
    "checkout_missing_rate",
    "product_missing_rate",
    "uv_gap_rate"
  )
)

collector_count_score <- score_from_metric(
  "observability",
  c("wc_hits", "canonical_behavior_events")
)

funnel_score <- score_from_metric(
  "behavior_funnel",
  c("conversion_rate", "collector_capture_rate", "estimated_missing_rate")
)

if (nrow(distribution_compare) > 0 && "distribution_shift_score" %in% names(distribution_compare)) {
  distribution_score <- max(safe_number(distribution_compare$distribution_shift_score), na.rm = TRUE)
  distribution_score <- ifelse(is.finite(distribution_score), distribution_score, 0)
} else {
  distribution_score <- 0
}

baseline_status_values <- character()

if (nrow(metric_delta) > 0 && "baseline_status" %in% names(metric_delta)) {
  baseline_status_values <- c(
    baseline_status_values,
    unique(as.character(metric_delta$baseline_status))
  )
}

if (nrow(distribution_compare) > 0 && "baseline_status" %in% names(distribution_compare)) {
  baseline_status_values <- c(
    baseline_status_values,
    unique(as.character(distribution_compare$baseline_status))
  )
}

baseline_status <- if (any(baseline_status_values == "baseline_available", na.rm = TRUE)) {
  "baseline_available"
} else if (scenario_name == "baseline") {
  "BASELINE_SELF_REFERENCE"
} else {
  "BASELINE_MISSING_REVIEW"
}

identity_score <- 0
mapping_score <- clamp01(1 - pick_number(batch_measurement, "mapping_coverage"))
batch_quality_score <- score_from_metric(
  "batch_quality",
  c("validation_fail_rate", "quality_issue_rate")
)

behavior_distortion_score <- clamp01(
  max(
    behavior_volume_score,
    distribution_score,
    collection_score,
    collector_count_score
  )
)

conversion_distortion_score <- clamp01(
  max(
    funnel_score,
    collection_score * 0.70
  )
)

session_fragmentation_score <- clamp01(
  max(
    score_from_metric("behavior_volume", c("visit")),
    collection_score * 0.45
  )
)

overall_score <- clamp01(
  max(
    behavior_distortion_score,
    conversion_distortion_score,
    session_fragmentation_score,
    identity_score,
    mapping_score,
    batch_quality_score
  )
)

signal_scores <- c(
  behavior_distortion = behavior_distortion_score,
  conversion_distortion = conversion_distortion_score,
  session_fragmentation = session_fragmentation_score,
  mapping_risk = mapping_score,
  batch_quality = batch_quality_score
)

dominant_batch_signal <- names(signal_scores)[which.max(signal_scores)]

if (overall_score <= 0) {
  dominant_batch_signal <- "none"
}

analysis_status <- if (baseline_status == "BASELINE_MISSING_REVIEW") {
  "BASELINE_MISSING_REVIEW"
} else {
  score_status(overall_score, warn = 0.20, high = 0.60)
}

analysis_reason <- paste0(
  "baseline_window=", baseline_window,
  ";behavior_volume_score=", round(behavior_volume_score, 6),
  ";collection_score=", round(collection_score, 6),
  ";collector_count_score=", round(collector_count_score, 6),
  ";distribution_score=", round(distribution_score, 6),
  ";funnel_score=", round(funnel_score, 6)
)

# ------------------------------------------------------------------
# Save Result
# ------------------------------------------------------------------

delete_scoped_rows(
  con,
  "r_batch_behavior_analysis_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

insert_schema_aware(
  con,
  "r_batch_behavior_analysis_day",
  list(
    profile_id = profile_id,
    dt = dt,
    run_id = run_id,
    scenario_name = scenario_name,
    behavior_distortion_score = behavior_distortion_score,
    conversion_distortion_score = conversion_distortion_score,
    session_fragmentation_score = session_fragmentation_score,
    identity_anomaly_score = identity_score,
    mapping_risk_score = mapping_score,
    batch_quality_risk_score = batch_quality_score,
    dominant_batch_signal = dominant_batch_signal,
    overall_batch_behavior_score = overall_score,
    analysis_status = analysis_status,
    baseline_status = baseline_status,
    analysis_reason = analysis_reason
  )
)

# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(
  sprintf(
    "[R_BATCH_BEHAVIOR_ANALYSIS] profile=%s dt=%s run_id=%s dominant=%s overall=%.6f behavior=%.6f conversion=%.6f session=%.6f collection=%.6f status=%s baseline_status=%s\n",
    profile_id,
    dt,
    run_id,
    dominant_batch_signal,
    overall_score,
    behavior_distortion_score,
    conversion_distortion_score,
    session_fragmentation_score,
    collection_score,
    analysis_status,
    baseline_status
  )
)
