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

hour_distribution <- read_scoped_table(
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

hour_distribution <- if (
  nrow(hour_distribution) > 0 &&
    "dimension_name" %in% names(hour_distribution)
) {
  hour_distribution[hour_distribution$dimension_name == "hour", , drop = FALSE]
} else {
  data.frame()
}

# ------------------------------------------------------------------
# Analysis
# ------------------------------------------------------------------

ratio_shift_score <- if (
  nrow(hour_distribution) > 0 &&
    "distribution_shift_score" %in% names(hour_distribution)
) {
  max(safe_number(hour_distribution$distribution_shift_score), na.rm = TRUE)
} else {
  0
}

ratio_shift_score <- ifelse(
  is.finite(ratio_shift_score),
  ratio_shift_score,
  0
)

count_delta_score <- if (
  nrow(hour_distribution) > 0 &&
    all(c("current_count", "baseline_count_avg") %in% names(hour_distribution))
) {
  current_count <- safe_number(hour_distribution$current_count)
  baseline_count <- safe_number(hour_distribution$baseline_count_avg)
  delta_rate <- abs(current_count - baseline_count) / pmax(abs(baseline_count), 1)
  max(clamp01(max(delta_rate, na.rm = TRUE) / 0.20), na.rm = TRUE)
} else {
  0
}

count_delta_score <- ifelse(
  is.finite(count_delta_score),
  count_delta_score,
  0
)

batch_volume_score <- 0

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
    batch_volume_score <- max(safe_number(volume_rows$risk_score), na.rm = TRUE)
  }
}

batch_volume_score <- ifelse(
  is.finite(batch_volume_score),
  batch_volume_score,
  0
)

localized_time_distortion_score <- clamp01(
  max(
    ratio_shift_score,
    count_delta_score - (batch_volume_score * 0.50)
  )
)

time_pattern_score <- clamp01(
  max(
    ratio_shift_score,
    count_delta_score,
    batch_volume_score * 0.70
  )
)

dominant_hour <- "none"
dominant_hour_delta_rate <- 0

if (
  nrow(hour_distribution) > 0 &&
    all(c("dimension_value", "current_count", "baseline_count_avg") %in% names(hour_distribution))
) {
  current_count <- safe_number(hour_distribution$current_count)
  baseline_count <- safe_number(hour_distribution$baseline_count_avg)
  hour_delta_rate <- abs(current_count - baseline_count) / pmax(abs(baseline_count), 1)
  max_idx <- which.max(hour_delta_rate)

  if (length(max_idx) > 0 && is.finite(hour_delta_rate[[max_idx]])) {
    dominant_hour <- as.character(hour_distribution$dimension_value[[max_idx]])
    dominant_hour_delta_rate <- hour_delta_rate[[max_idx]]
  }
}

baseline_status_values <- character()

if (nrow(hour_distribution) > 0 && "baseline_status" %in% names(hour_distribution)) {
  baseline_status_values <- c(
    baseline_status_values,
    unique(as.character(hour_distribution$baseline_status))
  )
}

if (nrow(metric_delta) > 0 && "baseline_status" %in% names(metric_delta)) {
  baseline_status_values <- c(
    baseline_status_values,
    unique(as.character(metric_delta$baseline_status))
  )
}

analysis_status <- if (
  any(baseline_status_values == "BASELINE_MISSING_REVIEW", na.rm = TRUE) &&
    time_pattern_score <= 0
) {
  "BASELINE_MISSING_REVIEW"
} else {
  score_status(time_pattern_score, warn = 0.20, high = 0.60)
}

analysis_reason <- paste0(
  "baseline_mode=", baseline_mode,
  ";baseline_window=", baseline_window,
  ";hour_rows=", nrow(hour_distribution),
  ";ratio_shift_score=", round(ratio_shift_score, 6),
  ";count_delta_score=", round(count_delta_score, 6),
  ";batch_volume_score=", round(batch_volume_score, 6),
  ";localized_time_distortion_score=", round(localized_time_distortion_score, 6),
  ";dominant_hour=", dominant_hour,
  ";dominant_hour_delta_rate=", round(dominant_hour_delta_rate, 6),
  ";baseline_status=", paste(unique(baseline_status_values), collapse = ",")
)

# ------------------------------------------------------------------
# Save Result
# ------------------------------------------------------------------

delete_scoped_rows(
  con,
  "r_metric_time_pattern_anomaly_day",
  profile_id,
  dt,
  run_id,
  NULL,
  scenario_name
)

insert_schema_aware(
  con,
  "r_metric_time_pattern_anomaly_day",
  list(
    profile_id = profile_id,
    dt = dt,
    run_id = run_id,
    scenario_name = scenario_name,
    metric_name = "hourly_behavior_volume_and_ratio_shift",
    grain = "hour",
    observed_value = time_pattern_score,
    baseline_value = 0,
    baseline_sd = 0,
    z_score = 0,
    delta_value = time_pattern_score,
    delta_ratio = time_pattern_score,
    anomaly_score = time_pattern_score,
    anomaly_status = analysis_status,
    ratio_shift_score = ratio_shift_score,
    count_delta_score = count_delta_score,
    volume_delta_score = batch_volume_score,
    localized_time_distortion_score = localized_time_distortion_score,
    dominant_hour = dominant_hour,
    dominant_hour_delta_rate = dominant_hour_delta_rate,
    analysis_reason = analysis_reason
  )
)

# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(
  sprintf(
    "[R_TIME_PATTERN_V05_INTERFACE] rows=%d ratio_score=%.6f count_score=%.6f volume_score=%.6f localized_score=%.6f dominant_hour=%s score=%.6f status=%s baseline_window=%s\n",
    nrow(hour_distribution),
    ratio_shift_score,
    count_delta_score,
    batch_volume_score,
    localized_time_distortion_score,
    dominant_hour,
    time_pattern_score,
    analysis_status,
    baseline_window
  )
)
