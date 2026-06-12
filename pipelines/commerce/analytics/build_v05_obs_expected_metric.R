#!/usr/bin/env Rscript

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))

args <- commandArgs(trailingOnly = TRUE)
profile_id <- arg_value(args, "--profile-id")
target_date <- arg_value(args, "--target-date")
scenario_name <- arg_value(args, "--scenario-name", "baseline")
run_id <- as.integer(arg_value(args, "--run-id", "0"))
source_gen_run_id <- as.integer(arg_value(args, "--source-gen-run-id", "0"))
baseline_window <- arg_value(args, "--baseline-window", "30d")
baseline_scenario <- arg_value(args, "--baseline-scenario", "baseline")
recent_days <- as.integer(arg_value(args, "--recent-days", "7"))
min_sample_days <- as.integer(arg_value(args, "--min-sample-days", "3"))

num <- function(x, default = NA_real_) {
  y <- suppressWarnings(as.numeric(x))
  if (length(y) == 0 || is.na(y) || !is.finite(y)) return(default)
  y
}

safe_mean <- function(x) {
  x <- suppressWarnings(as.numeric(x))
  x <- x[is.finite(x)]
  if (length(x) < 1) return(NA_real_)
  mean(x)
}

pick_stat <- function(stats, dtype, dkey, metric, btype) {
  s <- stats[stats$dimension_type == dtype & stats$dimension_key == dkey & stats$metric_name == metric & stats$baseline_type == btype, , drop = FALSE]
  if (nrow(s) < 1) return(NULL)
  s[order(-s$quality_score), ][1, , drop = FALSE]
}

quality_for_dimension <- function(dtype, web_value) {
  w <- num(web_value, 0)
  if (dtype %in% c("url", "client") && w < 100) return("low_volume")
  if (dtype %in% c("app_version", "sdk_version", "app_sdk") && w < 50) return("low_volume")
  "ok"
}

status_for_model <- function(selected_days, recent_days_n) {
  if (selected_days <= 0) return("missing_baseline")
  if (selected_days < min_sample_days) return("low_sample")
  if (recent_days_n < min(3, min_sample_days)) return("low_recent_sample")
  "usable"
}

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

for (t in c("v05_obs_baseline_feature_snapshot_day", "v05_obs_baseline_stat_profile_day", "v05_obs_expected_metric_day")) {
  if (!table_exists(con, t)) stop(paste("missing", t))
}

DBI::dbExecute(con, "DELETE FROM v05_obs_expected_metric_day WHERE profile_id=? AND target_date=? AND scenario_name=? AND run_id=? AND source_gen_run_id=? AND baseline_window=?", list(profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window))

features <- DBI::dbGetQuery(con, "
  SELECT * FROM v05_obs_baseline_feature_snapshot_day
  WHERE profile_id=? AND target_date=? AND scenario_name=? AND run_id=? AND source_gen_run_id=?",
  params = list(profile_id, target_date, scenario_name, run_id, source_gen_run_id)
)

stats <- DBI::dbGetQuery(con, "
  SELECT * FROM v05_obs_baseline_stat_profile_day
  WHERE profile_id=? AND target_date=? AND baseline_window=? AND baseline_scenario_name=?",
  params = list(profile_id, target_date, baseline_window, baseline_scenario)
)

recent_start <- as.character(as.Date(target_date) - max(0, recent_days - 1))
recent <- DBI::dbGetQuery(con, "
  SELECT target_date, dimension_type, dimension_key, metric_name, metric_value
  FROM v05_obs_baseline_feature_snapshot_day
  WHERE profile_id=? AND scenario_name=? AND target_date BETWEEN ? AND ?",
  params = list(profile_id, baseline_scenario, recent_start, target_date)
)

