#!/usr/bin/env Rscript
# -----------------------------------------------------------------------------
# ARCHITECTURE LAYER: BASELINE SCIENCE = AUTHORITY REFERENCE LAYER
#
# Baseline Science substitutes the historical/business experience that a real
# organization would have. It is not an OBS feature. It provides common
# reference evidence for batch, reconciliation, and observability analytics.
# -----------------------------------------------------------------------------
# CASE-OBS-001 Phase2-C4 final
# Baseline Science Statistical Evidence Builder.
# R owns statistical interpretation. SQL owns persistence. Python owns validation.

suppressPackageStartupMessages({
  library(DBI)
  library(RMariaDB)
  library(jsonlite)
})

parse_cli_args <- function(args) {
  out <- list(); i <- 1
  while (i <= length(args)) {
    key <- sub('^--', '', args[[i]])
    if (i == length(args) || grepl('^--', args[[i + 1]])) { out[[key]] <- TRUE; i <- i + 1 }
    else { out[[key]] <- args[[i + 1]]; i <- i + 2 }
  }
  out
}
arg <- function(args, key, default=NULL) {
  v <- args[[key]]
  if (is.null(v) || length(v)==0 || is.na(v) || !nzchar(as.character(v))) return(default)
  as.character(v)
}
num <- function(x, default=0) {
  # Always return a scalar-safe numeric vector. Missing optional columns in
  # schema-aware data frames can produce length-0 vectors; assigning those to a
  # one-row data frame column fails with: replacement has 0 rows, data has 1.
  if (is.null(x) || length(x) == 0) return(default)
  y <- suppressWarnings(as.numeric(x))
  if (length(y) == 0) return(default)
  y[is.na(y) | !is.finite(y)] <- default
  y
}
clamp01 <- function(x) max(0, min(1, num(x)))
level <- function(s) { s <- num(s); if (s>=0.75) 'critical' else if (s>=0.55) 'warning' else if (s>=0.30) 'watch' else if (s>=0.08) 'low' else 'stable' }
percentile_of <- function(x, hist) {
  if (is.null(x) || length(x) == 0 || is.na(x[1])) return(NA_real_)
  h <- hist[!is.na(hist) & is.finite(hist)]
  if (length(h) == 0) return(NA_real_)
  round(100 * mean(h <= x), 4)
}
score_from_stats <- function(z, pct, breach, delta_rate, sample_days, min_sample_days) {
  if (sample_days < min_sample_days) return(0)
  zc <- min(abs(num(z)) / 5, 1)
  pc <- if (is.na(pct)) 0 else if (pct >= 99) 1 else if (pct >= 95) 0.7 else if (pct >= 90) 0.4 else 0
  bc <- ifelse(num(breach) > 0, 1, 0)
  dc <- min(abs(num(delta_rate)) / 0.25, 1)
  clamp01(0.35*zc + 0.25*pc + 0.25*bc + 0.15*dc)
}
control_breach <- function(x, lo, up) {
  if (!is.na(up) && is.finite(up) && x > up) return(1)
  if (!is.na(lo) && is.finite(lo) && x < lo) return(1)
  0
}
qident <- function(x) paste0('`', gsub('`','',x), '`')

args <- parse_cli_args(commandArgs(trailingOnly=TRUE))
host <- arg(args,'db-host','127.0.0.1'); port <- as.integer(arg(args,'db-port','3306'))
user <- arg(args,'db-user'); password <- arg(args,'db-pass',''); db <- arg(args,'db-name')
profile_id <- arg(args,'profile-id'); target_date <- arg(args,'target-date'); scenario_name <- arg(args,'scenario-name','baseline')
run_id <- as.integer(arg(args,'run-id','0')); source_gen_run_id <- as.integer(arg(args,'source-gen-run-id','0'))
baseline_window <- arg(args,'baseline-window','30d'); baseline_scenario <- arg(args,'baseline-scenario','baseline')
domains <- trimws(strsplit(arg(args,'domains','batch,observability,reconciliation'), ',', fixed=TRUE)[[1]])
min_sample_days <- as.integer(arg(args,'min-sample-days','3'))
if (any(vapply(list(user,db,profile_id,target_date), function(x) is.null(x)||x=='', logical(1)))) stop('missing required args')

