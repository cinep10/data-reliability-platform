#!/usr/bin/env Rscript

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))

args <- commandArgs(trailingOnly = TRUE)
profile_id <- arg_value(args, "--profile-id")
target_date <- arg_value(args, "--target-date")
baseline_window <- arg_value(args, "--baseline-window", "30d")
baseline_scenario <- arg_value(args, "--baseline-scenario", "baseline")
min_sample_days <- as.integer(arg_value(args, "--min-sample-days", "3"))
include_target_date <- "--include-target-date" %in% args

window_days <- function(w) {
  if (grepl("^[0-9]+d$", w)) return(as.integer(sub("d$", "", w)))
  30L
}

qnum <- function(x) {
  x <- suppressWarnings(as.numeric(x))
  x[is.finite(x)]
}

pct <- function(x, p) {
  x <- qnum(x)
  if (length(x) < 1) return(NA_real_)
  as.numeric(stats::quantile(x, probs = p, na.rm = TRUE, names = FALSE, type = 7))
}

stat_summary <- function(x) {
  x <- qnum(x)
  n <- length(x)
  if (n < 1) {
    return(list(sample_days = 0L, mean_value = NA_real_, sd_value = NA_real_, median_value = NA_real_, p75_value = NA_real_, p90_value = NA_real_, p95_value = NA_real_, p99_value = NA_real_, min_value = NA_real_, max_value = NA_real_, lower_control_limit = NA_real_, upper_control_limit = NA_real_))
  }
  m <- mean(x)
  sdv <- if (n > 1) sqrt(mean((x - m)^2)) else 0
  list(
    sample_days = n,
    mean_value = m,
    sd_value = sdv,
    median_value = pct(x, 0.50),
    p75_value = pct(x, 0.75),
    p90_value = pct(x, 0.90),
    p95_value = pct(x, 0.95),
    p99_value = pct(x, 0.99),
    min_value = min(x),
    max_value = max(x),
    lower_control_limit = max(0, m - 3 * sdv),
    upper_control_limit = m + 3 * sdv
  )
}

quality <- function(sample_days) {
  if (sample_days <= 0) return(list(score = 0, status = "missing", usable = 0L))
  score <- min(1, sample_days / max(1, min_sample_days))
  if (sample_days >= min_sample_days) return(list(score = score, status = "usable", usable = 1L))
  list(score = score, status = "low_sample", usable = 0L)
}

upsert_reference <- function(con, baseline_type, start_date, end_date, sample_days, fallback_policy) {
  q <- quality(sample_days)
  DBI::dbExecute(con, "
    INSERT INTO v05_obs_baseline_reference_day
      (profile_id,target_date,baseline_window,baseline_scenario_name,baseline_type,baseline_start_date,baseline_end_date,sample_days,is_usable,quality_score,fallback_policy,source_table,detail_json)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON DUPLICATE KEY UPDATE baseline_start_date=VALUES(baseline_start_date), baseline_end_date=VALUES(baseline_end_date), sample_days=VALUES(sample_days), is_usable=VALUES(is_usable), quality_score=VALUES(quality_score), fallback_policy=VALUES(fallback_policy), source_table=VALUES(source_table), detail_json=VALUES(detail_json)",
    params = list(profile_id, target_date, baseline_window, baseline_scenario, baseline_type, start_date, end_date, as.integer(sample_days), as.integer(q$usable), q$score, fallback_policy, "v05_obs_baseline_feature_snapshot_day", jsonlite::toJSON(list(include_target_date = include_target_date, min_sample_days = min_sample_days), auto_unbox = TRUE))
  )
}

upsert_stat <- function(con, baseline_type, key_row, stat, source_table = NA_character_) {
  q <- quality(as.integer(stat$sample_days))
  DBI::dbExecute(con, "
    INSERT INTO v05_obs_baseline_stat_profile_day
      (profile_id,target_date,baseline_window,baseline_scenario_name,baseline_type,dimension_type,dimension_key,metric_name,sample_days,mean_value,sd_value,median_value,p75_value,p90_value,p95_value,p99_value,min_value,max_value,lower_control_limit,upper_control_limit,quality_score,baseline_status,source_table)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON DUPLICATE KEY UPDATE sample_days=VALUES(sample_days), mean_value=VALUES(mean_value), sd_value=VALUES(sd_value), median_value=VALUES(median_value), p75_value=VALUES(p75_value), p90_value=VALUES(p90_value), p95_value=VALUES(p95_value), p99_value=VALUES(p99_value), min_value=VALUES(min_value), max_value=VALUES(max_value), lower_control_limit=VALUES(lower_control_limit), upper_control_limit=VALUES(upper_control_limit), quality_score=VALUES(quality_score), baseline_status=VALUES(baseline_status), source_table=VALUES(source_table)",
    params = list(profile_id, target_date, baseline_window, baseline_scenario, baseline_type, key_row$dimension_type, key_row$dimension_key, key_row$metric_name, as.integer(stat$sample_days), stat$mean_value, stat$sd_value, stat$median_value, stat$p75_value, stat$p90_value, stat$p95_value, stat$p99_value, stat$min_value, stat$max_value, stat$lower_control_limit, stat$upper_control_limit, q$score, q$status, source_table)
  )
}

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

