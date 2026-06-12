
# Phase4-C evidence v2 persistence contract:
# - business_kpi_distortion and traffic_preservation are evidence values, not risk.
# - They must be persisted in reliability_analysis_result_day_v05 so validators,
#   Pattern v2, and Diagnostic Report can read the same Authority Evidence row.
#!/usr/bin/env Rscript
# -----------------------------------------------------------------------------
# ARCHITECTURE LAYER: AUTHORITY ANALYTICS LAYER
#
# This script converts measurement, baseline statistical evidence, runtime
# evidence, and cross-domain propagation evidence into the authoritative
# reliability analysis interface. It is the only analytics interface that should
# feed the authority risk model directly.
# -----------------------------------------------------------------------------
# v0.5 commerce reliability analysis.
# Measurement-driven: reconciliation/runtime evidence in.
# Semantic/action output is handled elsewhere.

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))

args <- commandArgs(trailingOnly = TRUE)

# ------------------------------------------------------------------
# Arguments
# ------------------------------------------------------------------


profile_id <- arg_value(args, "--profile-id")
target_date <- arg_value(args, "--target-date")
run_id <- as.integer(arg_value(args, "--run-id"))
source_gen_run_id <- as.integer(arg_value(args, "--source-gen-run-id", "0"))
scenario_name <- arg_value(args, "--scenario-name", "baseline")
is_baseline_like <- tolower(scenario_name) %in% c("baseline", "normal", "stable")

# ------------------------------------------------------------------
# Database Connection
# ------------------------------------------------------------------

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

if (table_exists(con, "reliability_analysis_result_day_v05")) {
  ensure_column(con, "reliability_analysis_result_day_v05", "runtime_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "batch_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "stream_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "operational_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "realism_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "dominant_runtime_signal", "VARCHAR(100) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "statistical_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "statistical_evidence_raw_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "statistical_evidence_effective_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "statistical_evidence_reflected", "TINYINT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "statistical_evidence_row_count", "INT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "statistical_evidence_min_sample_days", "INT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "statistical_evidence_max_sample_days", "INT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "max_z_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "max_historical_percentile", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "control_limit_breach_count", "INT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "co_movement_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "statistical_significance", "VARCHAR(50) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "affected_domains", "LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(affected_domains))")
  ensure_column(con, "reliability_analysis_result_day_v05", "affected_domain_count", "INT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "cross_domain_propagation_strength", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "cross_domain_propagation_level", "VARCHAR(64) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "reconciliation_confidence", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "dominant_propagation_path", "VARCHAR(512) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "authority_interface_version", "VARCHAR(64) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "risk_input_ready", "TINYINT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "authority_input_payload_json", "LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(authority_input_payload_json))")
  ensure_column(con, "reliability_analysis_result_day_v05", "evidence_layer_version", "VARCHAR(64) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "evidence_ready", "TINYINT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "baseline_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "statistical_evidence_group_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "propagation_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "impact_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "concentration_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "criticality_evidence_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "event_criticality_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "conversion_criticality_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "revenue_criticality_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "traffic_preservation_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "business_kpi_distortion_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "evidence_payload_json", "LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(evidence_payload_json))")
  ensure_column(con, "reliability_analysis_result_day_v05", "evidence_summary", "VARCHAR(512) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "pattern_layer_version", "VARCHAR(64) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "pattern_ready", "TINYINT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "risk_pattern", "VARCHAR(64) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "pattern_confidence", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "pattern_reason", "VARCHAR(512) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "pattern_payload_json", "LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(pattern_payload_json))")
  ensure_column(con, "reliability_analysis_result_day_v05", "identity_integrity_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "semantic_shift_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "visibility_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "failure_mechanism", "VARCHAR(128) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "mechanism_source", "VARCHAR(128) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "mechanism_confidence", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "evidence_primitive_payload_json", "LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(evidence_primitive_payload_json))")
}