con <- dbConnect(RMariaDB::MariaDB(), host=host, port=port, user=user, password=password, dbname=db, bigint='integer64')
on.exit(dbDisconnect(con), add=TRUE)

bq <- function(sql, params=list()) { r <- dbSendQuery(con, sql); on.exit(dbClearResult(r), add=TRUE); if (length(params)>0) dbBind(r, unname(params)); dbFetch(r) }
be <- function(sql, params=list()) { r <- dbSendStatement(con, sql); on.exit(dbClearResult(r), add=TRUE); if (length(params)>0) dbBind(r, unname(params)); dbGetRowsAffected(r) }
table_exists <- function(t) { nrow(bq('SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=?', list(t))) > 0 }
cols <- function(t) { if (!table_exists(t)) return(character()); as.character(bq('SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=?', list(t))$column_name) }

if (!table_exists('v05_baseline_science_statistical_evidence_day')) stop('missing v05_baseline_science_statistical_evidence_day; apply SQL 079/078')

# Delete target domains first.
domain_map <- list(batch='batch_metric_delta', observability='observability_expected', reconciliation='reconciliation_measurement')
resolved_domains <- c()
for (d in domains) {
  if (d %in% names(domain_map)) resolved_domains <- c(resolved_domains, domain_map[[d]]) else resolved_domains <- c(resolved_domains, d)
}
for (ed in unique(resolved_domains)) {
  be('DELETE FROM v05_baseline_science_statistical_evidence_day WHERE profile_id=? AND target_date=? AND scenario_name=? AND run_id=? AND source_gen_run_id=? AND baseline_window=? AND evidence_domain=?',
     list(profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window, ed))
}

rows <- list()
add_row <- function(df) rows[[length(rows)+1]] <<- df
base_row <- function(domain, source_table, dimension_type, dimension_key, metric_name) {
  data.frame(profile_id=profile_id, target_date=target_date, dt=target_date, scenario_name=scenario_name,
    run_id=run_id, source_gen_run_id=source_gen_run_id, baseline_window=baseline_window,
    baseline_scenario_name=baseline_scenario, evidence_domain=domain, evidence_source_table=source_table,
    evidence_metric_name=metric_name, dimension_type=dimension_type, dimension_key=substr(as.character(dimension_key),1,191), metric_name=metric_name,
    current_value=NA_real_, baseline_mean=NA_real_, baseline_sd=NA_real_, baseline_delta=NA_real_, baseline_delta_rate=NA_real_,
    z_score=NA_real_, historical_percentile=NA_real_, control_limit_lower=NA_real_, control_limit_upper=NA_real_, control_limit_breach=0L,
    expected_value=NA_real_, expected_delta=NA_real_, expected_delta_rate=NA_real_, watch_threshold=NA_real_, warning_threshold=NA_real_, critical_threshold=NA_real_, threshold_band='none',
    affected_metrics=0L, co_movement_score=0, co_movement_level='none', statistical_score=0, statistical_significance='stable',
    baseline_quality_score=0, sample_days=0L, baseline_status='unknown', analysis_status='PASS', analysis_summary=NA_character_, detail_json=NA_character_, stringsAsFactors=FALSE)
}
insert_rows <- function(all_rows) {
  if (length(all_rows) == 0) return(0)
  df <- do.call(rbind, all_rows)
  sql <- paste0('INSERT INTO v05_baseline_science_statistical_evidence_day (', paste(qident(names(df)), collapse=','), ') VALUES (', paste(rep('?', ncol(df)), collapse=','), ')')
  for (i in seq_len(nrow(df))) be(sql, as.list(df[i,]))
  nrow(df)
}

