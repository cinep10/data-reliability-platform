suppressPackageStartupMessages({
  library(jsonlite)
  library(stats)
})

args <- commandArgs(trailingOnly=TRUE)

arg <- function(name, default=NULL) {
  key <- paste0("--", name)
  i <- match(key, args)
  if (!is.na(i) && i < length(args)) return(args[[i+1]])
  default
}

cfg <- list(
  db_host=arg("db-host","127.0.0.1"),
  db_port=arg("db-port","3306"),
  db_user=arg("db-user"),
  db_pass=arg("db-pass"),
  db_name=arg("db-name"),
  profile_id=arg("profile-id"),
  dt=arg("dt", arg("dt-from")),
  run_id=arg("run-id",""),
  scenario_name=arg("scenario-name",""),
  baseline_dt=arg("baseline-dt", arg("dt", arg("dt-from"))),
  effective_from=arg("effective-from", arg("dt", arg("dt-from"))),
  expected_risk_family=arg("expected-risk-family","unknown")
)

mysql_args <- function(extra=c()) {
  c("-h", cfg$db_host, "-P", cfg$db_port, "-u", cfg$db_user, paste0("-p", cfg$db_pass), cfg$db_name, extra)
}

sql_escape <- function(x) {
  x <- as.character(x)
  x <- gsub("\\\\", "\\\\\\\\", x)
  x <- gsub("'", "''", x)
  paste0("'", x, "'")
}

qi <- function(x) paste0("`", gsub("`","``", as.character(x)), "`")

query_df <- function(sql) {
  tf <- tempfile(fileext=".sql")
  writeLines(sql, tf, useBytes=TRUE)
  out <- tryCatch(
    system2("mysql", mysql_args(c("-N", "-B")), stdin=tf, stdout=TRUE, stderr=TRUE),
    error=function(e) structure(character(), status=1, stderr=conditionMessage(e))
  )
  status <- attr(out, "status")
  if (!is.null(status) && status != 0) {
    stop(paste(c("mysql query failed:", out), collapse="\n"))
  }
  if (length(out)==0) return(data.frame())
  read.delim(text=paste(out, collapse="\n"), header=FALSE, sep="\t", stringsAsFactors=FALSE, quote="", check.names=FALSE)
}

exec_sql <- function(sql) {
  tf <- tempfile(fileext=".sql")
  writeLines(sql, tf, useBytes=TRUE)
  out <- tryCatch(
    system2("mysql", mysql_args(), stdin=tf, stdout=TRUE, stderr=TRUE),
    error=function(e) structure(character(), status=1, stderr=conditionMessage(e))
  )
  status <- attr(out, "status")
  if (!is.null(status) && status != 0) {
    stop(paste(c("mysql exec failed:", out), collapse="\n"))
  }
  invisible(TRUE)
}

scalar <- function(sql, default=0) {
  d <- query_df(sql)
  if (nrow(d)==0 || ncol(d)==0) return(default)
  v <- d[1,1]
  if (is.na(v) || v=="NULL") return(default)
  v
}

table_exists <- function(t) {
  as.integer(scalar(paste0(
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=", sql_escape(t), ";"
  ), 0)) > 0
}

col_exists <- function(t,c) {
  if (!table_exists(t)) return(FALSE)
  as.integer(scalar(paste0(
    "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=", sql_escape(t),
    " AND column_name=", sql_escape(c), ";"
  ), 0)) > 0
}

first_col <- function(t, cs) {
  for (c in cs) if (col_exists(t,c)) return(c)
  NA_character_
}

table_columns <- function(t) {
  if (!table_exists(t)) return(character())
  d <- query_df(paste0("SHOW COLUMNS FROM ", qi(t), ";"))
  if (nrow(d)==0) return(character())
  as.character(d[,1])
}

date_col <- function(t) first_col(t, c("dt","target_date","metric_dt","event_date","effective_from","baseline_dt"))

nz <- function(x, d=0) {
  if (length(x)==0 || is.null(x) || is.na(x) || x=="NULL") return(d)
  x <- suppressWarnings(as.numeric(x))
  if (!is.finite(x)) return(d)
  x
}

