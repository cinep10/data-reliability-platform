#!/usr/bin/env Rscript
# v0.5 R analytics common library
# Philosophy:
# - SQL persists measurements.
# - R interprets risk.
# - Python and shell orchestrate execution.

suppressPackageStartupMessages({
  library(DBI)
  library(RMariaDB)
  library(jsonlite)
})

# ------------------------------------------------------------------
# CLI Argument Helpers
# ------------------------------------------------------------------

parse_cli_args <- function(args = commandArgs(trailingOnly = TRUE)) {
  keys <- args[seq(1, length(args), by = 2)]
  vals <- args[seq(2, length(args), by = 2)]
  out <- as.list(vals)
  names(out) <- keys
  out
}

arg_value <- function(args, name, default = NULL) {
  parsed <- if (is.list(args) && !is.null(names(args))) args else parse_cli_args(args)
  value <- parsed[[name]]
  if (is.null(value) || length(value) == 0 || is.na(value) || !nzchar(as.character(value))) default else as.character(value)
}

get_arg <- function(name, default = NULL) arg_value(commandArgs(trailingOnly = TRUE), name, default)

safe_number <- function(x, default = 0) {
  y <- suppressWarnings(as.numeric(x))
  ifelse(is.na(y) | !is.finite(y), default, y)
}
safe_num <- safe_number
clamp01 <- function(x) max(0, min(1, safe_number(x)))
ratio_or_zero <- function(numerator, denominator) {
  d <- safe_number(denominator)
  if (d <= 0) return(0)
  safe_number(numerator) / d
}
score_status <- function(score, warn = 0.20, high = 0.50) {
  s <- safe_number(score)
  if (s >= high) "FAIL" else if (s >= warn) "WARN" else "PASS"
}
risk_level <- function(score) {
  s <- safe_number(score)
  if (s >= 0.75) "critical" else if (s >= 0.55) "high" else if (s >= 0.30) "warning" else if (s >= 0.08) "low" else "stable"
}


# ------------------------------------------------------------------
# Database Connection
# ------------------------------------------------------------------

connect_db <- function(args = commandArgs(trailingOnly = TRUE)) {
  DBI::dbConnect(
    RMariaDB::MariaDB(),
    host = arg_value(args, "--db-host", "127.0.0.1"),
    port = as.integer(arg_value(args, "--db-port", "3306")),
    user = arg_value(args, "--db-user", "nethru"),
    password = arg_value(args, "--db-pass", "nethru1234"),
    dbname = arg_value(args, "--db-name", "weblog")
  )
}

quote_value <- function(con, value) as.character(DBI::dbQuoteString(con, value))
esc <- function(value) gsub("'", "''", as.character(value))
quote_identifier <- function(name) paste0("`", gsub("`", "", name), "`")

query_df <- function(con, sql, params = NULL) {
  if (is.null(params)) DBI::dbGetQuery(con, sql) else DBI::dbGetQuery(con, sql, params = params)
}
execute_sql <- function(con, sql, params = NULL) {
  if (is.null(params)) DBI::dbExecute(con, sql) else DBI::dbExecute(con, sql, params = params)
}


# ------------------------------------------------------------------
# Schema Helpers
# ------------------------------------------------------------------

table_exists <- function(con, table_name) {
  result <- query_df(
    con,
    "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = ?",
    list(table_name)
  )

  safe_number(result$n[[1]]) > 0
}

exists_table <- table_exists

table_columns <- function(con, table_name) {
  if (!table_exists(con, table_name)) {
    return(character())
  }

  result <- query_df(
    con,
    "SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ?",
    list(table_name)
  )

  as.character(result$column_name)
}

cols <- table_columns

column_exists <- function(con, table_name, column_name) column_name %in% table_columns(con, table_name)
col_exists <- column_exists

ensure_column <- function(con, table_name, column_name, ddl_type) {
  if (!column_exists(con, table_name, column_name)) {
    execute_sql(con, sprintf("ALTER TABLE `%s` ADD COLUMN `%s` %s", table_name, column_name, ddl_type))
    message(sprintf("[SCHEMA] added %s.%s", table_name, column_name))
  }
}