# ------------------------------------------------------------------
# batch_metric_delta: true time-series history from v05_batch_metric_delta_day.
# ------------------------------------------------------------------
if ('batch' %in% domains || 'batch_metric_delta' %in% domains) {
  if (table_exists('v05_batch_metric_delta_day')) {
    current <- bq('SELECT * FROM v05_batch_metric_delta_day WHERE profile_id=? AND dt=? AND scenario_name=? AND run_id=? AND baseline_window=?',
      list(profile_id, target_date, scenario_name, run_id, baseline_window))
    if (table_exists('v05_batch_metric_delta_history_day')) {
      be('DELETE FROM v05_batch_metric_delta_history_day WHERE profile_id=? AND target_date=? AND baseline_scenario_name=? AND baseline_window=?', list(profile_id, target_date, baseline_scenario, baseline_window))
      hist_all <- bq("SELECT * FROM v05_batch_metric_delta_day WHERE profile_id=? AND scenario_name=? AND dt BETWEEN DATE_SUB(?, INTERVAL 30 DAY) AND ? AND baseline_window=?",
        list(profile_id, baseline_scenario, target_date, target_date, baseline_window))
      if (nrow(hist_all)>0) {
        ins_sql <- paste('INSERT INTO v05_batch_metric_delta_history_day (profile_id,target_date,history_date,scenario_name,baseline_scenario_name,baseline_window,metric_scope,metric_name,current_value,baseline_value_avg,baseline_value_std,absolute_delta,delta_rate,z_score,risk_score,risk_status,source_run_id,source_gen_run_id,source_table) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)')
        for (i in seq_len(nrow(hist_all))) {
          h <- hist_all[i,]
          be(ins_sql, list(profile_id,target_date,as.character(h$dt),as.character(h$scenario_name),baseline_scenario,baseline_window,as.character(h$metric_scope),as.character(h$metric_name),num(h$current_value,NA),num(h$baseline_value_avg,NA),num(h$baseline_value_std,NA),num(h$absolute_delta,NA),num(h$delta_rate,NA),num(h$z_score,NA),num(h$risk_score,NA),as.character(h$risk_status),num(h$run_id,0),num(h$source_gen_run_id,0),'v05_batch_metric_delta_day'))
        }
      }
    }
    if (nrow(current)>0) {
      for (i in seq_len(nrow(current))) {
        r <- current[i,]
        hist <- bq('SELECT * FROM v05_batch_metric_delta_day WHERE profile_id=? AND scenario_name=? AND dt BETWEEN DATE_SUB(?, INTERVAL 30 DAY) AND ? AND baseline_window=? AND metric_scope=? AND metric_name=?',
          list(profile_id, baseline_scenario, target_date, target_date, baseline_window, as.character(r$metric_scope), as.character(r$metric_name)))
        values <- num(hist$risk_score, NA_real_)
        values <- values[!is.na(values) & is.finite(values)]
        sample_days <- if (nrow(hist)>0) length(unique(as.character(hist$dt))) else 0
        cur_val <- num(r$risk_score, 0)
        mean_v <- if (length(values)>0) mean(values) else NA_real_
        sd_v <- if (length(values)>1) stats::sd(values) else 0
        delta <- if (!is.na(mean_v)) cur_val - mean_v else NA_real_
        delta_rate <- if (!is.na(mean_v) && abs(mean_v)>0) abs(delta)/abs(mean_v) else abs(delta)
        z <- if (!is.na(sd_v) && sd_v>0) delta/sd_v else 0
        pct <- percentile_of(cur_val, values)
        lo <- if (!is.na(mean_v)) max(0, mean_v - 3*sd_v) else NA_real_
        up <- if (!is.na(mean_v)) mean_v + 3*sd_v else NA_real_
        breach <- control_breach(cur_val, lo, up)
        score <- score_from_stats(z, pct, breach, delta_rate, sample_days, min_sample_days)
        er <- base_row('batch_metric_delta', 'v05_batch_metric_delta_day+history', as.character(r$metric_scope), 'all', as.character(r$metric_name))
        er$current_value <- cur_val; er$baseline_mean <- mean_v; er$baseline_sd <- sd_v; er$baseline_delta <- delta; er$baseline_delta_rate <- delta_rate
        er$z_score <- z; er$historical_percentile <- pct; er$control_limit_lower <- lo; er$control_limit_upper <- up; er$control_limit_breach <- breach
        er$statistical_score <- score; er$statistical_significance <- level(score); er$baseline_quality_score <- ifelse(sample_days>=min_sample_days,1,min(0.99,sample_days/min_sample_days)); er$sample_days <- sample_days
        er$baseline_status <- ifelse(sample_days>=min_sample_days,'history_available','LOW_SAMPLE_HISTORY')
        er$analysis_status <- ifelse(sample_days<min_sample_days,'LOW_SAMPLE_HISTORY', ifelse(score>=0.3,'SIGNAL','PASS'))
        er$analysis_summary <- sprintf('batch metric history %s/%s value=%.6f mean=%.6f sd=%.6f z=%.3f pct=%.2f sample_days=%d', r$metric_scope, r$metric_name, cur_val, mean_v, sd_v, z, pct, sample_days)
        er$detail_json <- toJSON(list(source='v05_batch_metric_delta_day', history_source='v05_batch_metric_delta_day', current_risk_status=as.character(r$risk_status)), auto_unbox=TRUE, null='null')
        add_row(er)
      }
      # Co-movement within batch domain: ratio of significant metric rows.
      if (length(rows)>0) {
        idx <- which(vapply(rows, function(x) x$evidence_domain[[1]]=='batch_metric_delta', logical(1)))
        if (length(idx)>0) {
          sig_count <- sum(vapply(rows[idx], function(x) num(x$statistical_score[[1]]) >= 0.3, logical(1)))
          cm <- ifelse(length(idx)>0, sig_count/length(idx), 0)
          for (j in idx) { rows[[j]]$affected_metrics <- sig_count; rows[[j]]$co_movement_score <- cm; rows[[j]]$co_movement_level <- ifelse(cm>=0.5,'high',ifelse(cm>=0.25,'medium',ifelse(cm>0,'low','none'))) }
        }
      }
    }
  }
}

