#!/usr/bin/env Rscript
# Generic Observability Semantic Interpreter
# This is not CASE-OBS-001-specific. It maps R observability analysis output into
# the existing v0.5 semantic table when direct observability risk is present.
suppressWarnings(suppressMessages({ library(DBI); library(RMariaDB) }))
args <- commandArgs(trailingOnly=TRUE)
get_arg <- function(name, default=NULL) { i <- match(name, args); if (!is.na(i) && i < length(args)) args[[i+1]] else default }
q <- function(con, x) as.character(dbQuoteString(con, as.character(x)))

db_host <- get_arg('--db-host','127.0.0.1'); db_port <- as.integer(get_arg('--db-port','3306'))
db_user <- get_arg('--db-user','nethru'); db_pass <- get_arg('--db-pass','nethru1234'); db_name <- get_arg('--db-name','weblog')
profile_id <- get_arg('--profile-id'); target_date <- get_arg('--target-date', get_arg('--dt'))
run_id <- as.integer(get_arg('--run-id')); source_gen_run_id <- as.integer(get_arg('--source-gen-run-id','0'))
scenario_name <- get_arg('--scenario-name','baseline')
con <- dbConnect(RMariaDB::MariaDB(), host=db_host, port=db_port, user=db_user, password=db_pass, dbname=db_name)
on.exit(dbDisconnect(con), add=TRUE)
exists_table <- function(t) dbGetQuery(con, sprintf("SELECT COUNT(*) n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", q(con,t)))$n[[1]] > 0
cols <- function(t) dbGetQuery(con, sprintf("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", q(con,t)))$column_name
if (!exists_table('r_v05_observability_analysis_day')) stop('missing r_v05_observability_analysis_day')
if (!exists_table('semantic_interpretation_day_v05')) stop('missing semantic_interpretation_day_v05')
a <- dbGetQuery(con, sprintf("SELECT * FROM r_v05_observability_analysis_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%d AND source_gen_run_id=%d LIMIT 1", q(con,profile_id), q(con,target_date), q(con,scenario_name), run_id, source_gen_run_id))
if (nrow(a)==0) stop('no observability analysis row found')
score <- as.numeric(a$observability_overall_score[[1]]); if (is.na(score)) score <- 0
semantic <- as.character(a$recommended_semantic_risk[[1]])
if (score < 0.15 || semantic == 'None' || is.na(semantic)) {
  cat(sprintf('[OK] apply_v05_observability_semantic_interpretation no semantic override needed score=%.6f\n', score)); quit(status=0)
}
tbl_cols <- cols('semantic_interpretation_day_v05')
row <- list(
  profile_id=profile_id, target_date=target_date, scenario_name=scenario_name,
  run_id=run_id, source_gen_run_id=source_gen_run_id,
  dominant_semantic_risk=semantic,
  semantic_confidence=1.0,
  interpretation_status='PASS',
  interpretation_reason=sprintf('observability_direct_measurement; score=%.6f; dominant=%s', score, a$dominant_observability_signal[[1]]),
  max_raw_score=score,
  completeness_score=score,
  consistency_score=0,
  integrity_score=0,
  timeliness_score=0,
  availability_score=0
)
insert_names <- intersect(names(row), tbl_cols)
if (length(insert_names) == 0) stop('semantic_interpretation_day_v05 has no compatible columns')
# Prefer update existing row; if absent insert compatible columns.
where <- sprintf("profile_id=%s AND target_date=%s AND run_id=%d", q(con,profile_id), q(con,target_date), run_id)
if ('source_gen_run_id' %in% tbl_cols) where <- paste0(where, sprintf(" AND source_gen_run_id=%d", source_gen_run_id))
if ('scenario_name' %in% tbl_cols) where <- paste0(where, sprintf(" AND scenario_name=%s", q(con,scenario_name)))
existing <- dbGetQuery(con, sprintf("SELECT COUNT(*) n FROM semantic_interpretation_day_v05 WHERE %s", where))$n[[1]]
if (existing > 0) {
  set_parts <- c()
  for (n in insert_names) {
    if (n %in% c('profile_id','target_date','scenario_name','run_id','source_gen_run_id')) next
    v <- row[[n]]
    if (is.numeric(v)) set_parts <- c(set_parts, sprintf('%s=%.10f', n, v)) else set_parts <- c(set_parts, sprintf('%s=%s', n, q(con,v)))
  }
  if (length(set_parts)>0) dbExecute(con, sprintf("UPDATE semantic_interpretation_day_v05 SET %s WHERE %s", paste(set_parts, collapse=','), where))
} else {
  vals <- sapply(insert_names, function(n) { v <- row[[n]]; if (is.numeric(v)) sprintf('%.10f', v) else q(con,v) })
  dbExecute(con, sprintf("INSERT INTO semantic_interpretation_day_v05 (%s) VALUES (%s)", paste(insert_names, collapse=','), paste(vals, collapse=',')))
}
cat(sprintf('[OK] apply_v05_observability_semantic_interpretation score=%.6f semantic=%s\n', score, semantic))