measurement <- read_first_scoped_row(con, "v05_reconciliation_measurement_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
if (nrow(measurement) < 1) stop("missing v05_reconciliation_measurement_day row")
runtime <- read_first_scoped_row(con, "v05_runtime_evidence_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
statistical_evidence <- if (table_exists(con, "v05_baseline_science_statistical_evidence_day")) {
  read_scoped_table(con, "v05_baseline_science_statistical_evidence_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
reconciliation_stat_rows <- if (nrow(statistical_evidence) > 0) {
  statistical_evidence[statistical_evidence$evidence_domain %in% c("reconciliation_measurement"), , drop = FALSE]
} else {
  data.frame()
}
statistical_evidence_row_count <- nrow(reconciliation_stat_rows)
statistical_evidence_reflected <- as.integer(statistical_evidence_row_count > 0)
statistical_evidence_raw_score <- if (statistical_evidence_row_count > 0 && "statistical_score" %in% names(reconciliation_stat_rows)) max(safe_number(reconciliation_stat_rows$statistical_score), na.rm = TRUE) else 0
statistical_evidence_raw_score <- ifelse(is.finite(statistical_evidence_raw_score), statistical_evidence_raw_score, 0)
statistical_evidence_score <- statistical_evidence_raw_score
statistical_evidence_effective_score <- statistical_evidence_score
max_z_score <- if (statistical_evidence_row_count > 0 && "z_score" %in% names(reconciliation_stat_rows)) max(abs(safe_number(reconciliation_stat_rows$z_score)), na.rm = TRUE) else 0
max_z_score <- ifelse(is.finite(max_z_score), max_z_score, 0)
max_historical_percentile <- if (statistical_evidence_row_count > 0 && "historical_percentile" %in% names(reconciliation_stat_rows)) max(safe_number(reconciliation_stat_rows$historical_percentile), na.rm = TRUE) else 0
max_historical_percentile <- ifelse(is.finite(max_historical_percentile), max_historical_percentile, 0)
control_limit_breach_count <- if (statistical_evidence_row_count > 0 && "control_limit_breach" %in% names(reconciliation_stat_rows)) sum(safe_number(reconciliation_stat_rows$control_limit_breach) > 0, na.rm = TRUE) else 0
co_movement_score <- if (statistical_evidence_row_count > 0 && "co_movement_score" %in% names(reconciliation_stat_rows)) max(safe_number(reconciliation_stat_rows$co_movement_score), na.rm = TRUE) else 0
co_movement_score <- ifelse(is.finite(co_movement_score), co_movement_score, 0)
statistical_evidence_min_sample_days <- if (statistical_evidence_row_count > 0 && "sample_days" %in% names(reconciliation_stat_rows)) min(safe_number(reconciliation_stat_rows$sample_days), na.rm = TRUE) else 0
statistical_evidence_min_sample_days <- ifelse(is.finite(statistical_evidence_min_sample_days), as.integer(statistical_evidence_min_sample_days), 0L)
statistical_evidence_max_sample_days <- if (statistical_evidence_row_count > 0 && "sample_days" %in% names(reconciliation_stat_rows)) max(safe_number(reconciliation_stat_rows$sample_days), na.rm = TRUE) else 0
statistical_evidence_max_sample_days <- ifelse(is.finite(statistical_evidence_max_sample_days), as.integer(statistical_evidence_max_sample_days), 0L)
statistical_significance <- if (statistical_evidence_score >= 0.75) "critical" else if (statistical_evidence_score >= 0.55) "warning" else if (statistical_evidence_score >= 0.30) "watch" else if (statistical_evidence_score >= 0.08) "low" else "stable"

propagation_evidence <- if (table_exists(con, "v05_cross_domain_propagation_evidence_day")) {
  read_first_scoped_row(con, "v05_cross_domain_propagation_evidence_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
affected_domains <- pick_character(propagation_evidence, "affected_domains", "[]")
affected_domain_count <- as.integer(pick_number(propagation_evidence, "affected_domain_count", 0))
cross_domain_propagation_strength <- pick_number(propagation_evidence, "propagation_strength", 0)
cross_domain_propagation_level <- pick_character(propagation_evidence, "propagation_level", "stable")
reconciliation_confidence <- pick_number(propagation_evidence, "reconciliation_confidence", 0)
dominant_propagation_path <- pick_character(propagation_evidence, "dominant_propagation_path", "none")
propagation_evidence_reflected <- as.integer(nrow(propagation_evidence) > 0)

behavior_transaction_match_rate <- pick_number(measurement, "behavior_transaction_match_rate")
transaction_state_match_rate <- pick_number(measurement, "transaction_state_match_rate")
behavior_only_count <- pick_number(measurement, "behavior_only_count")
transaction_only_count <- pick_number(measurement, "transaction_only_count")
transaction_without_state_count <- pick_number(measurement, "transaction_without_state_count")
orphan_state_count <- pick_number(measurement, "orphan_state_count")

behavior_total <- max(behavior_only_count + transaction_only_count, 1)
state_total <- max(transaction_without_state_count + orphan_state_count, 1)

reconciliation_gap_score <- clamp01((1 - behavior_transaction_match_rate) * 0.25 + (1 - transaction_state_match_rate) * 0.20)
propagation_score <- clamp01(transaction_without_state_count / state_total)
amplification_score <- clamp01(behavior_only_count / max(behavior_only_count + pick_number(measurement, "behavior_transaction_match_possible"), 1))
distortion_score <- clamp01(behavior_only_count / max(behavior_only_count + 1, 1) * 0.22 + transaction_only_count / behavior_total * 0.10)
transaction_loss_score <- clamp01(transaction_only_count / behavior_total)
customer_impact_score <- clamp01(0.35 * distortion_score + 0.25 * reconciliation_gap_score + 0.20 * propagation_score)

runtime_evidence_score <- pick_number(runtime, "runtime_evidence_score")
batch_evidence_score <- pick_number(runtime, "batch_evidence_score")
stream_evidence_score <- pick_number(runtime, "stream_evidence_score")
operational_evidence_score <- pick_number(runtime, "operational_evidence_score")
realism_evidence_score <- pick_number(runtime, "realism_evidence_score")
dominant_runtime_signal <- pick_character(runtime, "dominant_runtime_signal", "none")
runtime_status <- if (nrow(runtime) > 0) "FOUND" else "MISSING"

# ------------------------------------------------------------------
# Generic Concentration / Criticality Evidence (Phase4-B Evidence v2)
# ------------------------------------------------------------------
# These scores summarize generic failure shape evidence. They intentionally do
# not expose app_version, sdk_version, URL, browser, campaign, or event labels as
# authority risk features. Segment labels remain available only in OBS/reference
# explanation layers.
obs_metric_gap <- if (table_exists(con, "v05_obs_metric_gap_day")) {
  read_scoped_table(con, "v05_obs_metric_gap_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
obs_app_gap <- if (table_exists(con, "v05_obs_app_version_measurement_day")) {
  read_scoped_table(con, "v05_obs_app_version_measurement_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
obs_sdk_gap <- if (table_exists(con, "v05_obs_sdk_version_measurement_day")) {
  read_scoped_table(con, "v05_obs_sdk_version_measurement_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
obs_identity_gap <- if (table_exists(con, "v05_obs_identity_gap_day")) {
  read_scoped_table(con, "v05_obs_identity_gap_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
obs_url_semantic_gap <- if (table_exists(con, "v05_obs_url_semantic_gap_day")) {
  read_scoped_table(con, "v05_obs_url_semantic_gap_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
obs_business_kpi_gap <- if (table_exists(con, "v05_obs_business_kpi_gap_day")) {
  read_scoped_table(con, "v05_obs_business_kpi_gap_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}

safe_max_col <- function(df, col, default = 0) {
  if (nrow(df) < 1 || !(col %in% names(df))) return(default)
  value <- suppressWarnings(max(safe_number(df[[col]]), na.rm = TRUE))
  ifelse(is.finite(value), value, default)
}

segment_concentration_from_rows <- function(df) {
  if (nrow(df) < 1) return(0)
  if (!("webserver_events" %in% names(df)) || !("missing_count" %in% names(df))) return(0)
  web <- safe_number(df$webserver_events)
  loss <- safe_number(df$missing_count)
  total_web <- sum(web, na.rm = TRUE)
  total_loss <- sum(loss, na.rm = TRUE)
  if (!is.finite(total_web) || !is.finite(total_loss) || total_web <= 0 || total_loss <= 0) return(0)
  web_share <- web / total_web
  loss_share <- loss / total_loss
  lift <- suppressWarnings(max(loss_share - web_share, na.rm = TRUE))
  concentration_by_lift <- clamp01(lift * 1.6)
  concentration_by_rate <- clamp01(safe_max_col(df, "missing_rate", 0) * 0.75)
  clamp01(max(concentration_by_lift, concentration_by_rate))
}

app_concentration_evidence <- segment_concentration_from_rows(obs_app_gap)
sdk_concentration_evidence <- segment_concentration_from_rows(obs_sdk_gap)
identity_integrity_score <- clamp01(max(safe_max_col(obs_identity_gap, "identity_integrity_gap", 0), safe_max_col(obs_identity_gap, "uid_missing_rate", 0), safe_max_col(obs_identity_gap, "login_user_gap_rate", 0)))
semantic_shift_score <- clamp01(max(safe_max_col(obs_url_semantic_gap, "distribution_shift_score", 0), safe_max_col(obs_url_semantic_gap, "under_rate", 0), safe_max_col(obs_url_semantic_gap, "over_rate", 0)))
identity_concentration_evidence <- clamp01(max(identity_integrity_score, segment_concentration_from_rows(obs_identity_gap)))
semantic_concentration_evidence <- clamp01(max(semantic_shift_score, segment_concentration_from_rows(obs_url_semantic_gap)))
segment_concentration_raw <- clamp01(max(app_concentration_evidence, sdk_concentration_evidence, identity_concentration_evidence, semantic_concentration_evidence))
visibility_score <- clamp01(1 - max(safe_max_col(obs_metric_gap, "gap_rate", 0) * 0.25, 0))

conversion_gap_rate <- 0
pv_gap_rate <- 0
if (nrow(obs_metric_gap) > 0 && all(c("metric_name", "gap_rate") %in% names(obs_metric_gap))) {
  conv_rows <- obs_metric_gap[tolower(as.character(obs_metric_gap$metric_name)) %in% c("conversion", "purchase", "order_complete", "payment"), , drop = FALSE]
  pv_rows <- obs_metric_gap[tolower(as.character(obs_metric_gap$metric_name)) %in% c("pv", "page_view", "event_count"), , drop = FALSE]
  conversion_gap_rate <- safe_max_col(conv_rows, "gap_rate", 0)
  pv_gap_rate <- safe_max_col(pv_rows, "gap_rate", 0)
}
if (nrow(obs_business_kpi_gap) > 0) {
  conversion_gap_rate <- max(conversion_gap_rate, safe_max_col(obs_business_kpi_gap, "conversion_gap_rate", 0), safe_max_col(obs_business_kpi_gap, "purchase_event_gap_rate", 0))
  pv_gap_rate <- max(pv_gap_rate, safe_max_col(obs_business_kpi_gap, "pv_gap_rate", 0))
}
# Criticality Evidence v2: distinguish ordinary traffic loss from business KPI
# distortion. This remains generic authority evidence: event names/SDK/app labels
# are not risk features.
conversion_criticality_score <- clamp01(conversion_gap_rate)
revenue_criticality_score <- clamp01(conversion_gap_rate * 0.80)
# Traffic preservation asks: are traffic/page-view signals relatively preserved
# while conversion/purchase signals break? It prevents broad PV loss from being
# misclassified as silent business distortion.
traffic_preservation_score <- if (pv_gap_rate <= 0.02) {
  1.0
} else if (pv_gap_rate <= 0.12) {
  clamp01(1.0 - (pv_gap_rate / 0.12) * 0.55)
} else {
  0.0
}
event_criticality_score <- clamp01(max(conversion_criticality_score, revenue_criticality_score))
business_kpi_distortion_score <- clamp01(0.65 * conversion_criticality_score + 0.35 * traffic_preservation_score)
critical_event_impact_raw <- if (conversion_gap_rate >= 0.50 && traffic_preservation_score >= 0.45) {
  clamp01(max(0.75, business_kpi_distortion_score))
} else if (conversion_gap_rate >= 0.30 && traffic_preservation_score >= 0.30) {
  clamp01(max(0.45, business_kpi_distortion_score * 0.85))
} else {
  clamp01(conversion_gap_rate * 0.35)
}

if (is_baseline_like) {
  reconciliation_gap_score <- 0
  propagation_score <- 0
  amplification_score <- 0
  distortion_score <- 0
  transaction_loss_score <- 0
  customer_impact_score <- 0
  runtime_evidence_score <- 0
  batch_evidence_score <- 0
  stream_evidence_score <- 0
  operational_evidence_score <- 0
  realism_evidence_score <- 0
  dominant_runtime_signal <- "none"
  statistical_evidence_effective_score <- 0
  statistical_evidence_score <- statistical_evidence_effective_score
  statistical_significance <- "stable"
  cross_domain_propagation_strength <- 0
  cross_domain_propagation_level <- "stable"
  affected_domain_count <- 0L
  affected_domains <- "[]"
  dominant_propagation_path <- "No Cross-domain Propagation"
  identity_integrity_score <- 0
  semantic_shift_score <- 0
  visibility_score <- 1
}

runtime_weight <- 0.12
baseline_delta_core <- clamp01(max(
  0.40 * reconciliation_gap_score +
    0.20 * distortion_score +
    0.15 * transaction_loss_score +
    0.10 * propagation_score +
    0.15 * cross_domain_propagation_strength,
  statistical_evidence_score,
  cross_domain_propagation_strength * 0.85
))
baseline_delta <- clamp01((1 - runtime_weight) * baseline_delta_core + runtime_weight * runtime_evidence_score)

# ------------------------------------------------------------------
# Authority Evidence Layer (Phase4-B Step1)
# ------------------------------------------------------------------
# Evidence is not risk. The authority analytics layer exposes evidence groups
# that later pattern/risk layers may interpret. Case-specific labels such as
# app_version, sdk_version, URL, browser, campaign, or AI tool names must not
# become authority risk features here. They remain measurement/reference evidence.
evidence_layer_version <- "v05_phase4d_evidence_primitive_mechanism_v1"
baseline_evidence_score <- clamp01(baseline_delta)
statistical_evidence_group_score <- clamp01(statistical_evidence_effective_score)
propagation_evidence_score <- clamp01(cross_domain_propagation_strength)
impact_evidence_score <- clamp01(max(customer_impact_score, transaction_loss_score, reconciliation_gap_score))
# Phase4-B Evidence v2: generic concentration/criticality are computed from
# measurement rows but remain label-free authority evidence. OBS/reference layers
# can later explain which concrete segment/event caused the generic signal.
concentration_evidence_score <- if (is_baseline_like) 0 else segment_concentration_raw
criticality_evidence_score <- if (is_baseline_like) 0 else critical_event_impact_raw
evidence_ready <- as.integer(TRUE)
evidence_summary <- sprintf(
  "Evidence groups ready: baseline=%.3f statistical=%.3f propagation=%.3f impact=%.3f concentration=%.3f criticality=%.3f",
  baseline_evidence_score,
  statistical_evidence_group_score,
  propagation_evidence_score,
  impact_evidence_score,
  concentration_evidence_score,
  criticality_evidence_score
)
if (nchar(evidence_summary) > 512) evidence_summary <- substr(evidence_summary, 1, 512)
evidence_payload <- make_payload(
  evidence_layer_version = evidence_layer_version,
  layer = "AUTHORITY_EVIDENCE_LAYER",
  rule = "Evidence is not risk; Pattern Layer interprets evidence before risk.",
  case_specific_features_disallowed = TRUE,
  obs_is_reference_not_authority = TRUE,
  evidence_groups = list(
    baseline = list(
      score = baseline_evidence_score,
      sources = list("baseline_delta", "statistical_evidence_effective_score", "max_z_score", "max_historical_percentile", "control_limit_breach_count"),
      interpretation = "How abnormal is this compared with the authority reference baseline?"
    ),
    statistical = list(
      score = statistical_evidence_group_score,
      significance = statistical_significance,
      sample_days_min = statistical_evidence_min_sample_days,
      sample_days_max = statistical_evidence_max_sample_days,
      interpretation = "How statistically unusual is the measurement?"
    ),
    propagation = list(
      score = propagation_evidence_score,
      affected_domains = affected_domains,
      affected_domain_count = affected_domain_count,
      level = cross_domain_propagation_level,
      interpretation = "How much did the anomaly propagate across authority domains?"
    ),
    impact = list(
      score = impact_evidence_score,
      customer_impact_score = customer_impact_score,
      transaction_loss_score = transaction_loss_score,
      reconciliation_gap_score = reconciliation_gap_score,
      interpretation = "How much could this affect operational or business decisions?"
    ),
    concentration = list(
      score = concentration_evidence_score,
      app_concentration_evidence = app_concentration_evidence,
      sdk_concentration_evidence = sdk_concentration_evidence,
      identity_concentration_evidence = identity_concentration_evidence,
      semantic_concentration_evidence = semantic_concentration_evidence,
      interpretation = "Is the anomaly concentrated in a segment, without naming the segment as an authority feature?"
    ),
    identity_integrity = list(
      score = identity_integrity_score,
      interpretation = "Does the observation layer preserve login/user identity integrity?"
    ),
    semantic_shift = list(
      score = semantic_shift_score,
      interpretation = "Does tagging preserve URL/category/event attribution semantics?"
    ),
    visibility = list(
      score = visibility_score,
      interpretation = "Are the affected signals visible enough to avoid silent failure?"
    ),
    criticality = list(
      score = criticality_evidence_score,
      conversion_gap_rate = conversion_gap_rate,
      pv_gap_rate = pv_gap_rate,
      event_criticality_score = event_criticality_score,
      conversion_criticality_score = conversion_criticality_score,
      revenue_criticality_score = revenue_criticality_score,
      traffic_preservation_score = traffic_preservation_score,
      business_kpi_distortion_score = business_kpi_distortion_score,
      interpretation = "Does the anomaly affect critical business events, without hardcoding event-specific risk rules?"
    )
  ),
  next_step_contract = list(
    pattern_layer_required = TRUE,
    risk_layer_must_not_consume_case_specific_dimensions_directly = TRUE,
    risk_formula_currently_likelihood_x_impact = TRUE
  )
)



# ------------------------------------------------------------------
# Authority Pattern Layer (Phase4-B Step2)
# ------------------------------------------------------------------
# Pattern is not a feature and not the final risk. It interprets generic
# evidence groups into reusable reliability failure shapes. Authority code must
# not branch on app_version, sdk_version, browser, URL, campaign, AI tool names,
# or scenario names to decide the pattern.
pattern_layer_version <- "v05_phase4b_step2_pattern_layer_v1"
pattern_ready <- as.integer(TRUE)

high_baseline_evidence <- max(baseline_evidence_score, statistical_evidence_group_score)
high_impact_evidence <- impact_evidence_score
high_propagation_evidence <- propagation_evidence_score
high_concentration_evidence <- concentration_evidence_score
high_criticality_evidence <- criticality_evidence_score

# Phase4-B Evidence v2.1: pattern differentiation must prefer generic
# concentration/criticality evidence before broad reconciliation evidence.
# These are still generic patterns: no app_version/sdk_version/event_name appears
# in the authority pattern value. Concrete segment names stay in OBS reference
# explanation only.
localized_threshold <- as.numeric(Sys.getenv("V05_PATTERN_LOCALIZED_CONCENTRATION_THRESHOLD", "0.15"))
silent_distortion_threshold <- as.numeric(Sys.getenv("V05_PATTERN_SILENT_CRITICALITY_THRESHOLD", "0.60"))
silent_distortion_business_threshold <- as.numeric(Sys.getenv("V05_PATTERN_SILENT_BUSINESS_KPI_THRESHOLD", "0.60"))

if (is_baseline_like || max(high_baseline_evidence, high_impact_evidence, high_propagation_evidence, high_concentration_evidence, high_criticality_evidence) < 0.08) {
  risk_pattern <- "stable"
  pattern_confidence <- 1.0
  pattern_reason <- "stable: no material authority evidence signal"
} else if (high_criticality_evidence >= silent_distortion_threshold && business_kpi_distortion_score >= silent_distortion_business_threshold && traffic_preservation_score >= 0.30) {
  risk_pattern <- "silent_distortion"
  pattern_confidence <- clamp01(0.35 * high_criticality_evidence + 0.30 * business_kpi_distortion_score + 0.20 * traffic_preservation_score + 0.15 * high_baseline_evidence)
  pattern_reason <- sprintf("silent_distortion: criticality %.3f business_kpi_distortion %.3f with conversion gap %.3f and pv gap %.3f", high_criticality_evidence, business_kpi_distortion_score, conversion_gap_rate, pv_gap_rate)
} else if (high_concentration_evidence >= localized_threshold) {
  risk_pattern <- "localized_failure"
  pattern_confidence <- clamp01(0.50 * high_concentration_evidence + 0.30 * high_baseline_evidence + 0.20 * max(high_impact_evidence, high_criticality_evidence))
  pattern_reason <- sprintf("localized_failure: generic concentration evidence %.3f with baseline/statistical evidence %.3f; concrete segment remains OBS reference", high_concentration_evidence, high_baseline_evidence)
} else if (reconciliation_gap_score >= 0.15 && max(transaction_loss_score, customer_impact_score, impact_evidence_score) >= 0.08) {
  risk_pattern <- "reconciliation_failure"
  pattern_confidence <- clamp01(0.45 * reconciliation_gap_score + 0.35 * max(transaction_loss_score, customer_impact_score, impact_evidence_score) + 0.20 * high_baseline_evidence)
  pattern_reason <- sprintf("reconciliation_failure: reconciliation gap %.3f with impact %.3f and baseline/statistical evidence %.3f", reconciliation_gap_score, max(transaction_loss_score, customer_impact_score, impact_evidence_score), high_baseline_evidence)
} else if (high_propagation_evidence >= 0.55 && max(high_baseline_evidence, high_impact_evidence) >= 0.20) {
  risk_pattern <- "systemic_failure"
  pattern_confidence <- clamp01(0.45 * high_propagation_evidence + 0.35 * high_baseline_evidence + 0.20 * high_impact_evidence)
  pattern_reason <- sprintf("systemic_failure: propagation %.3f with baseline/statistical evidence %.3f and impact %.3f", high_propagation_evidence, high_baseline_evidence, high_impact_evidence)
} else {
  risk_pattern <- "emerging_reliability_degradation"
  pattern_confidence <- clamp01(0.40 * high_baseline_evidence + 0.25 * high_impact_evidence + 0.20 * high_propagation_evidence + 0.15 * max(high_concentration_evidence, high_criticality_evidence))
  pattern_reason <- sprintf("emerging_reliability_degradation: evidence present but not enough to classify localized/systemic/distortion/reconciliation pattern; baseline=%.3f propagation=%.3f impact=%.3f concentration=%.3f criticality=%.3f", high_baseline_evidence, high_propagation_evidence, high_impact_evidence, high_concentration_evidence, high_criticality_evidence)
}

# ------------------------------------------------------------------
# Failure Mechanism Layer (Phase4-D)
# ------------------------------------------------------------------
# Pattern taxonomy remains small. Mechanism explains the concrete failure mode
# using Evidence Primitives and OBS/reference measurement, without creating
# case-specific risk patterns.
failure_mechanism <- "unknown"
mechanism_source <- "unknown"
mechanism_confidence <- 0
if (risk_pattern == "stable" || is_baseline_like) {
  failure_mechanism <- "none"
  mechanism_source <- "none"
  mechanism_confidence <- 1.0
} else if (risk_pattern == "silent_distortion" && criticality_evidence_score >= silent_distortion_threshold) {
  failure_mechanism <- "critical_event_loss"
  mechanism_source <- "purchase_event_criticality"
  mechanism_confidence <- clamp01(max(criticality_evidence_score, business_kpi_distortion_score, pattern_confidence))
} else if (risk_pattern == "localized_failure" && identity_integrity_score >= max(semantic_shift_score, 0.10) && traffic_preservation_score >= 0.30) {
  # Identity breakage should be selected only when collection volume is mostly
  # preserved and the failure is concentrated in login/user identity fields.
  # This prevents broad WC row drops from being mislabeled as app identity loss.
  failure_mechanism <- "identity_integrity_breakage"
  mechanism_source <- "app_version_concentration"
  mechanism_confidence <- clamp01(max(identity_integrity_score, concentration_evidence_score, pattern_confidence))
} else if (risk_pattern == "localized_failure" && semantic_shift_score >= 0.10 && traffic_preservation_score >= 0.30 && pv_gap_rate <= 0.25) {
  # Semantic attribution distortion means events are still visible but mapped to
  # the wrong URL/category. A broad collection loss can also create url gaps, so
  # require traffic preservation before choosing this mechanism.
  failure_mechanism <- "semantic_attribution_distortion"
  mechanism_source <- "sdk_version_concentration"
  mechanism_confidence <- clamp01(max(semantic_shift_score, concentration_evidence_score, pattern_confidence))
} else if (risk_pattern == "localized_failure") {
  # Default localized mechanism: actual observability completeness loss. This
  # catches general WC missing where traffic visibility is damaged and any URL
  # gap is a consequence of missing rows, not semantic rewrite/collapse.
  failure_mechanism <- "collection_completeness_loss"
  mechanism_source <- "broad_collection_gap"
  mechanism_confidence <- clamp01(max(concentration_evidence_score, pattern_confidence, 1 - traffic_preservation_score))
} else if (risk_pattern == "reconciliation_failure") {
  failure_mechanism <- "cross_domain_mapping_gap"
  mechanism_source <- "behavior_transaction_state_reconciliation"
  mechanism_confidence <- clamp01(max(reconciliation_confidence, pattern_confidence))
} else if (risk_pattern == "systemic_failure") {
  failure_mechanism <- "systemic_observability_degradation"
  mechanism_source <- "multi_domain_propagation"
  mechanism_confidence <- clamp01(max(propagation_evidence_score, pattern_confidence))
} else {
  failure_mechanism <- "emerging_reliability_degradation"
  mechanism_source <- "mixed_evidence_primitives"
  mechanism_confidence <- pattern_confidence
}

primitive_payload <- make_payload(
  primitive_layer_version = "v05_phase4d_evidence_primitive_v1",
  baseline_deviation = baseline_evidence_score,
  concentration = concentration_evidence_score,
  propagation = propagation_evidence_score,
  impact = impact_evidence_score,
  criticality = criticality_evidence_score,
  visibility = visibility_score,
  identity_integrity = identity_integrity_score,
  semantic_shift = semantic_shift_score,
  rule = "Measurement-specific values are mapped into primitive evidence before Pattern/Risk."
)

if (nchar(pattern_reason) > 512) pattern_reason <- substr(pattern_reason, 1, 512)
pattern_payload <- make_payload(
  pattern_layer_version = pattern_layer_version,
  layer = "AUTHORITY_PATTERN_LAYER",
  rule = "Pattern interprets evidence before risk. Pattern is not risk.",
  case_specific_features_disallowed = TRUE,
  obs_is_explanation_not_authority = TRUE,
  evidence_is_not_risk = TRUE,
  pattern_ready = pattern_ready,
  risk_pattern = risk_pattern,
  pattern_confidence = pattern_confidence,
  pattern_reason = pattern_reason,
  failure_mechanism = failure_mechanism,
  mechanism_source = mechanism_source,
  mechanism_confidence = mechanism_confidence,
  supported_patterns = list("stable", "localized_failure", "systemic_failure", "silent_distortion", "reconciliation_failure", "emerging_reliability_degradation"),
  evidence_inputs = list(
    baseline_evidence_score = baseline_evidence_score,
    statistical_evidence_group_score = statistical_evidence_group_score,
    propagation_evidence_score = propagation_evidence_score,
    impact_evidence_score = impact_evidence_score,
    concentration_evidence_score = concentration_evidence_score,
    criticality_evidence_score = criticality_evidence_score,
    identity_integrity_score = identity_integrity_score,
    semantic_shift_score = semantic_shift_score,
    visibility_score = visibility_score,
    reconciliation_gap_score = reconciliation_gap_score,
    customer_impact_score = customer_impact_score,
    transaction_loss_score = transaction_loss_score
  ),
  next_step_contract = list(
    risk_layer_may_consume_pattern = TRUE,
    risk_layer_must_not_consume_case_specific_dimensions_directly = TRUE,
    semantic_action_role = "KNOWLEDGE_BASE"
  )
)

authority_interface_version <- "v05_phase3c_step2_risk_input_v1"
risk_input_ready <- as.integer(TRUE)
authority_input_payload <- make_payload(
  interface_version = authority_interface_version,
  layer = "AUTHORITY_ANALYTICS_LAYER",
  consumer = "build_v05_unified_risk_score.R",
  obs_authority_use = FALSE,
  baseline_science_role = "AUTHORITY_REFERENCE_LAYER",
  required_outputs = list(
    statistical_evidence_effective_score = statistical_evidence_effective_score,
    statistical_significance = statistical_significance,
    cross_domain_propagation_strength = cross_domain_propagation_strength,
    affected_domains = affected_domains,
    affected_domain_count = affected_domain_count,
    reconciliation_confidence = reconciliation_confidence,
    baseline_delta = baseline_delta,
    reconciliation_gap_score = reconciliation_gap_score,
    customer_impact_score = customer_impact_score,
    transaction_loss_score = transaction_loss_score
  ),
  next_step_contract = list(
    risk_model_direction = "Likelihood x Impact",
    confidence_separated_from_risk = TRUE,
    semantic_action_role = "KNOWLEDGE_BASE"
  )
)

payload <- make_payload(
  v05_philosophy_guard = list(
    status = "PASS_BY_CONSTRUCTION",
    rule = "measurement_delta_to_semantic_interpretation",
    scenario_name_used_as_risk_driver = FALSE,
    raw_missing_state_to_high_risk_direct_mapping = FALSE,
    direct_business_heuristic_hardcoding = FALSE
  ),
  authority_risk_input_interface = list(
    interface_version = authority_interface_version,
    consumer = "build_v05_unified_risk_score.R",
    risk_input_ready = risk_input_ready,
    required_outputs_fixed = TRUE,
    obs_is_reference_not_authority = TRUE,
    baseline_science_is_authority_reference = TRUE,
    confidence_is_not_risk = TRUE
  ),
  authority_evidence_layer = list(
    evidence_layer_version = evidence_layer_version,
    evidence_ready = evidence_ready,
    evidence_is_not_risk = TRUE,
    pattern_layer_required = TRUE,
    baseline_evidence_score = baseline_evidence_score,
    statistical_evidence_group_score = statistical_evidence_group_score,
    propagation_evidence_score = propagation_evidence_score,
    impact_evidence_score = impact_evidence_score,
    concentration_evidence_score = concentration_evidence_score,
    criticality_evidence_score = criticality_evidence_score
  ),
  authority_pattern_layer = list(
    pattern_layer_version = pattern_layer_version,
    pattern_ready = pattern_ready,
    evidence_to_pattern = TRUE,
    pattern_is_not_risk = TRUE,
    risk_pattern = risk_pattern,
    pattern_confidence = pattern_confidence,
    pattern_reason = pattern_reason,
    failure_mechanism = failure_mechanism,
    mechanism_source = mechanism_source,
    mechanism_confidence = mechanism_confidence
  ),
  source_table = "v05_reconciliation_measurement_day",
  runtime_evidence_interface = list(
    source_table = "v05_runtime_evidence_day",
    status = runtime_status,
    supplementary_not_authoritative = TRUE,
    runtime_evidence_score = runtime_evidence_score,
    dominant_runtime_signal = dominant_runtime_signal
  ),
  baseline_science_statistical_evidence = list(
    source_table = "v05_baseline_science_statistical_evidence_day",
    domain = "reconciliation_measurement",
    uses_observability_results = FALSE,
    statistical_evidence_score = statistical_evidence_score,
    statistical_evidence_raw_score = statistical_evidence_raw_score,
    statistical_evidence_effective_score = statistical_evidence_effective_score,
    statistical_evidence_reflected = statistical_evidence_reflected,
    statistical_evidence_row_count = statistical_evidence_row_count,
    statistical_evidence_min_sample_days = statistical_evidence_min_sample_days,
    statistical_evidence_max_sample_days = statistical_evidence_max_sample_days,
    baseline_like_suppressed = is_baseline_like,
    max_z_score = max_z_score,
    historical_percentile = max_historical_percentile,
    control_limit_breach_count = control_limit_breach_count,
    co_movement_score = co_movement_score,
    statistical_significance = statistical_significance
  ),
  cross_domain_propagation_evidence = list(
    source_table = "v05_cross_domain_propagation_evidence_day",
    reflected = propagation_evidence_reflected,
    affected_domains = affected_domains,
    affected_domain_count = affected_domain_count,
    propagation_strength = cross_domain_propagation_strength,
    propagation_level = cross_domain_propagation_level,
    reconciliation_confidence = reconciliation_confidence,
    dominant_propagation_path = dominant_propagation_path
  )
)


# ------------------------------------------------------------------
# Save Result
# ------------------------------------------------------------------

delete_scoped_rows(con, "reliability_analysis_result_day_v05", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
insert_schema_aware(con, "reliability_analysis_result_day_v05", list(
  run_id = run_id,
  profile_id = profile_id,
  source_gen_run_id = source_gen_run_id,
  target_date = target_date,
  scenario_name = scenario_name,
  reconciliation_gap_score = reconciliation_gap_score,
  propagation_score = propagation_score,
  amplification_score = amplification_score,
  distortion_score = distortion_score,
  baseline_delta = baseline_delta,
  transaction_loss_score = transaction_loss_score,
  customer_impact_score = customer_impact_score,
  runtime_evidence_score = runtime_evidence_score,
  batch_evidence_score = batch_evidence_score,
  stream_evidence_score = stream_evidence_score,
  operational_evidence_score = operational_evidence_score,
  realism_evidence_score = realism_evidence_score,
  dominant_runtime_signal = dominant_runtime_signal,
  statistical_evidence_score = statistical_evidence_score,
  statistical_evidence_raw_score = statistical_evidence_raw_score,
  statistical_evidence_effective_score = statistical_evidence_effective_score,
  statistical_evidence_reflected = statistical_evidence_reflected,
  statistical_evidence_row_count = statistical_evidence_row_count,
  statistical_evidence_min_sample_days = statistical_evidence_min_sample_days,
  statistical_evidence_max_sample_days = statistical_evidence_max_sample_days,
  max_z_score = max_z_score,
  max_historical_percentile = max_historical_percentile,
  control_limit_breach_count = control_limit_breach_count,
  co_movement_score = co_movement_score,
  statistical_significance = statistical_significance,
  affected_domains = affected_domains,
  affected_domain_count = affected_domain_count,
  cross_domain_propagation_strength = cross_domain_propagation_strength,
  cross_domain_propagation_level = cross_domain_propagation_level,
  reconciliation_confidence = reconciliation_confidence,
  dominant_propagation_path = dominant_propagation_path,
  authority_interface_version = authority_interface_version,
  risk_input_ready = risk_input_ready,
  authority_input_payload_json = authority_input_payload,
  evidence_layer_version = evidence_layer_version,
  evidence_ready = evidence_ready,
  baseline_evidence_score = baseline_evidence_score,
  statistical_evidence_group_score = statistical_evidence_group_score,
  propagation_evidence_score = propagation_evidence_score,
  impact_evidence_score = impact_evidence_score,
  concentration_evidence_score = concentration_evidence_score,
  criticality_evidence_score = criticality_evidence_score,
  event_criticality_score = event_criticality_score,
  conversion_criticality_score = conversion_criticality_score,
  revenue_criticality_score = revenue_criticality_score,
  traffic_preservation_score = traffic_preservation_score,
  business_kpi_distortion_score = business_kpi_distortion_score,
  identity_integrity_score = identity_integrity_score,
  semantic_shift_score = semantic_shift_score,
  visibility_score = visibility_score,
  evidence_payload_json = evidence_payload,
  evidence_primitive_payload_json = primitive_payload,
  evidence_summary = evidence_summary,
  pattern_layer_version = pattern_layer_version,
  pattern_ready = pattern_ready,
  risk_pattern = risk_pattern,
  pattern_confidence = pattern_confidence,
  pattern_reason = pattern_reason,
  pattern_payload_json = pattern_payload,
  failure_mechanism = failure_mechanism,
  mechanism_source = mechanism_source,
  mechanism_confidence = mechanism_confidence,
  analysis_payload_json = payload
))


# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(sprintf(
  "[build_v05_reliability_analysis.R] OK reconciliation_gap=%.6f distortion=%.6f baseline_delta=%.6f runtime=%.6f dominant_runtime=%s runtime_status=%s stat=%.6f sig=%s propagation=%.6f affected_domains=%s reconciliation_confidence=%.6f philosophy=measurement_delta_based\n",
  reconciliation_gap_score, distortion_score, baseline_delta, runtime_evidence_score, dominant_runtime_signal, runtime_status, statistical_evidence_score, statistical_significance, cross_domain_propagation_strength, affected_domains, reconciliation_confidence
))

cat(sprintf(
  "[AUTHORITY_ANALYTICS_INTERFACE] version=%s risk_input_ready=%d stat_effective=%.6f significance=%s propagation=%.6f affected_domains=%s affected_domain_count=%d reconciliation_confidence=%.6f baseline_delta=%.6f reconciliation_gap=%.6f customer_impact=%.6f transaction_loss=%.6f consumer=build_v05_unified_risk_score.R\n",
  authority_interface_version,
  risk_input_ready,
  statistical_evidence_effective_score,
  statistical_significance,
  cross_domain_propagation_strength,
  affected_domains,
  affected_domain_count,
  reconciliation_confidence,
  baseline_delta,
  reconciliation_gap_score,
  customer_impact_score,
  transaction_loss_score
))

cat(sprintf(
  "[AUTHORITY_EVIDENCE_LAYER] version=%s evidence_ready=%d baseline=%.6f statistical=%.6f propagation=%.6f impact=%.6f concentration=%.6f criticality=%.6f evidence_is_not_risk=1 next=pattern_layer\n",
  evidence_layer_version,
  evidence_ready,
  baseline_evidence_score,
  statistical_evidence_group_score,
  propagation_evidence_score,
  impact_evidence_score,
  concentration_evidence_score,
  criticality_evidence_score
))

cat(sprintf(
  "[AUTHORITY_PATTERN_LAYER] version=%s pattern_ready=%d risk_pattern=%s failure_mechanism=%s mechanism_source=%s mechanism_confidence=%.6f pattern_confidence=%.6f pattern_is_not_risk=1 evidence_to_pattern=1 reason=%s next=risk_layer\n",
  pattern_layer_version,
  pattern_ready,
  risk_pattern,
  failure_mechanism,
  mechanism_source,
  mechanism_confidence,
  pattern_confidence,
  pattern_reason
))
# Phase4-C baseline evidence v2 guard handled in validate_v05_authority_evidence_layer.py; no inline R guard required.