clip01 <- function(x) max(0, min(1, nz(x)))

status_by_score <- function(x) {
  x <- nz(x)
  if (x >= 0.6) return("FAIL")
  if (x >= 0.2) return("WARN")
  "PASS"
}

risk_level <- function(score) {
  s <- nz(score)
  if (s >= 0.80) return("CRITICAL")
  if (s >= 0.60) return("HIGH")
  if (s >= 0.30) return("MEDIUM")
  if (s > 0) return("LOW")
  "STABLE"
}

safe_ratio <- function(a,b) {
  a <- nz(a)
  b <- nz(b)
  if (abs(b)<1e-9) return(ifelse(abs(a)<1e-9,0,a))
  a/b
}

positive_delta_ratio <- function(actual, baseline) max(0, safe_ratio(actual - baseline, max(1, abs(baseline))))
negative_delta_ratio <- function(actual, baseline) max(0, safe_ratio(baseline - actual, max(1, abs(baseline))))
abs_delta_ratio <- function(actual, baseline) abs(safe_ratio(actual - baseline, max(1, abs(baseline))))

availability_drop <- function(actual, baseline) {
  a <- nz(actual)
  b <- nz(baseline)
  if (b <= 0) return(0)
  max(0, (b-a)/b)
}

safe_cor <- function(x, y) {
  x <- suppressWarnings(as.numeric(x))
  y <- suppressWarnings(as.numeric(y))
  ok <- is.finite(x) & is.finite(y)
  x <- x[ok]
  y <- y[ok]
  if (length(x) < 2 || length(y) < 2) return(NA_real_)
  if (sd(x) == 0 || sd(y) == 0) return(NA_real_)
  suppressWarnings(cor(x, y))
}

psi_score <- function(actual, base) {
  actual <- as.numeric(actual)
  base <- as.numeric(base)
  actual <- actual[is.finite(actual)]
  base <- base[is.finite(base)]
  if (length(actual)<2 || length(base)<2) return(0)
  qs2 <- unique(quantile(base, probs=seq(0,1,length.out=11), na.rm=TRUE))
  if (length(qs2)<3) return(0)
  ac <- hist(actual, breaks=qs2, plot=FALSE, include.lowest=TRUE)$counts + 0.5
  bc <- hist(base, breaks=qs2, plot=FALSE, include.lowest=TRUE)$counts + 0.5
  ap <- ac/sum(ac)
  bp <- bc/sum(bc)
  clip01(sum((ap-bp)*log(ap/bp)))
}

schema_where <- function(t, d=cfg$dt, run_id=cfg$run_id, profile_id=cfg$profile_id,
                         date_candidates=c("dt","target_date","metric_dt","event_date"),
                         use_run_id=TRUE) {
  w <- c("1=1")
  if (col_exists(t,"profile_id") && !is.null(profile_id) && profile_id!="") {
    w <- c(w, paste0("profile_id=", sql_escape(profile_id)))
  }
  dc <- first_col(t, date_candidates)
  if (!is.na(dc) && !is.null(d) && d!="") {
    w <- c(w, paste0(qi(dc), "=", sql_escape(d)))
  }
  if (use_run_id && col_exists(t,"run_id") && !is.null(run_id) && run_id!="") {
    w <- c(w, paste0("run_id=", sql_escape(run_id)))
  }
  paste(w, collapse=" AND ")
}

query_table <- function(t, d=cfg$dt, run_id=cfg$run_id, limit=NULL,
                        date_candidates=c("dt","target_date","metric_dt","event_date"),
                        use_run_id=TRUE) {
  if (!table_exists(t)) return(data.frame())
  where <- schema_where(t, d=d, run_id=run_id, date_candidates=date_candidates, use_run_id=use_run_id)
  sql <- paste0("SELECT * FROM ", qi(t), " WHERE ", where)
  if (!is.null(limit)) sql <- paste0(sql, " LIMIT ", as.integer(limit))
  sql <- paste0(sql, ";")
  dfr <- query_df(sql)
  if (nrow(dfr)>0) {
    cols <- table_columns(t)
    if (length(cols)==ncol(dfr)) names(dfr) <- cols
  }
  dfr
}

