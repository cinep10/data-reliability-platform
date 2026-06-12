#!/usr/bin/env Rscript
# CASE-OBS-001 Phase2-C3-A
# R = statistical threshold calibration. SQL persists, Python validates/orchestrates.

parse_cli_args <- function(args) {
  out <- list()
  i <- 1
  while (i <= length(args)) {
    key <- sub('^--', '', args[[i]])
    if (i == length(args) || grepl('^--', args[[i + 1]])) {
      out[[key]] <- TRUE
      i <- i + 1
    } else {
      out[[key]] <- args[[i + 1]]
      i <- i + 2
    }
  }
  out
}

arg_value <- function(args, key, default = NULL) {
  v <- args[[key]]
  if (is.null(v)) return(default)
  v
}

suppressPackageStartupMessages({
  library(DBI)
  library(RMariaDB)
})

args <- parse_cli_args(commandArgs(trailingOnly = TRUE))

host <- arg_value(args, 'db-host', '127.0.0.1')
port <- as.integer(arg_value(args, 'db-port', '3306'))
user <- arg_value(args, 'db-user')
password <- arg_value(args, 'db-pass', '')
db <- arg_value(args, 'db-name')
profile_id <- arg_value(args, 'profile-id')
target_date <- arg_value(args, 'target-date')
scenario_name <- arg_value(args, 'scenario-name', 'baseline')
run_id <- as.integer(arg_value(args, 'run-id'))
source_gen_run_id <- as.integer(arg_value(args, 'source-gen-run-id', '0'))
baseline_window <- arg_value(args, 'baseline-window', '30d')
baseline_scenario <- arg_value(args, 'baseline-scenario', 'baseline')
min_sample_days <- as.integer(arg_value(args, 'min-sample-days', '3'))
rule_version <- arg_value(args, 'rule-version', 'obs_threshold_calibration_v1')

required <- c(user, db, profile_id, target_date, run_id)
if (any(vapply(required, function(x) is.null(x) || is.na(x) || x == '', logical(1)))) {
  stop('missing required arguments')
}

con <- dbConnect(
  RMariaDB::MariaDB(), host = host, port = port, user = user,
  password = password, dbname = db, bigint = 'integer64'
)
on.exit(dbDisconnect(con), add = TRUE)

# RMariaDB can fail when a named `params=` argument is used with anonymous `?`
# placeholders. Keep all parameter binding explicit and positional.
db_query <- function(sql, params = list()) {
  res <- dbSendQuery(con, sql)
  on.exit(dbClearResult(res), add = TRUE)
  if (length(params) > 0) {
    dbBind(res, unname(params))
  }
  dbFetch(res)
}

db_exec <- function(sql, params = list()) {
  res <- dbSendStatement(con, sql)
  on.exit(dbClearResult(res), add = TRUE)
  if (length(params) > 0) {
    dbBind(res, unname(params))
  }
  dbGetRowsAffected(res)
}

quote_id <- function(x) dbQuoteIdentifier(con, x)

table_exists <- function(table_name) {
  sql <- "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = ?"
  as.integer(db_query(sql, list(table_name))$n[[1]]) > 0
}

columns <- function(table_name) {
  sql <- "SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ?"
  as.character(db_query(sql, list(table_name))$column_name)
}

first_existing <- function(cols, candidates) {
  for (c in candidates) if (c %in% cols) return(c)
  NULL
}

if (!table_exists('v05_obs_expected_metric_day')) {
  stop('missing input table v05_obs_expected_metric_day')
}
if (!table_exists('v05_obs_threshold_calibration_day')) {
  stop('missing output table v05_obs_threshold_calibration_day; apply sql/076 first')
}

cols <- columns('v05_obs_expected_metric_day')
value_col <- first_existing(cols, c('abs_delta_rate', 'expected_delta_rate', 'delta_rate'))
if (is.null(value_col)) value_col <- first_existing(cols, c('abs_delta', 'expected_delta', 'delta'))
if (is.null(value_col)) value_col <- first_existing(cols, c('current_value', 'metric_value'))
if (is.null(value_col)) stop('v05_obs_expected_metric_day has no usable value column')

sample_col <- first_existing(cols, c('sample_days', 'baseline_sample_days', 'rolling_sample_days'))
quality_col <- first_existing(cols, c('quality_status', 'baseline_quality_level', 'baseline_quality_status'))
model_col <- first_existing(cols, c('model_status', 'expected_model_status'))
dim_col <- first_existing(cols, c('dimension_type'))
metric_col <- first_existing(cols, c('metric_name'))
if (is.null(dim_col) || is.null(metric_col)) stop('expected metric table must have dimension_type and metric_name')

where <- c('profile_id = ?', 'target_date = ?', 'scenario_name = ?', 'run_id = ?', 'source_gen_run_id = ?', 'baseline_window = ?')
params <- list(profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window)

select_sql <- paste0(
  'SELECT dimension_type, metric_name, ', value_col, ' AS value_col',
  if (!is.null(sample_col)) paste0(', ', sample_col, ' AS sample_days') else ', 0 AS sample_days',
  if (!is.null(quality_col)) paste0(', ', quality_col, ' AS quality_status') else ", 'unknown' AS quality_status",
  if (!is.null(model_col)) paste0(', ', model_col, ' AS model_status') else ", 'unknown' AS model_status",
  ' FROM v05_obs_expected_metric_day WHERE ', paste(where, collapse = ' AND ')
)
raw <- db_query(select_sql, params)
if (nrow(raw) == 0) {
  message('[OK] build_v05_obs_threshold_calibration no input expected metrics')
  quit(status = 0)
}

