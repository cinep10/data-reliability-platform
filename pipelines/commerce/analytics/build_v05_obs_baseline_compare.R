#!/usr/bin/env Rscript

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))

args <- commandArgs(trailingOnly = TRUE)
profile_id <- arg_value(args, "--profile-id")
target_date <- arg_value(args, "--target-date")
scenario_name <- arg_value(args, "--scenario-name")
run_id <- as.integer(arg_value(args, "--run-id", "0"))
source_gen_run_id <- as.integer(arg_value(args, "--source-gen-run-id", "0"))
baseline_window <- arg_value(args, "--baseline-window", "30d")
baseline_scenario <- arg_value(args, "--baseline-scenario", "baseline")

num <- function(x) {
  y <- suppressWarnings(as.numeric(x))
  if (length(y) == 0 || is.na(y) || !is.finite(y)) return(NA_real_)
  y
}

percentile_band <- function(value, stat) {
  v <- num(value)
  if (is.na(v)) return("unknown")
  p99 <- num(stat$p99_value); p95 <- num(stat$p95_value); p90 <- num(stat$p90_value); p75 <- num(stat$p75_value)
  if (!is.na(p99) && v >= p99) return("p99_plus")
  if (!is.na(p95) && v >= p95) return("p95_plus")
  if (!is.na(p90) && v >= p90) return("p90_plus")
  if (!is.na(p75) && v >= p75) return("p75_plus")
  "normal_band"
}

severity_value <- function(value, z, breach, sample_days) {
  if (is.na(num(value)) || sample_days <= 0) return("unknown")
  zz <- abs(num(z)); if (is.na(zz)) zz <- 0
  if (breach == 1 && zz >= 5) return("critical")
  if (breach == 1 || zz >= 3) return("warning")
  if (zz >= 2) return("watch")
  "normal"
}

upsert_compare <- function(con, feature, stat) {
  current <- num(feature$metric_value)
  meanv <- num(stat$mean_value)
  sdv <- num(stat$sd_value)
  upper <- num(stat$upper_control_limit)
  delta <- if (!is.na(current) && !is.na(meanv)) current - meanv else NA_real_
  z <- NA_real_
  if (!is.na(delta)) {
    if (is.na(sdv) || abs(sdv) < 1e-12) z <- if (abs(delta) < 1e-12) 0 else 999 else z <- delta / sdv
  }
  breach <- if (!is.na(current) && !is.na(upper) && current > upper) 1L else 0L
  sample_days <- as.integer(ifelse(is.na(stat$sample_days), 0, stat$sample_days))
  sev <- severity_value(current, z, breach, sample_days)
  DBI::dbExecute(con, "
    INSERT INTO v05_obs_baseline_compare_day
      (profile_id,target_date,scenario_name,run_id,source_gen_run_id,baseline_window,baseline_scenario_name,selected_baseline_type,dimension_type,dimension_key,metric_name,current_value,baseline_mean,baseline_sd,baseline_p95,baseline_upper_control_limit,baseline_delta,z_score,percentile_band,control_limit_breach,baseline_quality_score,sample_days,severity,baseline_status,detail_json)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON DUPLICATE KEY UPDATE selected_baseline_type=VALUES(selected_baseline_type), current_value=VALUES(current_value), baseline_mean=VALUES(baseline_mean), baseline_sd=VALUES(baseline_sd), baseline_p95=VALUES(baseline_p95), baseline_upper_control_limit=VALUES(baseline_upper_control_limit), baseline_delta=VALUES(baseline_delta), z_score=VALUES(z_score), percentile_band=VALUES(percentile_band), control_limit_breach=VALUES(control_limit_breach), baseline_quality_score=VALUES(baseline_quality_score), sample_days=VALUES(sample_days), severity=VALUES(severity), baseline_status=VALUES(baseline_status), detail_json=VALUES(detail_json)",
    params = list(profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window, baseline_scenario, stat$baseline_type, feature$dimension_type, feature$dimension_key, feature$metric_name, current, meanv, sdv, num(stat$p95_value), upper, delta, z, percentile_band(current, stat), breach, num(stat$quality_score), sample_days, sev, stat$baseline_status, jsonlite::toJSON(list(source_table = feature$source_table, feature_json = feature$source_dimension_json), auto_unbox = TRUE))
  )
}

select_stat <- function(stats, dtype, dkey, metric) {
  s <- stats[stats$dimension_type == dtype & stats$dimension_key == dkey & stats$metric_name == metric, , drop = FALSE]
  if (nrow(s) < 1) return(NULL)
  usable_weekday <- s[s$baseline_type == "same_weekday" & s$baseline_status == "usable", , drop = FALSE]
  if (nrow(usable_weekday) > 0) return(usable_weekday[order(-usable_weekday$quality_score), ][1, , drop = FALSE])
  rolling <- s[s$baseline_type == "rolling_30d", , drop = FALSE]
  if (nrow(rolling) > 0) return(rolling[order(-rolling$quality_score), ][1, , drop = FALSE])
  s[order(-s$quality_score), ][1, , drop = FALSE]
}

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

for (t in c("v05_obs_baseline_feature_snapshot_day", "v05_obs_baseline_stat_profile_day", "v05_obs_baseline_compare_day")) {
  if (!table_exists(con, t)) stop(paste("missing", t))
}

DBI::dbExecute(con, "DELETE FROM v05_obs_baseline_compare_day WHERE profile_id=? AND target_date=? AND scenario_name=? AND run_id=? AND source_gen_run_id=? AND baseline_window=?", list(profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window))

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

n <- 0L
if (nrow(features) > 0 && nrow(stats) > 0) {
  for (i in seq_len(nrow(features))) {
    f <- features[i, , drop = FALSE]
    st <- select_stat(stats, f$dimension_type[[1]], f$dimension_key[[1]], f$metric_name[[1]])
    if (is.null(st)) next
    upsert_compare(con, f, st[1, , drop = FALSE])
    n <- n + 1L
  }
}
cat(sprintf("[OK] build_v05_obs_baseline_compare rows=%d\n", n))