# ------------------------------------------------------------------
# observability_expected: reference domain, not statistical meaning domain.
# ------------------------------------------------------------------
if ('observability' %in% domains || 'observability_expected' %in% domains) {
  if (table_exists('v05_obs_expected_metric_day')) {
    expected <- bq('SELECT * FROM v05_obs_expected_metric_day WHERE profile_id=? AND target_date=? AND scenario_name=? AND run_id=? AND source_gen_run_id=? AND baseline_window=?',
      list(profile_id, target_date, scenario_name, run_id, source_gen_run_id, baseline_window))
    if (nrow(expected)>0) {
      for (i in seq_len(nrow(expected))) {
        r <- expected[i,]
        er <- base_row('observability_expected', 'v05_obs_expected_metric_day', as.character(r$dimension_type), as.character(r$dimension_key), as.character(r$metric_name))
        er$current_value <- num(r$current_value,NA); er$expected_value <- num(r$expected_value,NA); er$expected_delta <- num(r$expected_delta,NA); er$expected_delta_rate <- num(r$expected_delta_rate,NA)
        er$baseline_mean <- num(r$baseline_mean,NA); er$baseline_sd <- num(r$baseline_sd,NA); er$baseline_delta <- num(r$current_value,NA) - num(r$baseline_mean,NA)
        er$sample_days <- num(r$selected_sample_days,0); er$baseline_quality_score <- num(r$baseline_quality_score,0); er$baseline_status <- as.character(r$model_status)
        er$analysis_status <- 'REFERENCE_DOMAIN_NOT_STATISTICAL'
        er$analysis_summary <- 'observability_expected is an expected/reference model output; statistical meaning is tested through gap/anomaly scenarios or future observed history, not this reference domain'
        er$detail_json <- toJSON(list(source='v05_obs_expected_metric_day', quality_status=as.character(r$quality_status)), auto_unbox=TRUE, null='null')
        add_row(er)
      }
    }
  }
}

