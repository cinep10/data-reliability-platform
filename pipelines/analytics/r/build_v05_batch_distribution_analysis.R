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

source_gen_run_id_raw <- arg_value(args, "--source-gen-run-id", "")
source_gen_run_id <- if (nzchar(source_gen_run_id_raw)) {
  suppressWarnings(as.integer(source_gen_run_id_raw))
} else {
  NA_integer_
}
source_gen_run_id_for_scope <- if (is.na(source_gen_run_id) || source_gen_run_id <= 0) NULL else source_gen_run_id

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

distribution_compare <- read_scoped_table(
  con,
  "v05_batch_behavior_distribution_compare_day",
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


# ------------------------------------------------------------------
# Baseline Science Statistical Evidence Interface
# ------------------------------------------------------------------
statistical_evidence <- if (table_exists(con, "v05_baseline_science_statistical_evidence_day")) {
  read_scoped_table(con, "v05_baseline_science_statistical_evidence_day", profile_id, dt, run_id, source_gen_run_id_for_scope, scenario_name)
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

ratio_shift_score <- if (
  nrow(distribution_compare) > 0 &&
    "distribution_shift_score" %in% names(distribution_compare)
) {
  max(safe_number(distribution_compare$distribution_shift_score), na.rm = TRUE)
} else {
  0
}

ratio_shift_score <- ifelse(is.finite(ratio_shift_score), ratio_shift_score, 0)

volume_shift_score <- 0

if (nrow(metric_delta) > 0 && "risk_score" %in% names(metric_delta)) {
  volume_rows <- metric_delta[
    metric_delta$metric_scope %in% c("behavior_volume", "observability") &
      metric_delta$metric_name %in% c(
        "event_count",
        "pv",
        "uv",
        "visit",
        "wc_hits",
        "canonical_behavior_events",
        "collection_gap_rate",
        "canonical_gap_rate"
      ),
  ]

  if (nrow(volume_rows) > 0) {
    volume_shift_score <- max(safe_number(volume_rows$risk_score), na.rm = TRUE)
    volume_shift_score <- ifelse(is.finite(volume_shift_score), volume_shift_score, 0)
  }
}

batch_distribution_score <- clamp01(
  max(
    ratio_shift_score,
    volume_shift_score,
    statistical_evidence_score
  )
)

# Baseline executions build reference data. Do not let reference-generation
# self-noise appear as distribution WARN evidence.
if (scenario_name == "baseline") {
  ratio_shift_score <- 0
  volume_shift_score <- 0
  batch_distribution_score <- 0
  statistical_evidence_score <- 0
  max_z_score <- 0
  max_historical_percentile <- 0
  control_limit_breach_count <- 0
  co_movement_score <- 0
  statistical_significance <- "stable"
}

status_values <- character()

if (nrow(distribution_compare) > 0 && "baseline_status" %in% names(distribution_compare)) {
  status_values <- c(status_values, unique(as.character(distribution_compare$baseline_status)))
}

if (nrow(metric_delta) > 0 && "baseline_status" %in% names(metric_delta)) {
  status_values <- c(status_values, unique(as.character(metric_delta$baseline_status)))
}

analysis_status <- if (any(status_values == "BASELINE_MISSING_REVIEW", na.rm = TRUE)) {
  "BASELINE_MISSING_REVIEW"
} else {
  score_status(batch_distribution_score, warn = 0.20, high = 0.60)
}

analysis_reason <- paste0(
  "compare_rows=", nrow(distribution_compare),
  ";source_gen_run_id=", ifelse(is.null(source_gen_run_id_for_scope), "NULL", as.character(source_gen_run_id_for_scope)),
  ";metric_delta_rows=", nrow(metric_delta),
  ";ratio_shift_score=", round(ratio_shift_score, 6),
  ";volume_shift_score=", round(volume_shift_score, 6),
  ";baseline_status=", paste(unique(status_values), collapse = ","),
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
  "r_batch_distribution_analysis_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

insert_schema_aware(
  con,
  "r_batch_distribution_analysis_day",
  list(
    profile_id = profile_id,
    dt = dt,
    run_id = run_id,
    scenario_name = scenario_name,
    dimension_name = "all",
    ratio_shift_score = ratio_shift_score,
    volume_shift_score = volume_shift_score,
    max_ratio_delta = ratio_shift_score,
    max_distribution_shift_score = batch_distribution_score,
    distribution_risk_score = batch_distribution_score,
    batch_distribution_score = batch_distribution_score,
    batch_distribution_risk_score = batch_distribution_score,
    max_distribution_score = batch_distribution_score,
    distribution_signal = ifelse(batch_distribution_score >= 0.20, "batch_distribution_shift", "none"),
    analysis_status = analysis_status,
    baseline_window = baseline_window,
    statistical_evidence_score = statistical_evidence_score,
    max_z_score = max_z_score,
    max_historical_percentile = max_historical_percentile,
    control_limit_breach_count = control_limit_breach_count,
    co_movement_score = co_movement_score,
    statistical_significance = statistical_significance,
    analysis_reason = analysis_reason
  )
)

# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(
  sprintf(
    "[OK] build_v05_batch_distribution_analysis scenario=%s rows=%d ratio_score=%.6f volume_score=%.6f max_score=%.6f status=%s baseline_window=%s\n",
    scenario_name,
    nrow(distribution_compare),
    ratio_shift_score,
    volume_shift_score,
    batch_distribution_score,
    analysis_status,
    baseline_window
  )
)
