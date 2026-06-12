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

contribution <- read_scoped_table(
  con,
  "v05_batch_score_contribution_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)


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

max_metric_score <- 0

if (nrow(metric_delta) > 0 && "risk_score" %in% names(metric_delta)) {
  max_metric_score <- max(safe_number(metric_delta$risk_score), na.rm = TRUE)
  max_metric_score <- ifelse(is.finite(max_metric_score), max_metric_score, 0)
}

contribution_max_score <- 0

top_contribution <- list(
  score_family = "none",
  input_metric_name = "none",
  contribution_score = 0
)

if (nrow(contribution) > 0 && "contribution_score" %in% names(contribution)) {
  contribution_scores <- safe_number(contribution$contribution_score)
  contribution_max_score <- max(contribution_scores, na.rm = TRUE)
  contribution_max_score <- ifelse(is.finite(contribution_max_score), contribution_max_score, 0)

  contribution$.score_for_rank <- contribution_scores
  contribution$.family_rank <- ifelse(contribution$score_family == "behavior_distortion", 1,
    ifelse(contribution$score_family == "collection_effect", 2,
      ifelse(contribution$score_family == "conversion_distortion", 3,
        ifelse(contribution$score_family == "session_fragmentation", 4, 9)
      )
    )
  )
  contribution$.metric_rank <- ifelse(contribution$input_metric_name %in% c("event_count", "pv", "pv_count", "pageview_count"), 1, 5)

  ordered_contribution <- contribution[
    order(
      -contribution$.score_for_rank,
      contribution$.family_rank,
      contribution$.metric_rank,
      contribution$input_metric_name
    ),
    ,
    drop = FALSE
  ]

  top_contribution <- list(
    score_family = as.character(ordered_contribution$score_family[[1]]),
    input_metric_name = as.character(ordered_contribution$input_metric_name[[1]]),
    contribution_score = safe_number(ordered_contribution$.score_for_rank[[1]])
  )
}

collection_contribution_score <- 0

if (nrow(contribution) > 0 && all(c("score_family", "contribution_score") %in% names(contribution))) {
  collection_rows <- contribution[
    contribution$score_family %in% c("collection_effect", "behavior_distortion", "conversion_distortion", "session_fragmentation") &
      contribution$input_metric_scope %in% c("observability"),
    ,
    drop = FALSE
  ]

  if (nrow(collection_rows) > 0) {
    collection_contribution_score <- max(safe_number(collection_rows$contribution_score), na.rm = TRUE)
    collection_contribution_score <- ifelse(is.finite(collection_contribution_score), collection_contribution_score, 0)
  }
}

collection_score <- clamp01(
  max(
    pick_number(observability, "collection_gap_rate") * 3,
    pick_number(observability, "canonical_gap_rate") * 3,
    pick_number(observability, "web_to_canonical_gap_rate") * 3,
    pick_number(observability, "checkout_missing_rate") * 2,
    pick_number(observability, "product_missing_rate") * 2,
    pick_number(observability, "uv_gap_rate") * 2,
    collection_contribution_score
  )
)

behavior_analysis_score <- clamp01(
  max(
    pick_number(batch_analysis, c("batch_overall_analysis_score", "overall_batch_behavior_score")),
    pick_number(batch_analysis, "behavior_distortion_score"),
    pick_number(batch_analysis, "conversion_distortion_score"),
    pick_number(batch_analysis, "session_fragmentation_score")
  )
)

batch_distribution_risk_score <- clamp01(
  max(
    pick_number(distribution_analysis, c(
      "distribution_risk_score",
      "batch_distribution_score",
      "batch_distribution_risk_score",
      "max_distribution_score"
    )),
    max_metric_score * 0.50
  )
)

time_pattern_score <- 0
if (table_exists(con, "r_metric_time_pattern_anomaly_day")) {
  time_pattern <- read_first_scoped_row(
    con,
    "r_metric_time_pattern_anomaly_day",
    profile_id,
    dt,
    run_id,
    NULL,
    scenario_name
  )
  time_pattern_score <- pick_number(time_pattern, "anomaly_score")
}

correlation_score <- 0
if (table_exists(con, "r_metric_correlation_anomaly_day")) {
  correlation_rows <- read_scoped_table(
    con,
    "r_metric_correlation_anomaly_day",
    profile_id,
    dt,
    run_id,
    NULL,
    scenario_name
  )
  if (nrow(correlation_rows) > 0 && "anomaly_score" %in% names(correlation_rows)) {
    correlation_score <- max(safe_number(correlation_rows$anomaly_score), na.rm = TRUE)
    correlation_score <- ifelse(is.finite(correlation_score), correlation_score, 0)
  }
}

batch_score <- clamp01(
  max(
    behavior_analysis_score,
    batch_distribution_risk_score,
    contribution_max_score,
    max_metric_score * 0.50,
    statistical_evidence_score
  )
)

overall_score <- clamp01(
  max(
    batch_score,
    collection_score
  )
)

anomaly_signal <- if (collection_score >= 0.60 && batch_score >= 0.60) {
  "observed_kpi_distortion_from_collection_loss"
} else if (collection_score >= 0.20) {
  "observability_collection_anomaly"
} else if (batch_score >= 0.20) {
  "batch_behavior_distortion"
} else {
  "none"
}

anomaly_status <- score_status(
  overall_score,
  warn = 0.20,
  high = 0.60
)

analysis_reason <- paste0(
  "baseline_mode=", baseline_mode,
  ";baseline_window=", baseline_window,
  ";signal=", anomaly_signal,
  ";collection_score=", round(collection_score, 6),
  ";batch_score=", round(batch_score, 6),
  ";behavior_analysis_score=", round(behavior_analysis_score, 6),
  ";batch_distribution_risk_score=", round(batch_distribution_risk_score, 6),
  ";time_pattern_score=", round(time_pattern_score, 6),
  ";correlation_score=", round(correlation_score, 6),
  ";metric_delta_score=", round(max_metric_score, 6),
  ";contribution_max_score=", round(contribution_max_score, 6),
  ";top_contribution_family=", top_contribution$score_family,
  ";top_contribution_metric=", top_contribution$input_metric_name,
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
    source_gen_run_id = ifelse(source_gen_run_id > 0, source_gen_run_id, NA),
    scenario_name = scenario_name,
    anomaly_signal = anomaly_signal,
    anomaly_score = overall_score,
    batch_distribution_risk_score = batch_distribution_risk_score,
    behavior_analysis_score = behavior_analysis_score,
    observability_collection_score = collection_score,
    time_pattern_score = time_pattern_score,
    correlation_score = correlation_score,
    contribution_max_score = contribution_max_score,
    dominant_contribution_family = top_contribution$score_family,
    dominant_contribution_metric = top_contribution$input_metric_name,
    statistical_evidence_score = statistical_evidence_score,
    max_z_score = max_z_score,
    max_historical_percentile = max_historical_percentile,
    control_limit_breach_count = control_limit_breach_count,
    co_movement_score = co_movement_score,
    statistical_significance = statistical_significance,
    anomaly_status = anomaly_status,
    analysis_reason = analysis_reason
  )
)

# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(
  sprintf(
    "[OK] build_v05_batch_behavior_anomaly scenario=%s signal=%s score=%.6f batch_score=%.6f collection_score=%.6f contribution_score=%.6f top_family=%s top_metric=%s status=%s\n",
    scenario_name,
    anomaly_signal,
    overall_score,
    batch_score,
    collection_score,
    contribution_max_score,
    top_contribution$score_family,
    top_contribution$input_metric_name,
    anomaly_status
  )
)
