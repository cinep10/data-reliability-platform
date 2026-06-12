#!/usr/bin/env Rscript
# -----------------------------------------------------------------------------
# ARCHITECTURE LAYER: OBSERVABILITY REFERENCE EVIDENCE / EXPLANATION SUPPORT
#
# Produces root-cause confidence candidates for observability issues.
# Confidence is explanation confidence, not risk magnitude.
# -----------------------------------------------------------------------------
# CASE-OBS-001 Phase3-A
# R Analytics Enhancement + Root Cause Confidence.
# Input: OBS gap measurements + Baseline Science statistical evidence.
# Output: r_v05_observability_interpretation_day and enhanced r_v05_observability_analysis_day.

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))
suppressPackageStartupMessages({ library(jsonlite) })

args <- commandArgs(trailingOnly = TRUE)
profile_id <- arg_value(args, "--profile-id")
target_date <- arg_value(args, "--target-date")
scenario_name <- arg_value(args, "--scenario-name", "baseline")
run_id <- as.integer(arg_value(args, "--run-id", "0"))
source_gen_run_id <- as.integer(arg_value(args, "--source-gen-run-id", "0"))
baseline_window <- arg_value(args, "--baseline-window", "30d")
top_n <- as.integer(arg_value(args, "--top-n", "20"))
min_signal_score <- as.numeric(arg_value(args, "--min-signal-score", "0"))

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

lvl <- function(x) {
  s <- safe_number(x)
  if (s >= 0.75) "critical" else if (s >= 0.55) "high" else if (s >= 0.30) "warning" else if (s >= 0.08) "low" else "stable"
}
conf_level <- function(x) {
  s <- safe_number(x)
  if (s >= 0.80) "high" else if (s >= 0.55) "medium" else if (s >= 0.30) "low" else "weak"
}
prop_level <- function(x) {
  s <- safe_number(x)
  if (s >= 0.70) "high" else if (s >= 0.40) "medium" else if (s > 0) "low" else "none"
}
short_value <- function(x, n = 191) substr(ifelse(is.na(x) || !nzchar(as.character(x)), "unknown", as.character(x)), 1, n)
metric_names <- c("event_count", "pv", "uv", "visit", "conversion")
rate_cols <- c("missing_rate", "pv_missing_rate", "uv_missing_rate", "visit_missing_rate", "conversion_missing_rate")

read_scoped <- function(table_name) {
  read_scoped_table(con, table_name, profile_id, target_date, run_id, source_gen_run_id, scenario_name)
}
max0 <- function(x) { y <- safe_number(x); if (length(y) == 0) return(0); m <- suppressWarnings(max(y, na.rm = TRUE)); ifelse(is.finite(m), m, 0) }
sum0 <- function(x) { y <- safe_number(x); if (length(y) == 0) return(0); s <- suppressWarnings(sum(y, na.rm = TRUE)); ifelse(is.finite(s), s, 0) }

# Keep text columns within conservative MariaDB varchar limits.
# iOS app/SDK targeted scenarios can merge multiple evidence sources; without
# truncation the merged analysis_summary may exceed the deployed column length.
truncate_text <- function(x, n = 900) {
  y <- ifelse(is.na(x), "", as.character(x))
  ifelse(nchar(y, type = "chars") > n, paste0(substr(y, 1, n - 15), "... [truncated]"), y)
}
truncate_json <- function(x, n = 60000) {
  y <- ifelse(is.na(x), "{}", as.character(x))
  ifelse(nchar(y, type = "chars") > n, paste0(substr(y, 1, n - 20), "...\"truncated\":true}"), y)
}

# Runtime compatibility for older deployed schemas.  The Phase4-D realistic
# measurement patch can merge several evidence source names, so source_table
# must either be widened or safely truncated before insert.
if (table_exists(con, "r_v05_observability_interpretation_day")) {
  tryCatch({
    execute_sql(con, "ALTER TABLE r_v05_observability_interpretation_day MODIFY COLUMN source_table VARCHAR(512) DEFAULT NULL")
  }, error = function(e) {
    message(sprintf("[WARN] source_table widening skipped: %s", e$message))
  })
}