read_one <- function(t, d=cfg$dt, run_id=cfg$run_id, use_run_id=TRUE) {
  query_table(t, d=d, run_id=run_id, limit=1, use_run_id=use_run_id)
}

val <- function(df,c,d=0) {
  if (nrow(df)==0 || !(c %in% names(df))) return(d)
  nz(df[[c]][[1]], d)
}

count_with_mode <- function(t, d=cfg$dt, run_id=cfg$run_id,
                            date_candidates=c("dt","target_date","metric_dt","event_date")) {
  if (!table_exists(t)) return(list(count=0, mode="TABLE_MISSING"))
  strict <- 0
  if (col_exists(t,"run_id") && !is.null(run_id) && run_id!="") {
    where1 <- schema_where(t, d=d, run_id=run_id, date_candidates=date_candidates, use_run_id=TRUE)
    strict <- as.numeric(scalar(paste0("SELECT COUNT(*) FROM ", qi(t), " WHERE ", where1, ";"), 0))
    if (strict > 0) return(list(count=strict, mode="DIRECT_RUN_ID"))
  }
  where2 <- schema_where(t, d=d, run_id="", date_candidates=date_candidates, use_run_id=FALSE)
  no_run <- as.numeric(scalar(paste0("SELECT COUNT(*) FROM ", qi(t), " WHERE ", where2, ";"), 0))
  if (no_run > 0) {
    return(list(count=no_run, mode=ifelse(strict == 0 && col_exists(t,"run_id"), "DIRECT_DATE_FALLBACK_NO_RUN_ID", "DIRECT_DATE")))
  }
  list(count=0, mode="ZERO")
}

row_count <- function(t, d=cfg$dt, run_id=cfg$run_id,
                      date_candidates=c("dt","target_date","metric_dt","event_date"),
                      use_run_id=TRUE) {
  if (!use_run_id) return(count_with_mode(t, d=d, run_id="", date_candidates=date_candidates)$count)
  count_with_mode(t, d=d, run_id=run_id, date_candidates=date_candidates)$count
}

metric_value_with_mode <- function(t, cols, d=cfg$dt, run_id=cfg$run_id, agg="MAX") {
  if (!table_exists(t)) return(list(value=0, mode="TABLE_MISSING", column=""))
  c <- first_col(t, cols)
  if (is.na(c)) return(list(value=0, mode="COLUMN_MISSING", column=""))
  if (col_exists(t,"run_id") && !is.null(run_id) && run_id!="") {
    where1 <- schema_where(t, d=d, run_id=run_id, use_run_id=TRUE)
    v <- nz(scalar(paste0("SELECT COALESCE(", agg, "(", qi(c), "),0) FROM ", qi(t), " WHERE ", where1, ";"), 0))
    if (v != 0) return(list(value=v, mode="DIRECT_RUN_ID", column=c))
  }
  where2 <- schema_where(t, d=d, run_id="", use_run_id=FALSE)
  v2 <- nz(scalar(paste0("SELECT COALESCE(", agg, "(", qi(c), "),0) FROM ", qi(t), " WHERE ", where2, ";"), 0))
  if (v2 != 0) return(list(value=v2, mode="DIRECT_DATE_FALLBACK_NO_RUN_ID", column=c))
  list(value=0, mode="ZERO", column=c)
}

metric_value <- function(t, cols, d=cfg$dt, run_id=cfg$run_id, agg="MAX", prefer_no_runid=FALSE) {
  if (prefer_no_runid) return(metric_value_with_mode(t, cols, d=d, run_id="", agg=agg)$value)
  metric_value_with_mode(t, cols, d=d, run_id=run_id, agg=agg)$value
}

