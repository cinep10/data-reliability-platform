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

metric_delta <- read_scoped_table(
  con,
  "v05_batch_metric_delta_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

batch_analysis <- read_first_scoped_row(
  con,
  "r_batch_behavior_analysis_day",
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

metric_score <- function(scope, name) {
  if (nrow(metric_delta) < 1 || !"risk_score" %in% names(metric_delta)) {
    return(0)
  }

  rows <- metric_delta[
    metric_delta$metric_scope %in% scope &
      metric_delta$metric_name %in% name,
  ]

  if (nrow(rows) < 1) {
    return(0)
  }

  score <- max(safe_number(rows$risk_score), na.rm = TRUE)

  ifelse(is.finite(score), score, 0)
}

metric_values <- c(
  event_count_delta = metric_score("behavior_volume", "event_count"),
  pv_delta = metric_score("behavior_volume", "pv"),
  uv_delta = metric_score("behavior_volume", "uv"),
  visit_delta = metric_score("behavior_volume", "visit"),
  collection_gap = metric_score("observability", "collection_gap_rate"),
  canonical_gap = metric_score("observability", "canonical_gap_rate"),
  checkout_missing = metric_score("observability", "checkout_missing_rate"),
  product_missing = metric_score("observability", "product_missing_rate"),
  behavior_distortion = pick_number(batch_analysis, "behavior_distortion_score"),
  conversion_distortion = pick_number(batch_analysis, "conversion_distortion_score"),
  session_fragmentation = pick_number(batch_analysis, "session_fragmentation_score"),
  observability_gap = clamp01(
    max(
      pick_number(observability, "collection_gap_rate") * 3,
      pick_number(observability, "canonical_gap_rate") * 3,
      pick_number(observability, "web_to_canonical_gap_rate") * 3,
      na.rm = TRUE
    )
  )
)

metric_names <- names(metric_values)
metric_values <- safe_number(metric_values)
names(metric_values) <- metric_names

metric_values <- metric_values[
  is.finite(metric_values) &
    !is.na(metric_values)
]

metric_values <- metric_values[
  !is.na(names(metric_values)) &
    nzchar(names(metric_values))
]

# Keep zero-valued metrics as valid evidence. They are needed so that
# correlation/co-movement diagnostics can still write a neutral row for
# baseline runs. Only fail-safe when fewer than two named metrics exist.
if (length(metric_values) < 2) {
  pair_scores <- list(
    list(
      metric_pair = "insufficient_metrics",
      corr_value = 0,
      baseline_corr_value = 0,
      corr_delta = 0,
      anomaly_score = 0,
      anomaly_status = "INSUFFICIENT_METRICS",
      analysis_reason = paste0(
        "baseline_mode=", baseline_mode,
        ";baseline_window=", baseline_window,
        ";metric_count=", length(metric_values),
        ";reason=need_at_least_two_named_metrics_for_pair_diagnostic"
      )
    )
  )
} else {
  pair_names <- combn(
    names(metric_values),
    2,
    FUN = function(pair) paste(pair, collapse = "__")
  )

  pair_scores <- lapply(pair_names, function(pair_name) {
    parts <- strsplit(pair_name, "__", fixed = TRUE)[[1]]
    left <- metric_values[[parts[[1]]]]
    right <- metric_values[[parts[[2]]]]
    coupled_score <- clamp01(sqrt(abs(left * right)))
    directional_gap <- abs(left - right)

    list(
      metric_pair = pair_name,
      corr_value = coupled_score,
      baseline_corr_value = 0,
      corr_delta = directional_gap,
      anomaly_score = coupled_score,
      anomaly_status = score_status(coupled_score, warn = 0.20, high = 0.60),
      analysis_reason = paste0(
        "baseline_mode=", baseline_mode,
        ";baseline_window=", baseline_window,
        ";left=", round(left, 6),
        ";right=", round(right, 6),
        ";coupled_score=", round(coupled_score, 6),
        ";directional_gap=", round(directional_gap, 6)
      )
    )
  })
}

max_score <- max(
  vapply(pair_scores, function(row) safe_number(row$anomaly_score), numeric(1)),
  na.rm = TRUE
)

max_score <- ifelse(is.finite(max_score), max_score, 0)

# ------------------------------------------------------------------
# Save Result
# ------------------------------------------------------------------

delete_scoped_rows(
  con,
  "r_metric_correlation_anomaly_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

for (row in pair_scores) {
  insert_schema_aware(
    con,
    "r_metric_correlation_anomaly_day",
    list(
      profile_id = profile_id,
      dt = dt,
      run_id = run_id,
      scenario_name = scenario_name,
      metric_pair = row$metric_pair,
      corr_value = row$corr_value,
      baseline_corr_value = row$baseline_corr_value,
      corr_delta = row$corr_delta,
      anomaly_score = row$anomaly_score,
      anomaly_status = row$anomaly_status,
      analysis_reason = row$analysis_reason
    )
  )
}

# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(
  sprintf(
    "[R_CORRELATION_V05_INTERFACE] pairs=%d max_score=%.6f status=%s baseline_window=%s\n",
    length(pair_scores),
    max_score,
    score_status(max_score, warn = 0.20, high = 0.60),
    baseline_window
  )
)