# ------------------------------------------------------------------
# Baseline Science statistical evidence summary for OBS reference domain.
# It is a reference domain, so it may score 0 in baseline, but still gives
# statistical context and co-movement columns when present.
# ------------------------------------------------------------------
stat <- if (table_exists(con, "v05_baseline_science_statistical_evidence_day")) {
  df <- read_scoped_table(con, "v05_baseline_science_statistical_evidence_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
  if (nrow(df) > 0 && "evidence_domain" %in% names(df)) df[df$evidence_domain %in% c("observability_expected"), , drop = FALSE] else data.frame()
} else data.frame()

statistical_context <- list(
  evidence_rows = nrow(stat),
  max_statistical_score = if (nrow(stat) > 0 && "statistical_score" %in% names(stat)) max0(stat$statistical_score) else 0,
  max_abs_z = if (nrow(stat) > 0 && "z_score" %in% names(stat)) max0(abs(safe_number(stat$z_score))) else 0,
  max_percentile = if (nrow(stat) > 0 && "historical_percentile" %in% names(stat)) max0(stat$historical_percentile) else 0,
  max_co_movement = if (nrow(stat) > 0 && "co_movement_score" %in% names(stat)) max0(stat$co_movement_score) else 0
)

candidates <- list()
add_candidate <- function(root_dim, root_val, label, source_table, total_missing, missing_count, gap_rates, affected_metric_list, evidence_rows, detail) {
  root_val <- short_value(root_val)
  gap_rates <- safe_number(gap_rates)
  gap_rates <- gap_rates[is.finite(gap_rates)]
  if (length(gap_rates) == 0) gap_rates <- 0
  max_gap <- max0(gap_rates)
  avg_gap <- mean(gap_rates)
  affected_metrics <- length(unique(affected_metric_list[!is.na(affected_metric_list) & nzchar(as.character(affected_metric_list))]))
  multi_metric_gap_score <- clamp01(affected_metrics / 5)
  baseline_deviation_score <- clamp01(max(max_gap, avg_gap) * 3)
  segment_concentration <- if (safe_number(total_missing) > 0) clamp01(safe_number(missing_count) / safe_number(total_missing)) else 0
  # KPI distortion emphasizes PV/UV/Visit/Conversion movement rather than event_count only.
  kpi_distortion_score <- clamp01(mean(pmin(gap_rates, 1)))
  # Statistical severity consumes C4 stats when non-zero, but direct gap evidence keeps anomaly scenarios interpretable.
  stat_score <- max(safe_number(statistical_context$max_statistical_score), baseline_deviation_score * 0.65, kpi_distortion_score * 0.55)
  propagation_strength <- clamp01(0.55 * multi_metric_gap_score + 0.25 * safe_number(statistical_context$max_co_movement) + 0.20 * ifelse(affected_metrics >= 3, 1, 0))
  root_cause_confidence <- clamp01(
    0.30 * segment_concentration +
      0.25 * multi_metric_gap_score +
      0.25 * stat_score +
      0.20 * propagation_strength
  )
  if (root_cause_confidence < min_signal_score && max_gap <= 0) return(invisible(NULL))
  candidates[[length(candidates) + 1]] <<- list(
    root_cause_dimension = root_dim,
    root_cause_value = root_val,
    root_cause_label = label,
    segment_concentration = segment_concentration,
    affected_metrics = affected_metrics,
    affected_metric_list = paste(unique(affected_metric_list), collapse = ","),
    propagation_strength = propagation_strength,
    propagation_level = prop_level(propagation_strength),
    statistical_severity_score = stat_score,
    statistical_severity_level = lvl(stat_score),
    baseline_deviation_score = baseline_deviation_score,
    multi_metric_gap_score = multi_metric_gap_score,
    kpi_distortion_score = kpi_distortion_score,
    root_cause_confidence = root_cause_confidence,
    confidence_level = conf_level(root_cause_confidence),
    evidence_row_count = safe_number(evidence_rows),
    source_table = source_table,
    recommended_semantic_risk = ifelse(root_cause_confidence >= 0.30, "Operational Observability Reliability", "None"),
    recommended_action = if (root_cause_confidence >= 0.55) {
      paste0("Validate tagging/SDK interface for ", root_dim, "=", root_val, " and compare WebServer vs WC collection path.")
    } else if (root_cause_confidence >= 0.30) {
      paste0("Review observability gap concentration for ", root_dim, "=", root_val, ".")
    } else {
      "No action"
    },
    analysis_status = ifelse(root_cause_confidence >= 0.55, "SIGNAL", ifelse(root_cause_confidence >= 0.30, "WATCH", "PASS")),
    analysis_summary = sprintf(
      "%s=%s confidence=%.3f concentration=%.3f affected_metrics=%d propagation=%s severity=%s max_gap=%.4f",
      root_dim, root_val, root_cause_confidence, segment_concentration, affected_metrics, prop_level(propagation_strength), lvl(stat_score), max_gap
    ),
    detail_json = toJSON(c(list(source = source_table, metrics = unique(affected_metric_list), max_gap_rate = max_gap, avg_gap_rate = avg_gap), detail, statistical_context), auto_unbox = TRUE, null = "null")
  )
}

# ------------------------------------------------------------------
# Direct OBS segment measurements.
# ------------------------------------------------------------------
app <- read_scoped("v05_obs_app_version_measurement_day")
if (nrow(app) > 0) {
  total_missing <- sum0(app$missing_count)
  for (i in seq_len(nrow(app))) {
    r <- app[i,]
    rates <- safe_number(unlist(r[intersect(rate_cols, names(r))]))
    affected <- c("event_count", "pv", "uv", "visit", "conversion")[seq_along(rates)][rates > 0.01]
    val <- paste(short_value(r$app_platform), short_value(r$app_version), short_value(r$sdk_version), sep = "/")
    add_candidate("app_version", val, val, "v05_obs_app_version_measurement_day", total_missing, r$missing_count, rates, affected, 1,
                  list(app_platform = as.character(r$app_platform), app_version = as.character(r$app_version), sdk_version = as.character(r$sdk_version)))
  }
}

sdk <- read_scoped("v05_obs_sdk_version_measurement_day")
if (nrow(sdk) > 0) {
  total_missing <- sum0(sdk$missing_count)
  for (i in seq_len(nrow(sdk))) {
    r <- sdk[i,]
    rates <- safe_number(unlist(r[intersect(rate_cols, names(r))]))
    affected <- c("event_count", "pv", "uv", "visit", "conversion")[seq_along(rates)][rates > 0.01]
    val <- paste(short_value(r$app_platform), short_value(r$sdk_version), sep = "/")
    add_candidate("sdk_version", val, val, "v05_obs_sdk_version_measurement_day", total_missing, r$missing_count, rates, affected, 1,
                  list(app_platform = as.character(r$app_platform), sdk_version = as.character(r$sdk_version)))
  }
}

url <- read_scoped("v05_obs_url_gap_day")
if (nrow(url) > 0) {
  total_missing <- sum0(url$missing_count)
  # Limit row explosion: use top 100 URL candidates by missing_count/gap rate.
  if ("missing_count" %in% names(url)) url <- url[order(-safe_number(url$missing_count), -safe_number(url$missing_rate)), , drop = FALSE]
  url <- head(url, 100)
  for (i in seq_len(nrow(url))) {
    r <- url[i,]
    affected <- c("event_count", "uv")[safe_number(c(r$missing_rate, r$uv_missing_rate)) > 0.01]
    val <- short_value(r$surface_path)
    add_candidate("url_path", val, val, "v05_obs_url_gap_day", total_missing, r$missing_count, c(r$missing_rate, r$uv_missing_rate), affected, 1,
                  list(app_platform = as.character(r$app_platform), app_version = as.character(r$app_version), sdk_version = as.character(r$sdk_version), surface_path = as.character(r$surface_path)))
  }
}

client <- read_scoped("v05_obs_client_gap_day")
if (nrow(client) > 0) {
  total_missing <- sum0(client$missing_count)
  for (i in seq_len(nrow(client))) {
    r <- client[i,]
    affected <- c("event_count", "uv")[safe_number(c(r$missing_rate, r$uv_missing_rate)) > 0.01]
    val <- paste(short_value(r$app_platform), short_value(r$device_type), short_value(r$browser_family), short_value(r$os_family), sep = "/")
    add_candidate("client", val, val, "v05_obs_client_gap_day", total_missing, r$missing_count, c(r$missing_rate, r$uv_missing_rate), affected, 1,
                  list(app_platform = as.character(r$app_platform), app_version = as.character(r$app_version), sdk_version = as.character(r$sdk_version), device_type = as.character(r$device_type), browser_family = as.character(r$browser_family), os_family = as.character(r$os_family)))
  }
}

metric_gap <- read_scoped("v05_obs_metric_gap_day")
if (nrow(metric_gap) > 0) {
  # Aggregate by dimension_type/dimension_value to produce metric co-movement interpretation.
  keys <- unique(paste(metric_gap$dimension_type, metric_gap$dimension_value, sep = "\u0001"))
  for (key in keys) {
    parts <- strsplit(key, "\u0001", fixed = TRUE)[[1]]
    g <- metric_gap[paste(metric_gap$dimension_type, metric_gap$dimension_value, sep = "\u0001") == key, , drop = FALSE]
    rates <- safe_number(g$gap_rate)
    affected <- as.character(g$metric_name[rates > 0.01])
    add_candidate(paste0("metric_", parts[[1]]), short_value(parts[[2]]), short_value(parts[[2]]), "v05_obs_metric_gap_day", sum0(metric_gap$missing_value), sum0(g$missing_value), rates, affected, nrow(g),
                  list(dimension_type = parts[[1]], dimension_value = parts[[2]]))
  }
}


# ------------------------------------------------------------------
# Phase4-D realistic scenario explanation measurements.
# These OBS tables are reference/explanation inputs only. They do not expand
# the generic risk pattern taxonomy. They help explain the Failure Mechanism:
# - identity_integrity_breakage       -> app_version_concentration
# - semantic_attribution_distortion   -> sdk_version_concentration
# - critical_event_loss               -> purchase_event_criticality
# ------------------------------------------------------------------
identity_gap <- read_scoped("v05_obs_identity_gap_day")
if (nrow(identity_gap) > 0) {
  total_identity_missing <- sum0(identity_gap$uid_missing_count)
  for (i in seq_len(nrow(identity_gap))) {
    r <- identity_gap[i,]
    rates <- safe_number(c(r$uid_missing_rate, r$login_user_gap_rate, r$identity_integrity_gap))
    affected <- c("uid", "login_user", "identity_integrity")[rates > 0.01]
    val <- paste(short_value(r$app_platform), short_value(r$app_version), short_value(r$sdk_version), sep = "/")
    # Use uid_missing_count for concentration; fallback to identity gap magnitude
    # when count is unavailable so null_uid scenarios still produce a candidate.
    miss <- if ("uid_missing_count" %in% names(r)) safe_number(r$uid_missing_count) else max0(rates)
    total <- if (safe_number(total_identity_missing) > 0) total_identity_missing else sum0(identity_gap$identity_integrity_gap)
    add_candidate(
      "app_version", val, val, "v05_obs_identity_gap_day", total, miss,
      rates, affected, 1,
      list(
        app_platform = as.character(r$app_platform),
        app_version = as.character(r$app_version),
        sdk_version = as.character(r$sdk_version),
        uid_missing_rate = safe_number(r$uid_missing_rate),
        login_user_gap_rate = safe_number(r$login_user_gap_rate),
        identity_integrity_gap = safe_number(r$identity_integrity_gap),
        mechanism_hint = "identity_integrity_breakage",
        mechanism_source_hint = "app_version_concentration"
      )
    )
  }
}

url_semantic_gap <- read_scoped("v05_obs_url_semantic_gap_day")
if (nrow(url_semantic_gap) > 0) {
  # Prefer shifted rows; keep all rows because over-count and under-count are
  # both useful to explain URL/category attribution collapse.
  total_semantic_shift <- sum0(url_semantic_gap$under_count) + sum0(url_semantic_gap$over_count)
  for (i in seq_len(nrow(url_semantic_gap))) {
    r <- url_semantic_gap[i,]
    rates <- safe_number(c(r$distribution_shift_score, r$under_rate, r$over_rate))
    affected <- c("url_distribution", "url_undercount", "url_overcount")[rates > 0.01]
    val <- paste(short_value(r$app_platform), short_value(r$sdk_version), sep = "/")
    shift_count <- safe_number(r$under_count) + safe_number(r$over_count)
    total <- if (safe_number(total_semantic_shift) > 0) total_semantic_shift else sum0(url_semantic_gap$distribution_shift_score)
    add_candidate(
      "sdk_version", val, val, "v05_obs_url_semantic_gap_day", total, shift_count,
      rates, affected, 1,
      list(
        app_platform = as.character(r$app_platform),
        app_version = as.character(r$app_version),
        sdk_version = as.character(r$sdk_version),
        surface_path = as.character(r$surface_path),
        distribution_shift_score = safe_number(r$distribution_shift_score),
        url_collapse_flag = safe_number(r$url_collapse_flag),
        shifted_direction = as.character(r$shifted_direction),
        mechanism_hint = "semantic_attribution_distortion",
        mechanism_source_hint = "sdk_version_concentration"
      )
    )
  }
}

business_kpi_gap <- read_scoped("v05_obs_business_kpi_gap_day")
if (nrow(business_kpi_gap) > 0) {
  total_business_distortion <- sum0(business_kpi_gap$business_kpi_distortion_score)
  for (i in seq_len(nrow(business_kpi_gap))) {
    r <- business_kpi_gap[i,]
    rates <- safe_number(c(
      r$purchase_event_gap_rate,
      r$conversion_gap_rate,
      r$revenue_proxy_gap_rate,
      r$business_kpi_distortion_score
    ))
    affected <- c("purchase_event", "conversion", "revenue_proxy", "business_kpi")[rates > 0.01]
    val <- paste(short_value(r$scope_type), short_value(r$scope_value), sep = ":")
    # business_kpi_distortion_score is already a normalized criticality/impact
    # measurement. Treat it as concentration weight for candidate confidence.
    distortion <- max0(c(r$business_kpi_distortion_score, r$purchase_event_gap_rate, r$conversion_gap_rate, r$revenue_proxy_gap_rate))
    total <- if (safe_number(total_business_distortion) > 0) total_business_distortion else distortion
    add_candidate(
      "business_kpi", val, val, "v05_obs_business_kpi_gap_day", total, distortion,
      rates, affected, 1,
      list(
        scope_type = as.character(r$scope_type),
        scope_value = as.character(r$scope_value),
        purchase_event_gap_rate = safe_number(r$purchase_event_gap_rate),
        conversion_gap_rate = safe_number(r$conversion_gap_rate),
        revenue_proxy_gap_rate = safe_number(r$revenue_proxy_gap_rate),
        traffic_preservation_score = safe_number(r$traffic_preservation_score),
        business_kpi_distortion_score = safe_number(r$business_kpi_distortion_score),
        mechanism_hint = "critical_event_loss",
        mechanism_source_hint = "purchase_event_criticality"
      )
    )
  }
}

# ------------------------------------------------------------------
# Persist results.
# ------------------------------------------------------------------
# Phase4-A hotfix: the iOS app/SDK targeted scenarios can produce the same
# root_cause_dimension/root_cause_value from multiple evidence sources. The
# table primary key intentionally treats dimension+value as the stable
# candidate identity, so we must collapse duplicates before insert. Keep the
# strongest candidate and merge source/evidence context for explainability.
dedupe_candidates <- function(items) {
  if (length(items) == 0) return(items)
  out <- list()
  for (x in items) {
    key <- paste0(as.character(x$root_cause_dimension), "\001", as.character(x$root_cause_value))
    if (!key %in% names(out)) {
      out[[key]] <- x
    } else {
      old <- out[[key]]
      old_score <- safe_number(old$root_cause_confidence)
      new_score <- safe_number(x$root_cause_confidence)
      old_metrics <- safe_number(old$affected_metrics)
      new_metrics <- safe_number(x$affected_metrics)
      keep_new <- (new_score > old_score) || (new_score == old_score && new_metrics > old_metrics)
      chosen <- if (keep_new) x else old
      other <- if (keep_new) old else x
      # Preserve multi-source provenance without changing the stable PK.
      chosen$source_table <- truncate_text(paste(unique(c(as.character(chosen$source_table), as.character(other$source_table))), collapse = ","), 500)
      chosen$evidence_row_count <- safe_number(chosen$evidence_row_count) + safe_number(other$evidence_row_count)
      chosen$analysis_summary <- truncate_text(paste(unique(c(as.character(chosen$analysis_summary), as.character(other$analysis_summary))), collapse = " | "), 900)
      chosen$detail_json <- truncate_json(toJSON(list(
        chosen = tryCatch(fromJSON(chosen$detail_json, simplifyVector = FALSE), error = function(e) list(raw = truncate_text(chosen$detail_json, 2000))),
        duplicate_merged = tryCatch(fromJSON(other$detail_json, simplifyVector = FALSE), error = function(e) list(raw = truncate_text(other$detail_json, 2000)))
      ), auto_unbox = TRUE, null = "null"), 60000)
      out[[key]] <- chosen
    }
  }
  unname(out)
}

candidates <- dedupe_candidates(candidates)

delete_scoped_rows(con, "r_v05_observability_interpretation_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
if (length(candidates) == 0) {
  # Insert a stable/pass row so downstream validation can distinguish no-signal from missing execution.
  candidates[[1]] <- list(
    root_cause_dimension = "none", root_cause_value = "none", root_cause_label = "none",
    segment_concentration = 0, affected_metrics = 0, affected_metric_list = "",
    propagation_strength = 0, propagation_level = "none", statistical_severity_score = 0, statistical_severity_level = "stable",
    baseline_deviation_score = 0, multi_metric_gap_score = 0, kpi_distortion_score = 0,
    root_cause_confidence = 0, confidence_level = "weak", evidence_row_count = nrow(stat), source_table = "none",
    recommended_semantic_risk = "None", recommended_action = "No action", analysis_status = "NO_SIGNAL",
    analysis_summary = "no observability root-cause signal", detail_json = truncate_json(toJSON(list(statistical_context = statistical_context), auto_unbox = TRUE, null = "null"), 60000)
  )
}

scores <- vapply(candidates, function(x) safe_number(x$root_cause_confidence), numeric(1))
ord <- order(-scores)
ord <- ord[seq_len(min(length(ord), max(1, top_n)))]
rank <- 1
for (j in ord) {
  x <- candidates[[j]]
  insert_schema_aware(con, "r_v05_observability_interpretation_day", list(
    profile_id = profile_id, target_date = target_date, scenario_name = scenario_name,
    run_id = run_id, source_gen_run_id = source_gen_run_id,
    root_cause_rank = rank,
    root_cause_dimension = x$root_cause_dimension,
    root_cause_value = x$root_cause_value,
    root_cause_label = x$root_cause_label,
    segment_concentration = x$segment_concentration,
    affected_metrics = x$affected_metrics,
    affected_metric_list = x$affected_metric_list,
    propagation_strength = x$propagation_strength,
    propagation_level = x$propagation_level,
    statistical_severity_score = x$statistical_severity_score,
    statistical_severity_level = x$statistical_severity_level,
    baseline_deviation_score = x$baseline_deviation_score,
    multi_metric_gap_score = x$multi_metric_gap_score,
    kpi_distortion_score = x$kpi_distortion_score,
    root_cause_confidence = x$root_cause_confidence,
    confidence_level = x$confidence_level,
    evidence_row_count = x$evidence_row_count,
    source_table = truncate_text(x$source_table, 500),
    recommended_semantic_risk = x$recommended_semantic_risk,
    recommended_action = x$recommended_action,
    analysis_status = x$analysis_status,
    analysis_summary = truncate_text(x$analysis_summary, 900),
    detail_json = truncate_json(x$detail_json, 60000)
  ))
  rank <- rank + 1
}

# Enhance the existing OBS analysis row with top interpretation values when present.
top <- candidates[[ord[[1]]]]
if (table_exists(con, "r_v05_observability_analysis_day")) {
  for (col in c("affected_metrics", "propagation_strength", "propagation_level", "segment_concentration", "root_cause_confidence", "root_cause_dimension", "root_cause_value", "root_cause_label", "statistical_severity_score", "statistical_severity_level")) {
    # DDL should have added these. This is defensive for partial patch application.
    if (!column_exists(con, "r_v05_observability_analysis_day", col)) {
      type <- if (grepl("score|strength|concentration|confidence", col)) "DOUBLE DEFAULT 0" else if (col == "affected_metrics") "INT DEFAULT 0" else "VARCHAR(255) DEFAULT NULL"
      ensure_column(con, "r_v05_observability_analysis_day", col, type)
    }
  }
  execute_sql(con, paste0(
    "UPDATE r_v05_observability_analysis_day SET ",
    "affected_metrics=?, propagation_strength=?, propagation_level=?, segment_concentration=?, root_cause_confidence=?, ",
    "root_cause_dimension=?, root_cause_value=?, root_cause_label=?, statistical_severity_score=?, statistical_severity_level=? ",
    "WHERE profile_id=? AND target_date=? AND scenario_name=? AND run_id=? AND source_gen_run_id=?"
  ), list(
    top$affected_metrics, top$propagation_strength, top$propagation_level, top$segment_concentration, top$root_cause_confidence,
    top$root_cause_dimension, top$root_cause_value, top$root_cause_label, top$statistical_severity_score, top$statistical_severity_level,
    profile_id, target_date, scenario_name, run_id, source_gen_run_id
  ))
}

cat(sprintf(
  "[OK] build_v05_observability_interpretation scenario=%s run_id=%d rows=%d top_dimension=%s top_value=%s confidence=%.6f affected_metrics=%d propagation=%s severity=%s\n",
  scenario_name, run_id, length(ord), top$root_cause_dimension, top$root_cause_value, top$root_cause_confidence, top$affected_metrics, top$propagation_level, top$statistical_severity_level
))