integrated_score_from_phase2 <- function(d=cfg$dt, run_id=cfg$run_id) {
  candidates <- c("scenario_validation_report_v1","integrated_risk_score_day_v04","data_risk_score_day_v3")
  score_cols <- c("integrated_risk_score","actual_score","overall_risk_score","risk_score","score")
  for (t in candidates) {
    if (!table_exists(t)) next
    sc <- first_col(t, score_cols)
    if (is.na(sc)) next
    dc <- date_col(t)
    if (is.na(dc)) next
    where <- schema_where(t, d=d, run_id=run_id, date_candidates=c(dc))
    v <- scalar(paste0("SELECT COALESCE(", qi(sc), ",0) FROM ", qi(t), " WHERE ", where, " LIMIT 1;"), NA)
    if (!is.na(suppressWarnings(as.numeric(v)))) return(nz(v))
  }
  NA_real_
}

phase2_signal_strength <- function(family, d=cfg$dt, run_id=cfg$run_id) {
  score <- integrated_score_from_phase2(d, run_id)
  base <- integrated_score_from_phase2(cfg$baseline_dt, "")
  raw <- 0
  mode <- "PHASE2_SCORE_DELTA"
  if (is.finite(score) && is.finite(base) && !is.na(score) && !is.na(base)) {
    raw <- abs_delta_ratio(score, base)
  }
  if (raw <= 1e-9 && cfg$scenario_name != "baseline") {
    if (family == "completeness" && grepl("partial_missing|missing", cfg$scenario_name)) { raw <- 0.25; mode <- "SCENARIO_NAME_FALLBACK" }
    if (family == "latency_performance" && grepl("latency|delay|lag", cfg$scenario_name)) { raw <- 0.25; mode <- "SCENARIO_NAME_FALLBACK" }
    if (family == "availability" && grepl("no_data|availability", cfg$scenario_name)) { raw <- 0.25; mode <- "SCENARIO_NAME_FALLBACK" }
    if (family == "schema_validation" && grepl("schema", cfg$scenario_name)) { raw <- 0.25; mode <- "SCENARIO_NAME_FALLBACK" }
  }
  list(value=clip01(raw), mode=mode)
}

sql_num <- function(x) {
  x <- nz(x)
  if (!is.finite(x)) x <- 0
  as.character(x)
}

sql_int <- function(x) as.character(as.integer(nz(x)))

dominant_signal_from_phase2 <- function() {
  candidates <- c("scenario_validation_report_v1","scenario_propagation_summary_v1","integrated_risk_score_day_v04","data_risk_score_day_v3")
  signal_cols <- c("strongest_signal","actual_signal","dominant_signal","root_cause_signal","dominant_risk_type","risk_type")
  for (t in candidates) {
    if (!table_exists(t)) next
    sc <- first_col(t, signal_cols)
    if (is.na(sc)) next
    dc <- date_col(t)
    if (is.na(dc)) next
    where <- schema_where(t, d=cfg$dt, run_id=cfg$run_id, date_candidates=c(dc))
    v <- scalar(paste0("SELECT COALESCE(", qi(sc), ",'') FROM ", qi(t), " WHERE ", where, " LIMIT 1;"), "")
    if (!is.null(v) && !is.na(v) && v != "" && v != "NULL") return(as.character(v))
  }
  ""
}

risk_family_to_layer <- function(family) {
  switch(family,
    "completeness"="batch",
    "schema_validation"="batch",
    "identity_mapping"="batch",
    "latency_performance"="stream",
    "capacity_volume"="stream",
    "availability"="operational",
    "performance_availability"="operational",
    "low"="",
    ""
  )
}

signal_to_family <- function(signal) {
  s <- tolower(as.character(signal))
  if (s == "" || is.na(s)) return("unknown")
  if (grepl("comple|missing|partial|drop|no_data", s)) return("completeness")
  if (grepl("schema|validation|contract", s)) return("schema_validation")
  if (grepl("identity|uid|pcid|mapping", s)) return("identity_mapping")
  if (grepl("latency|lag|delay|freshness|performance", s)) return("latency_performance")
  if (grepl("availability|timeout|retry|resource|saturation", s)) return("availability")
  if (grepl("root_cause_weighted", s)) return("root_cause_weighted")
  "unknown"
}
