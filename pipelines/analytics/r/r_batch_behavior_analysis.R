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

source_gen_run_id <- as.integer(
  arg_value(args, "--source-gen-run-id", "0")
)

scenario_name <- arg_value(
  args,
  "--scenario-name",
  "baseline"
)

baseline_mode <- arg_value(
  args,
  "--baseline-mode",
  "temporal_baseline"
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
# Contribution Helpers
# ------------------------------------------------------------------

metric_rows <- function(scopes, metric_names) {
  if (nrow(metric_delta) < 1) {
    return(data.frame())
  }

  if (!all(c("metric_scope", "metric_name") %in% names(metric_delta))) {
    return(data.frame())
  }

  metric_delta[
    metric_delta$metric_scope %in% scopes &
      metric_delta$metric_name %in% metric_names,
    ,
    drop = FALSE
  ]
}

metric_score <- function(scopes, metric_names) {
  rows <- metric_rows(scopes, metric_names)

  if (nrow(rows) < 1 || !"risk_score" %in% names(rows)) {
    return(0)
  }

  score <- max(safe_number(rows$risk_score), na.rm = TRUE)

  ifelse(is.finite(score), score, 0)
}

row_value <- function(row, candidates, default = NA_real_) {
  if (nrow(row) < 1) {
    return(default)
  }

  for (candidate in candidates) {
    if (candidate %in% names(row)) {
      value <- row[[candidate]][[1]]
      if (!is.na(value)) {
        return(safe_number(value, default))
      }
    }
  }

  default
}

add_contribution <- function(contributions, score_family, rows, weight, reason_prefix) {
  if (nrow(rows) < 1) {
    return(contributions)
  }

  for (i in seq_len(nrow(rows))) {
    row <- rows[i, , drop = FALSE]
    metric_score_value <- row_value(row, c("risk_score", "metric_risk_score"), 0)
    contribution_score <- clamp01(metric_score_value * weight)

    contributions[[length(contributions) + 1]] <- list(
      profile_id = profile_id,
      dt = dt,
      run_id = run_id,
      source_gen_run_id = ifelse(source_gen_run_id > 0, source_gen_run_id, NA),
      scenario_name = scenario_name,
      baseline_mode = baseline_mode,
      baseline_window = baseline_window,
      score_family = score_family,
      input_metric_scope = as.character(row$metric_scope[[1]]),
      input_metric_name = as.character(row$metric_name[[1]]),
      current_value = row_value(row, c("current_value", "metric_value", "observed_value"), NA_real_),
      baseline_value = row_value(row, c("baseline_value", "baseline_avg", "baseline_metric_value"), NA_real_),
      delta_rate = row_value(row, c("delta_rate", "delta_ratio", "relative_delta"), NA_real_),
      metric_risk_score = metric_score_value,
      weight = weight,
      contribution_score = contribution_score,
      contribution_reason = paste0(
        reason_prefix,
        ";metric_scope=", as.character(row$metric_scope[[1]]),
        ";metric_name=", as.character(row$metric_name[[1]]),
        ";metric_risk_score=", round(metric_score_value, 6),
        ";weight=", round(weight, 6)
      )
    )
  }

  contributions
}


# ------------------------------------------------------------------
# Baseline Science Statistical Evidence Interface
# ------------------------------------------------------------------
statistical_evidence <- if (table_exists(con, "v05_baseline_science_statistical_evidence_day")) {
  read_scoped_table(con, "v05_baseline_science_statistical_evidence_day", profile_id, dt, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
stat_evidence_rows <- if (nrow(statistical_evidence) > 0) {
  statistical_evidence[statistical_evidence$evidence_domain %in% c("batch_metric_delta"), , drop = FALSE]
} else {
  data.frame()
}
statistical_evidence_score <- if (nrow(stat_evidence_rows) > 0 && "statistical_score" %in% names(stat_evidence_rows)) {
  max(safe_number(stat_evidence_rows$statistical_score), na.rm = TRUE)
} else { 0 }
statistical_evidence_score <- ifelse(is.finite(statistical_evidence_score), statistical_evidence_score, 0)
max_z_score <- if (nrow(stat_evidence_rows) > 0 && "z_score" %in% names(stat_evidence_rows)) max(abs(safe_number(stat_evidence_rows$z_score)), na.rm = TRUE) else 0
max_z_score <- ifelse(is.finite(max_z_score), max_z_score, 0)
max_historical_percentile <- if (nrow(stat_evidence_rows) > 0 && "historical_percentile" %in% names(stat_evidence_rows)) max(safe_number(stat_evidence_rows$historical_percentile), na.rm = TRUE) else 0
max_historical_percentile <- ifelse(is.finite(max_historical_percentile), max_historical_percentile, 0)
control_limit_breach_count <- if (nrow(stat_evidence_rows) > 0 && "control_limit_breach" %in% names(stat_evidence_rows)) sum(safe_number(stat_evidence_rows$control_limit_breach) > 0, na.rm = TRUE) else 0
co_movement_score <- if (nrow(stat_evidence_rows) > 0 && "co_movement_score" %in% names(stat_evidence_rows)) max(safe_number(stat_evidence_rows$co_movement_score), na.rm = TRUE) else 0
co_movement_score <- ifelse(is.finite(co_movement_score), co_movement_score, 0)
statistical_significance <- if (statistical_evidence_score >= 0.75) "critical" else if (statistical_evidence_score >= 0.55) "warning" else if (statistical_evidence_score >= 0.30) "watch" else if (statistical_evidence_score >= 0.08) "low" else "stable"

# ------------------------------------------------------------------
# Analysis
# ------------------------------------------------------------------

behavior_volume_rows <- metric_rows(
  "behavior_volume",
  c("event_count", "pv", "uv", "visit")
)

collection_rows <- metric_rows(
  "observability",
  c(
    "collection_gap_rate",
    "canonical_gap_rate",
    "web_to_canonical_gap_rate",
    "checkout_missing_rate",
    "product_missing_rate",
    "uv_gap_rate",
    "wc_hits",
    "canonical_behavior_events"
  )
)

funnel_rows <- metric_rows(
  "behavior_funnel",
  c("conversion_rate", "collector_capture_rate", "estimated_missing_rate")
)

batch_quality_rows <- metric_rows(
  "batch_quality",
  c("validation_fail_rate", "quality_issue_rate")
)

if (nrow(distribution_compare) > 0 && "distribution_shift_score" %in% names(distribution_compare)) {
  distribution_score <- max(safe_number(distribution_compare$distribution_shift_score), na.rm = TRUE)
  distribution_score <- ifelse(is.finite(distribution_score), distribution_score, 0)
} else {
  distribution_score <- 0
}

behavior_volume_score <- metric_score(
  "behavior_volume",
  c("event_count", "pv", "uv", "visit")
)

collection_score <- metric_score(
  "observability",
  c(
    "collection_gap_rate",
    "canonical_gap_rate",
    "web_to_canonical_gap_rate",
    "checkout_missing_rate",
    "product_missing_rate",
    "uv_gap_rate"
  )
)

collector_count_score <- metric_score(
  "observability",
  c("wc_hits", "canonical_behavior_events")
)

funnel_score <- metric_score(
  "behavior_funnel",
  c("conversion_rate", "collector_capture_rate", "estimated_missing_rate")
)

identity_score <- 0

mapping_score <- clamp01(
  1 - pick_number(batch_measurement, "mapping_coverage")
)

batch_quality_score <- metric_score(
  "batch_quality",
  c("validation_fail_rate", "quality_issue_rate")
)

contributions <- list()

contributions <- add_contribution(
  contributions,
  "behavior_distortion",
  behavior_volume_rows,
  1.00,
  "behavior volume delta drives observed batch KPI distortion"
)

contributions <- add_contribution(
  contributions,
  "behavior_distortion",
  collection_rows,
  1.00,
  "collection loss can reduce observed behavior volume"
)

contributions <- add_contribution(
  contributions,
  "conversion_distortion",
  funnel_rows,
  1.00,
  "funnel metric delta drives conversion distortion"
)

contributions <- add_contribution(
  contributions,
  "conversion_distortion",
  collection_rows,
  0.70,
  "collection loss can make conversion KPI appear lower"
)

visit_rows <- metric_rows(
  "behavior_volume",
  c("visit", "uv", "pv")
)

contributions <- add_contribution(
  contributions,
  "session_fragmentation",
  visit_rows,
  1.00,
  "visit and session-like metric delta drives session fragmentation"
)

contributions <- add_contribution(
  contributions,
  "session_fragmentation",
  collection_rows,
  0.45,
  "collection loss can fragment observed session continuity"
)

contributions <- add_contribution(
  contributions,
  "batch_quality",
  batch_quality_rows,
  1.00,
  "batch quality diagnostic metric contributes to batch quality risk"
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
    metric_score("behavior_volume", c("visit")),
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
    batch_quality_score,
    statistical_evidence_score
  )
)

# Baseline runs are reference-producing executions.
# Small self-reference noise from distribution/baseline snapshots must not be
# emitted as batch distortion evidence. Scenario runs still use the same logic.
if (scenario_name == "baseline") {
  behavior_distortion_score <- 0
  conversion_distortion_score <- 0
  session_fragmentation_score <- 0
  identity_score <- 0
  mapping_score <- 0
  batch_quality_score <- 0
  collection_score <- 0
  collector_count_score <- 0
  distribution_score <- 0
  overall_score <- 0
  statistical_evidence_score <- 0
  max_z_score <- 0
  max_historical_percentile <- 0
  control_limit_breach_count <- 0
  co_movement_score <- 0
  statistical_significance <- "stable"
  contributions <- list()
}

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

analysis_status <- if (baseline_status == "BASELINE_MISSING_REVIEW" && overall_score <= 0) {
  "BASELINE_MISSING_REVIEW"
} else {
  score_status(overall_score, warn = 0.20, high = 0.60)
}

top_contribution <- if (length(contributions) > 0) {
  scores <- vapply(contributions, function(row) safe_number(row$contribution_score), numeric(1))
  contributions[[which.max(scores)]]
} else {
  list(score_family = "none", input_metric_name = "none", contribution_score = 0)
}

analysis_reason <- paste0(
  "baseline_mode=", baseline_mode,
  ";baseline_window=", baseline_window,
  ";behavior_volume_score=", round(behavior_volume_score, 6),
  ";collection_score=", round(collection_score, 6),
  ";collector_count_score=", round(collector_count_score, 6),
  ";distribution_score=", round(distribution_score, 6),
  ";funnel_score=", round(funnel_score, 6),
  ";top_contribution_family=", top_contribution$score_family,
  ";top_contribution_metric=", top_contribution$input_metric_name,
  ";top_contribution_score=", round(safe_number(top_contribution$contribution_score), 6),
  ";statistical_evidence_score=", round(statistical_evidence_score, 6),
  ";max_z_score=", round(max_z_score, 6),
  ";historical_percentile=", round(max_historical_percentile, 4),
  ";control_limit_breach_count=", control_limit_breach_count,
  ";co_movement_score=", round(co_movement_score, 6),
  ";statistical_significance=", statistical_significance
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
    batch_overall_analysis_score = overall_score,
    overall_batch_behavior_score = overall_score,
    statistical_evidence_score = statistical_evidence_score,
    max_z_score = max_z_score,
    max_historical_percentile = max_historical_percentile,
    control_limit_breach_count = control_limit_breach_count,
    co_movement_score = co_movement_score,
    statistical_significance = statistical_significance,
    analysis_status = analysis_status,
    baseline_status = baseline_status,
    analysis_reason = analysis_reason
  )
)

if (table_exists(con, "v05_batch_score_contribution_day")) {
  delete_scoped_rows(
    con,
    "v05_batch_score_contribution_day",
    profile_id,
    dt,
    run_id,
    NULL,
    scenario_name
  )

  for (row in contributions) {
    insert_schema_aware(
      con,
      "v05_batch_score_contribution_day",
      row
    )
  }
}

# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(
  sprintf(
    "[R_BATCH_BEHAVIOR_ANALYSIS_V05_INTERFACE] profile=%s dt=%s run_id=%s dominant=%s overall=%.6f behavior=%.6f conversion=%.6f session=%.6f collection=%.6f contribution_rows=%d top_family=%s top_metric=%s top_score=%.6f status=%s baseline_status=%s\n",
    profile_id,
    dt,
    run_id,
    dominant_batch_signal,
    overall_score,
    behavior_distortion_score,
    conversion_distortion_score,
    session_fragmentation_score,
    collection_score,
    length(contributions),
    top_contribution$score_family,
    top_contribution$input_metric_name,
    safe_number(top_contribution$contribution_score),
    analysis_status,
    baseline_status
  )
)