scoped_where <- function(con, table_name, profile_id, date_value, run_id = NULL, source_gen_run_id = NULL, scenario_name = NULL, date_candidates = c("target_date", "dt")) {
  table_cols <- table_columns(con, table_name)
  filters <- character()
  params <- list()
  if ("profile_id" %in% table_cols) { filters <- c(filters, "profile_id = ?")
 params <- c(params, list(profile_id)) }
  date_col <- date_candidates[date_candidates %in% table_cols][1]
  if (!is.na(date_col)) { filters <- c(filters, paste0(date_col, " = ?"))
 params <- c(params, list(date_value)) }
  if (!is.null(run_id) && "run_id" %in% table_cols) { filters <- c(filters, "run_id = ?")
 params <- c(params, list(as.integer(run_id))) }
  if (!is.null(source_gen_run_id) && "source_gen_run_id" %in% table_cols) { filters <- c(filters, "source_gen_run_id = ?")
 params <- c(params, list(as.integer(source_gen_run_id))) }
  if (!is.null(scenario_name) && "scenario_name" %in% table_cols) { filters <- c(filters, "scenario_name = ?")
 params <- c(params, list(scenario_name)) }
  list(sql = if (length(filters) > 0) paste(filters, collapse = " AND ") else "1 = 1", params = params)
}

read_scoped_table <- function(con, table_name, profile_id, date_value, run_id = NULL, source_gen_run_id = NULL, scenario_name = NULL, limit = NULL) {
  if (!table_exists(con, table_name)) return(data.frame())
  scope <- scoped_where(con, table_name, profile_id, date_value, run_id, source_gen_run_id, scenario_name)
  order_cols <- intersect(c("created_at", "updated_at", "run_id"), table_columns(con, table_name))
  sql <- paste0("SELECT * FROM `", table_name, "` WHERE ", scope$sql)
  if (length(order_cols) > 0) sql <- paste0(sql, " ORDER BY ", paste(sprintf("`%s` DESC", order_cols), collapse = ", "))
  if (!is.null(limit)) sql <- paste0(sql, " LIMIT ", as.integer(limit))
  query_df(con, sql, scope$params)
}

read_first_scoped_row <- function(con, table_name, profile_id, date_value, run_id = NULL, source_gen_run_id = NULL, scenario_name = NULL) {
  df <- read_scoped_table(con, table_name, profile_id, date_value, run_id, source_gen_run_id, scenario_name, limit = 1)
  if (nrow(df) < 1) return(data.frame())
  df[1, , drop = FALSE]
}

pick_number <- function(row, columns, default = 0) {
  if (nrow(row) < 1) return(default)
  for (column in columns) {
    if (column %in% names(row) && !is.na(row[[column]][[1]])) return(safe_number(row[[column]][[1]], default))
  }
  default
}

pick_character <- function(row, columns, default = "none") {
  if (nrow(row) < 1) return(default)
  for (column in columns) {
    if (column %in% names(row) && !is.na(row[[column]][[1]]) && nzchar(as.character(row[[column]][[1]]))) return(as.character(row[[column]][[1]]))
  }
  default
}

insert_schema_aware <- function(con, table_name, row) {
  if (!table_exists(con, table_name)) stop(sprintf("missing target table: %s", table_name))
  target_cols <- table_columns(con, table_name)
  row_names <- names(row)
  keep <- row_names[row_names %in% target_cols]
  if (length(keep) < 1) stop(sprintf("no compatible columns for %s", table_name))
  sql <- sprintf(
    "INSERT INTO `%s` (%s) VALUES (%s)",
    table_name,
    paste(sprintf("`%s`", keep), collapse = ","),
    paste(rep("?", length(keep)), collapse = ",")
  )
  execute_sql(con, sql, unname(row[keep]))
}

delete_scoped_rows <- function(con, table_name, profile_id, date_value, run_id = NULL, source_gen_run_id = NULL, scenario_name = NULL) {
  if (!table_exists(con, table_name)) return(0)
  scope <- scoped_where(con, table_name, profile_id, date_value, run_id, source_gen_run_id, scenario_name)
  execute_sql(con, paste0("DELETE FROM `", table_name, "` WHERE ", scope$sql), scope$params)
}

make_payload <- function(...) jsonlite::toJSON(list(...), auto_unbox = TRUE, null = "null")