if (!table_exists(con, "v05_obs_baseline_feature_snapshot_day")) stop("missing v05_obs_baseline_feature_snapshot_day")
if (!table_exists(con, "v05_obs_baseline_stat_profile_day")) stop("missing v05_obs_baseline_stat_profile_day")

end_date <- as.Date(target_date)
start_date <- end_date - window_days(baseline_window)
stat_end_date <- if (include_target_date) end_date else end_date - 1
if (stat_end_date < start_date) stat_end_date <- start_date

dbExecute(con, "DELETE FROM v05_obs_baseline_stat_profile_day WHERE profile_id=? AND target_date=? AND baseline_window=? AND baseline_scenario_name=?", list(profile_id, target_date, baseline_window, baseline_scenario))
dbExecute(con, "DELETE FROM v05_obs_baseline_reference_day WHERE profile_id=? AND target_date=? AND baseline_window=? AND baseline_scenario_name=?", list(profile_id, target_date, baseline_window, baseline_scenario))

features <- DBI::dbGetQuery(con, "
  SELECT target_date, dimension_type, dimension_key, metric_name, metric_value, source_table
  FROM v05_obs_baseline_feature_snapshot_day
  WHERE profile_id = ? AND scenario_name = ? AND target_date BETWEEN ? AND ?",
  params = list(profile_id, baseline_scenario, as.character(start_date), as.character(stat_end_date))
)

if (nrow(features) < 1) {
  upsert_reference(con, "rolling_30d", as.character(start_date), as.character(stat_end_date), 0L, "primary")
  upsert_reference(con, "same_weekday", as.character(start_date), as.character(stat_end_date), 0L, "fallback_to_rolling_30d_when_low_sample")
  cat("[OK] build_v05_obs_baseline_stat_profile rows=0 rolling_days=0 weekday_days=0\n")
  quit(status = 0)
}
features$target_date <- as.Date(features$target_date)

groups <- split(features, interaction(features$dimension_type, features$dimension_key, features$metric_name, drop = TRUE, sep = "\r"))
rolling_rows <- 0L
for (g in groups) {
  key <- g[1, c("dimension_type", "dimension_key", "metric_name"), drop = FALSE]
  st <- stat_summary(g$metric_value)
  st$sample_days <- length(unique(g$target_date))
  upsert_stat(con, "rolling_30d", key, st, as.character(g$source_table[[1]]))
  rolling_rows <- rolling_rows + 1L
}

target_wday <- as.POSIXlt(as.Date(target_date))$wday
weekday_features <- features[as.POSIXlt(features$target_date)$wday == target_wday, , drop = FALSE]
weekday_rows <- 0L
if (nrow(weekday_features) > 0) {
  wg <- split(weekday_features, interaction(weekday_features$dimension_type, weekday_features$dimension_key, weekday_features$metric_name, drop = TRUE, sep = "\r"))
  for (g in wg) {
    key <- g[1, c("dimension_type", "dimension_key", "metric_name"), drop = FALSE]
    st <- stat_summary(g$metric_value)
    st$sample_days <- length(unique(g$target_date))
    upsert_stat(con, "same_weekday", key, st, as.character(g$source_table[[1]]))
    weekday_rows <- weekday_rows + 1L
  }
}

rolling_days <- length(unique(features$target_date))
weekday_days <- if (nrow(weekday_features) > 0) length(unique(weekday_features$target_date)) else 0L
upsert_reference(con, "rolling_30d", as.character(start_date), as.character(stat_end_date), rolling_days, "primary")
upsert_reference(con, "same_weekday", as.character(start_date), as.character(stat_end_date), weekday_days, "fallback_to_rolling_30d_when_low_sample")
cat(sprintf("[OK] build_v05_obs_baseline_stat_profile rolling=%d weekday=%d rolling_days=%d weekday_days=%d\n", rolling_rows, weekday_rows, rolling_days, weekday_days))