raw$value_col <- suppressWarnings(as.numeric(raw$value_col))
raw$value_col[is.na(raw$value_col)] <- 0
raw$sample_days <- suppressWarnings(as.integer(raw$sample_days))
raw$sample_days[is.na(raw$sample_days)] <- 0
raw$abs_value <- abs(raw$value_col)

policy_for <- function(dimension_type) {
  if (dimension_type %in% c('all', 'app_platform', 'sdk_version')) return('sensitive')
  if (dimension_type %in% c('app_version', 'app_sdk')) return('version_sensitive')
  if (dimension_type %in% c('url', 'client')) return('volume_guarded')
  'default'
}

min_sample_count_for <- function(dimension_type) {
  if (dimension_type %in% c('url', 'client')) return(100L)
  if (dimension_type %in% c('app_version', 'app_sdk')) return(30L)
  1L
}

threshold_defaults <- function(policy) {
  if (policy == 'sensitive') return(c(0.04, 0.08, 0.20))
  if (policy == 'version_sensitive') return(c(0.04, 0.08, 0.18))
  if (policy == 'volume_guarded') return(c(0.08, 0.15, 0.30))
  c(0.05, 0.10, 0.25)
}

parts <- split(raw, paste(raw$dimension_type, raw$metric_name, sep = '\001'))
rows <- list()
for (nm in names(parts)) {
  d <- parts[[nm]]
  dimension_type <- as.character(d$dimension_type[[1]])
  metric_name <- as.character(d$metric_name[[1]])
  vals <- d$abs_value
  sample_days <- max(d$sample_days, na.rm = TRUE)
  row_count <- nrow(d)
  policy <- policy_for(dimension_type)
  defs <- threshold_defaults(policy)
  p90 <- as.numeric(stats::quantile(vals, probs = 0.90, na.rm = TRUE, names = FALSE, type = 7))
  p95 <- as.numeric(stats::quantile(vals, probs = 0.95, na.rm = TRUE, names = FALSE, type = 7))
  p99 <- as.numeric(stats::quantile(vals, probs = 0.99, na.rm = TRUE, names = FALSE, type = 7))
  mean_value <- mean(vals, na.rm = TRUE)
  sd_value <- stats::sd(vals, na.rm = TRUE)
  if (is.na(sd_value)) sd_value <- 0
  watch <- max(defs[[1]], p90, na.rm = TRUE)
  warning <- max(defs[[2]], p95, watch, na.rm = TRUE)
  critical <- max(defs[[3]], p99, warning, na.rm = TRUE)
  quality_status <- if (sample_days >= min_sample_days) 'usable' else 'low_sample'
  calibration_status <- if (sample_days >= min_sample_days) 'usable' else 'low_sample'
  if (policy == 'volume_guarded' && row_count < min_sample_count_for(dimension_type)) {
    calibration_status <- 'low_volume'
  }
  rows[[length(rows) + 1]] <- data.frame(
    profile_id = profile_id,
    target_date = target_date,
    scenario_name = scenario_name,
    run_id = run_id,
    source_gen_run_id = source_gen_run_id,
    baseline_window = baseline_window,
    baseline_scenario = baseline_scenario,
    dimension_type = dimension_type,
    metric_name = metric_name,
    sample_days = sample_days,
    row_count = row_count,
    min_sample_count = min_sample_count_for(dimension_type),
    quality_status = quality_status,
    calibration_status = calibration_status,
    dimension_policy = policy,
    mean_value = mean_value,
    sd_value = sd_value,
    p90_value = p90,
    p95_value = p95,
    p99_value = p99,
    watch_threshold = watch,
    warning_threshold = warning,
    critical_threshold = critical,
    z_watch = 2,
    z_warning = 3,
    z_critical = 5,
    delta_rate_watch = defs[[1]],
    delta_rate_warning = defs[[2]],
    delta_rate_critical = defs[[3]],
    calibration_rule_version = rule_version,
    stringsAsFactors = FALSE
  )
}

out <- do.call(rbind, rows)

db_exec(
  paste(
    'DELETE FROM v05_obs_threshold_calibration_day',
    'WHERE profile_id = ? AND target_date = ? AND scenario_name = ? AND run_id = ? AND source_gen_run_id = ? AND baseline_window = ?'
  ),
  list(profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window)
)

for (i in seq_len(nrow(out))) {
  r <- out[i, ]
  db_exec(paste0(
    'INSERT INTO v05_obs_threshold_calibration_day (',
    'profile_id,target_date,scenario_name,run_id,source_gen_run_id,baseline_window,baseline_scenario,',
    'dimension_type,metric_name,sample_days,row_count,min_sample_count,quality_status,calibration_status,dimension_policy,',
    'mean_value,sd_value,p90_value,p95_value,p99_value,watch_threshold,warning_threshold,critical_threshold,',
    'z_watch,z_warning,z_critical,delta_rate_watch,delta_rate_warning,delta_rate_critical,calibration_rule_version',
    ') VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
  ), as.list(r[1, c(
    'profile_id','target_date','scenario_name','run_id','source_gen_run_id','baseline_window','baseline_scenario',
    'dimension_type','metric_name','sample_days','row_count','min_sample_count','quality_status','calibration_status','dimension_policy',
    'mean_value','sd_value','p90_value','p95_value','p99_value','watch_threshold','warning_threshold','critical_threshold',
    'z_watch','z_warning','z_critical','delta_rate_watch','delta_rate_warning','delta_rate_critical','calibration_rule_version'
  )]))
}

message(sprintf('[OK] build_v05_obs_threshold_calibration rows=%d target=%s run_id=%s', nrow(out), target_date, run_id))