n <- 0L
if (nrow(features) > 0 && nrow(stats) > 0) {
  for (i in seq_len(nrow(features))) {
    f <- features[i, , drop = FALSE]
    dtype <- as.character(f$dimension_type[[1]])
    dkey <- as.character(f$dimension_key[[1]])
    metric <- as.character(f$metric_name[[1]])
    current <- num(f$metric_value[[1]])

    rolling <- pick_stat(stats, dtype, dkey, metric, "rolling_30d")
    weekday <- pick_stat(stats, dtype, dkey, metric, "same_weekday")

    rolling_mean <- if (!is.null(rolling)) num(rolling$mean_value[[1]]) else NA_real_
    rolling_sd <- if (!is.null(rolling)) num(rolling$sd_value[[1]], 0) else 0
    rolling_days <- if (!is.null(rolling)) as.integer(num(rolling$sample_days[[1]], 0)) else 0L
    rolling_q <- if (!is.null(rolling)) num(rolling$quality_score[[1]], 0) else 0

    weekday_mean <- if (!is.null(weekday)) num(weekday$mean_value[[1]]) else NA_real_
    weekday_days <- if (!is.null(weekday)) as.integer(num(weekday$sample_days[[1]], 0)) else 0L
    weekday_q <- if (!is.null(weekday)) num(weekday$quality_score[[1]], 0) else 0

    rf <- recent[recent$dimension_type == dtype & recent$dimension_key == dkey & recent$metric_name == metric, , drop = FALSE]
    recent_mean <- if (nrow(rf) > 0) safe_mean(rf$metric_value) else NA_real_
    recent_sample_days <- if (nrow(rf) > 0) length(unique(as.character(rf$target_date))) else 0L

    selected_mean <- rolling_mean
    selected_days <- rolling_days
    selected_q <- rolling_q
    weekday_component <- rolling_mean
    if (!is.na(weekday_mean) && weekday_days >= min_sample_days) {
      weekday_component <- weekday_mean
      selected_mean <- weekday_mean
      selected_days <- weekday_days
      selected_q <- weekday_q
    }
    if (is.na(recent_mean)) recent_mean <- selected_mean

    vals <- c(rolling_mean, weekday_component, recent_mean)
    weights <- c(0.50, 0.30, 0.20)
    ok <- is.finite(vals)
    expected <- NA_real_
    if (any(ok)) expected <- sum(vals[ok] * weights[ok]) / sum(weights[ok])

    lower <- if (is.na(expected)) NA_real_ else max(0, expected - 3 * rolling_sd)
    upper <- if (is.na(expected)) NA_real_ else expected + 3 * rolling_sd
    delta <- if (!is.na(current) && !is.na(expected)) current - expected else NA_real_
    delta_rate <- if (!is.na(delta) && !is.na(expected) && abs(expected) >= 1e-12) delta / abs(expected) else if (!is.na(delta) && abs(delta) < 1e-12) 0 else NA_real_
    breach <- if (!is.na(current) && !is.na(upper) && current > upper) 1L else 0L

    model_status <- status_for_model(selected_days, recent_sample_days)
    dim_status <- quality_for_dimension(dtype, f$webserver_value[[1]])
    confidence <- min(1, max(0, selected_q) * 0.7 + min(1, recent_sample_days / max(1, recent_days)) * 0.3)
    quality_status <- if (model_status == "usable" && dim_status == "ok") "usable" else if (model_status == "missing_baseline") "missing" else "low_quality"

    DBI::dbExecute(con, "
      INSERT INTO v05_obs_expected_metric_day
        (profile_id,target_date,scenario_name,run_id,source_gen_run_id,baseline_window,baseline_scenario_name,dimension_type,dimension_key,metric_name,current_value,rolling_mean,weekday_mean,recent_7d_mean,selected_baseline_mean,expected_value,expected_lower,expected_upper,expected_delta,expected_delta_rate,expected_breach,rolling_sample_days,weekday_sample_days,recent_sample_days,selected_sample_days,baseline_quality_score,expected_confidence,model_status,quality_status,dimension_quality_status,expected_model_name,expected_model_version,source_table,detail_json)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON DUPLICATE KEY UPDATE current_value=VALUES(current_value), rolling_mean=VALUES(rolling_mean), weekday_mean=VALUES(weekday_mean), recent_7d_mean=VALUES(recent_7d_mean), selected_baseline_mean=VALUES(selected_baseline_mean), expected_value=VALUES(expected_value), expected_lower=VALUES(expected_lower), expected_upper=VALUES(expected_upper), expected_delta=VALUES(expected_delta), expected_delta_rate=VALUES(expected_delta_rate), expected_breach=VALUES(expected_breach), rolling_sample_days=VALUES(rolling_sample_days), weekday_sample_days=VALUES(weekday_sample_days), recent_sample_days=VALUES(recent_sample_days), selected_sample_days=VALUES(selected_sample_days), baseline_quality_score=VALUES(baseline_quality_score), expected_confidence=VALUES(expected_confidence), model_status=VALUES(model_status), quality_status=VALUES(quality_status), dimension_quality_status=VALUES(dimension_quality_status), source_table=VALUES(source_table), detail_json=VALUES(detail_json)",
      params = list(profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window, baseline_scenario, dtype, dkey, metric, current, rolling_mean, weekday_mean, recent_mean, selected_mean, expected, lower, upper, delta, delta_rate, breach, rolling_days, weekday_days, recent_sample_days, selected_days, selected_q, confidence, model_status, quality_status, dim_status, "hybrid_expected_v1", "v1", as.character(f$source_table[[1]]), jsonlite::toJSON(list(recent_days = recent_days, formula = "0.50*rolling + 0.30*weekday_or_rolling + 0.20*recent", webserver_value = num(f$webserver_value[[1]], 0), wc_value = num(f$wc_value[[1]], 0)), auto_unbox = TRUE))
    )
    n <- n + 1L
  }
}
cat(sprintf("[OK] build_v05_obs_expected_metric rows=%d recent_days=%d\n", n, recent_days))