# ------------------------------------------------------------------
# reconciliation_measurement: true time-series from v05_reconciliation_measurement_day.
# ------------------------------------------------------------------
if ('reconciliation' %in% domains || 'reconciliation_measurement' %in% domains) {
  if (table_exists('v05_reconciliation_measurement_day')) {
    current <- bq('SELECT * FROM v05_reconciliation_measurement_day WHERE profile_id=? AND target_date=? AND scenario_name=? AND run_id=? AND source_gen_run_id=? LIMIT 1',
      list(profile_id, target_date, scenario_name, run_id, source_gen_run_id))
    if (nrow(current)>0) {
      metrics <- c('behavior_transaction_match_rate','transaction_state_match_rate','behavior_only_count','transaction_only_count','transaction_without_state_count','orphan_state_count')
      hist <- bq('SELECT * FROM v05_reconciliation_measurement_day WHERE profile_id=? AND scenario_name=? AND target_date BETWEEN DATE_SUB(?, INTERVAL 30 DAY) AND ?',
        list(profile_id, baseline_scenario, target_date, target_date))
      for (m in metrics) {
        if (!(m %in% names(current))) next
        vals <- if (m %in% names(hist)) num(hist[[m]], NA_real_) else numeric()
        vals <- vals[!is.na(vals) & is.finite(vals)]
        sample_days <- if (nrow(hist)>0) length(unique(as.character(hist$target_date))) else 0
        cur_val <- num(current[[m]][[1]],0); mean_v <- if (length(vals)>0) mean(vals) else NA_real_; sd_v <- if (length(vals)>1) stats::sd(vals) else 0
        delta <- if (!is.na(mean_v)) cur_val - mean_v else NA_real_; delta_rate <- if (!is.na(mean_v) && abs(mean_v)>0) abs(delta)/abs(mean_v) else abs(delta)
        z <- if (!is.na(sd_v) && sd_v>0) delta/sd_v else 0; pct <- percentile_of(cur_val, vals)
        lo <- if (!is.na(mean_v)) mean_v - 3*sd_v else NA_real_; up <- if (!is.na(mean_v)) mean_v + 3*sd_v else NA_real_; breach <- control_breach(cur_val, lo, up)
        score <- score_from_stats(z,pct,breach,delta_rate,sample_days,min_sample_days)
        er <- base_row('reconciliation_measurement', 'v05_reconciliation_measurement_day', 'reconciliation', 'all', m)
        er$current_value <- cur_val; er$baseline_mean <- mean_v; er$baseline_sd <- sd_v; er$baseline_delta <- delta; er$baseline_delta_rate <- delta_rate
        er$z_score <- z; er$historical_percentile <- pct; er$control_limit_lower <- lo; er$control_limit_upper <- up; er$control_limit_breach <- breach
        er$statistical_score <- score; er$statistical_significance <- level(score); er$baseline_quality_score <- ifelse(sample_days>=min_sample_days,1,min(0.99,sample_days/min_sample_days)); er$sample_days <- sample_days
        er$baseline_status <- ifelse(sample_days>=min_sample_days,'history_available','LOW_SAMPLE_HISTORY')
        er$analysis_status <- ifelse(sample_days<min_sample_days,'LOW_SAMPLE_HISTORY', ifelse(score>=0.3,'SIGNAL','PASS'))
        er$analysis_summary <- sprintf('reconciliation %s value=%.6f mean=%.6f sd=%.6f z=%.3f pct=%.2f sample_days=%d', m, cur_val, mean_v, sd_v, z, pct, sample_days)
        er$detail_json <- toJSON(list(source='v05_reconciliation_measurement_day'), auto_unbox=TRUE, null='null')
        add_row(er)
      }
      idx <- which(vapply(rows, function(x) x$evidence_domain[[1]]=='reconciliation_measurement', logical(1)))
      if (length(idx)>0) {
        sig_count <- sum(vapply(rows[idx], function(x) num(x$statistical_score[[1]]) >= 0.3, logical(1)))
        cm <- sig_count/length(idx)
        for (j in idx) { rows[[j]]$affected_metrics <- sig_count; rows[[j]]$co_movement_score <- cm; rows[[j]]$co_movement_level <- ifelse(cm>=0.5,'high',ifelse(cm>=0.25,'medium',ifelse(cm>0,'low','none'))) }
      }
    }
  }
}

inserted <- insert_rows(rows)

# Enrich v05_batch_metric_delta_day for direct v0.4 evidence inspection.
if (table_exists('v05_batch_metric_delta_day') && inserted>0) {
  be(paste(
    'UPDATE v05_batch_metric_delta_day b',
    'JOIN v05_baseline_science_statistical_evidence_day e',
    'ON e.profile_id COLLATE utf8mb4_general_ci = b.profile_id COLLATE utf8mb4_general_ci',
    'AND e.target_date=b.dt',
    'AND e.scenario_name COLLATE utf8mb4_general_ci = b.scenario_name COLLATE utf8mb4_general_ci',
    'AND e.run_id=b.run_id',
    'AND e.source_gen_run_id=b.source_gen_run_id',
    'AND e.baseline_window COLLATE utf8mb4_general_ci = b.baseline_window COLLATE utf8mb4_general_ci',
    'AND e.evidence_domain COLLATE utf8mb4_general_ci = \'batch_metric_delta\' COLLATE utf8mb4_general_ci',
    'AND e.dimension_type COLLATE utf8mb4_general_ci = b.metric_scope COLLATE utf8mb4_general_ci',
    'AND e.metric_name COLLATE utf8mb4_general_ci = b.metric_name COLLATE utf8mb4_general_ci',
    'SET b.historical_percentile=e.historical_percentile, b.control_limit_lower=e.control_limit_lower,',
    'b.control_limit_upper=e.control_limit_upper, b.control_limit_breach=e.control_limit_breach,',
    'b.statistical_score=e.statistical_score, b.statistical_significance=e.statistical_significance,',
    'b.baseline_quality_score=e.baseline_quality_score, b.co_movement_score=e.co_movement_score',
    'WHERE b.profile_id=? AND b.dt=? AND b.scenario_name=? AND b.run_id=? AND b.source_gen_run_id=? AND b.baseline_window=?'),
    list(profile_id,target_date,scenario_name,run_id,source_gen_run_id,baseline_window))
}

summary <- bq('SELECT evidence_domain, COUNT(*) AS n, MAX(statistical_score) AS max_score, MIN(sample_days) AS min_days, MAX(sample_days) AS max_days FROM v05_baseline_science_statistical_evidence_day WHERE profile_id=? AND target_date=? AND scenario_name=? AND run_id=? AND source_gen_run_id=? AND baseline_window=? GROUP BY evidence_domain ORDER BY evidence_domain',
  list(profile_id,target_date,scenario_name,run_id,source_gen_run_id,baseline_window))
cat(sprintf('[OK] build_v05_baseline_science_statistical_evidence rows=%d target=%s scenario=%s run_id=%d\n', inserted, target_date, scenario_name, run_id))
if (nrow(summary)>0) {
  for (i in seq_len(nrow(summary))) cat(sprintf('  - domain=%s rows=%d sample_days=%s..%s max_statistical_score=%.6f\n', summary$evidence_domain[[i]], as.integer(summary$n[[i]]), as.character(summary$min_days[[i]]), as.character(summary$max_days[[i]]), num(summary$max_score[[i]])))
}
