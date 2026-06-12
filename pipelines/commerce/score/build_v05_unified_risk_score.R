#!/usr/bin/env Rscript
# ------------------------------------------------------------------
# AUTHORITY RISK LAYER
# Phase4-B Step3: Evidence -> Pattern -> Risk
#
# Contract:
# - Consumes Authority Analytics output from build_v05_reliability_analysis.R.
# - Risk is computed from generic risk_pattern + evidence payload.
# - Evidence is not risk; Pattern is not risk; Pattern is the required bridge.
# - OBS is reference explanation only and is not an authority risk input.
# - Semantic/Action are Knowledge Base layers and must not drive numeric risk.
# ------------------------------------------------------------------

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))

args <- commandArgs(trailingOnly = TRUE)
profile_id <- arg_value(args, "--profile-id")
target_date <- arg_value(args, "--target-date")
run_id <- as.integer(arg_value(args, "--run-id"))
source_gen_run_id <- arg_value(args, "--source-gen-run-id", NULL)
scenario_name <- arg_value(args, "--scenario-name", "baseline")
source_gen_run_id_int <- if (is.null(source_gen_run_id)) NULL else as.integer(source_gen_run_id)

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

# ------------------------------------------------------------------
# Schema contract for Pattern-driven Authority Risk Layer
# ------------------------------------------------------------------
if (table_exists(con, "unified_reliability_score_day_v05")) {
  ensure_column(con, "unified_reliability_score_day_v05", "runtime_evidence_weight", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "dominant_runtime_signal", "VARCHAR(100) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "risk_model_version", "VARCHAR(80) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "authority_risk_input_version", "VARCHAR(80) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "risk_model_formula", "VARCHAR(160) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "risk_pattern", "VARCHAR(80) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "pattern_confidence", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "pattern_reason", "VARCHAR(1024) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "pattern_payload_json", "LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "pattern_is_risk_driver", "TINYINT NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "evidence_direct_to_risk", "TINYINT NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "likelihood_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "impact_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "unified_risk_model_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "statistical_likelihood_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "baseline_deviation_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "propagation_likelihood_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "concentration_likelihood_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "criticality_impact_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "multi_metric_co_movement_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "business_impact_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "kpi_distortion_impact_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "transaction_impact_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "affected_domain_impact_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "runtime_decision_impact_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "root_cause_confidence", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "reconciliation_confidence", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "confidence_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "confidence_level", "VARCHAR(64) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "confidence_separate_from_risk", "TINYINT NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "risk_classification", "VARCHAR(128) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "failure_mechanism", "VARCHAR(128) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "mechanism_source", "VARCHAR(128) NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "mechanism_confidence", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "identity_integrity_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "semantic_shift_score", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "visibility_score", "DOUBLE NULL")
}

analysis <- read_first_scoped_row(con, "reliability_analysis_result_day_v05", profile_id, target_date, run_id, source_gen_run_id_int, NULL)
if (nrow(analysis) < 1) stop("missing reliability analysis row")

is_baseline_like <- tolower(scenario_name) %in% c("baseline", "normal", "stable")

risk_model_version <- "v05_phase4b_step3_pattern_driven_risk_v1"
risk_model_formula <- "risk_score=f(pattern,evidence): likelihood(pattern)*impact(pattern); confidence_separate"
authority_risk_input_version <- pick_character(analysis, c("authority_interface_version", "evidence_layer_version"), "unknown")

# ------------------------------------------------------------------
# Load explicit Evidence Layer + Pattern Layer from Authority Analytics
# ------------------------------------------------------------------
baseline_evidence_score <- clamp01(pick_number(analysis, c("baseline_evidence_score", "baseline_delta")))
statistical_evidence_group_score <- clamp01(pick_number(analysis, c("statistical_evidence_group_score", "statistical_evidence_effective_score")))
propagation_evidence_score <- clamp01(pick_number(analysis, c("propagation_evidence_score", "cross_domain_propagation_strength")))
impact_evidence_score <- clamp01(pick_number(analysis, c("impact_evidence_score", "reconciliation_gap_score", "customer_impact_score")))
concentration_evidence_score <- clamp01(pick_number(analysis, "concentration_evidence_score"))
criticality_evidence_score <- clamp01(pick_number(analysis, "criticality_evidence_score"))
co_movement_score <- clamp01(pick_number(analysis, "co_movement_score"))
identity_integrity_score <- clamp01(pick_number(analysis, "identity_integrity_score"))
semantic_shift_score <- clamp01(pick_number(analysis, "semantic_shift_score"))
visibility_score <- clamp01(pick_number(analysis, "visibility_score", 1))
failure_mechanism <- pick_character(analysis, "failure_mechanism", if (is_baseline_like) "none" else "unknown")
mechanism_source <- pick_character(analysis, "mechanism_source", if (is_baseline_like) "none" else "unknown")
mechanism_confidence <- clamp01(pick_number(analysis, "mechanism_confidence", 0))

risk_pattern <- pick_character(analysis, "risk_pattern", if (is_baseline_like) "stable" else "emerging_reliability_degradation")
pattern_confidence <- clamp01(pick_number(analysis, "pattern_confidence", 0))
pattern_reason <- pick_character(analysis, "pattern_reason", "pattern layer not populated; fallback pattern used")
pattern_payload <- pick_character(analysis, "pattern_payload_json", "{}")

allowed_patterns <- c(
  "stable",
  "localized_failure",
  "systemic_failure",
  "silent_distortion",
  "reconciliation_failure",
  "emerging_reliability_degradation",
  "interpretation_failure"
)
if (!(risk_pattern %in% allowed_patterns)) {
  risk_pattern <- "emerging_reliability_degradation"
  pattern_reason <- paste("unknown pattern normalized to emerging_reliability_degradation; original=", risk_pattern)
}

# Compatibility: if older analysis did not compute pattern_confidence, derive a weak confidence
# from generic evidence. This is not risk; it only indicates pattern reliability.
if (pattern_confidence <= 0 && !is_baseline_like) {
  pattern_confidence <- clamp01(max(baseline_evidence_score, statistical_evidence_group_score, propagation_evidence_score, impact_evidence_score))
}

# ------------------------------------------------------------------
# Pattern-conditioned Likelihood Model
# Evidence does not go directly to risk; pattern chooses how evidence is interpreted.
# ------------------------------------------------------------------
statistical_likelihood_score <- statistical_evidence_group_score
baseline_deviation_score <- baseline_evidence_score
propagation_likelihood_score <- propagation_evidence_score
concentration_likelihood_score <- concentration_evidence_score
multi_metric_co_movement_score <- co_movement_score

pattern_likelihood <- function(pattern) {
  if (pattern == "stable") {
    return(0)
  } else if (pattern == "localized_failure") {
    return(clamp01(0.25 * baseline_deviation_score + 0.25 * concentration_likelihood_score + 0.15 * statistical_likelihood_score + 0.15 * max(identity_integrity_score, semantic_shift_score) + 0.20 * max(pattern_confidence, mechanism_confidence)))
  } else if (pattern == "systemic_failure") {
    return(clamp01(0.25 * baseline_deviation_score + 0.30 * propagation_likelihood_score + 0.25 * statistical_likelihood_score + 0.20 * pattern_confidence))
  } else if (pattern == "silent_distortion") {
    return(clamp01(0.35 * criticality_evidence_score + 0.25 * impact_evidence_score + 0.15 * concentration_likelihood_score + 0.25 * max(pattern_confidence, mechanism_confidence)))
  } else if (pattern == "reconciliation_failure") {
    return(clamp01(0.25 * baseline_deviation_score + 0.25 * statistical_likelihood_score + 0.30 * propagation_likelihood_score + 0.20 * pattern_confidence))
  } else if (pattern == "interpretation_failure") {
    return(clamp01(0.35 * statistical_likelihood_score + 0.35 * criticality_evidence_score + 0.30 * pattern_confidence))
  }
  clamp01(0.30 * baseline_deviation_score + 0.25 * statistical_likelihood_score + 0.20 * propagation_likelihood_score + 0.15 * concentration_likelihood_score + 0.10 * pattern_confidence)
}

likelihood_score <- pattern_likelihood(risk_pattern)

# ------------------------------------------------------------------
# Pattern-conditioned Impact Model
# ------------------------------------------------------------------
business_impact_score <- clamp01(pick_number(analysis, "customer_impact_score"))
transaction_impact_score <- clamp01(pick_number(analysis, "transaction_loss_score"))
criticality_impact_score <- criticality_evidence_score

# OBS/semantic are not read here. KPI distortion impact must be produced by Authority Analytics/Evidence.
kpi_distortion_impact_score <- clamp01(pick_number(analysis, c("kpi_distortion_impact_score", "impact_evidence_score", "customer_impact_score"), impact_evidence_score))

affected_domain_count <- as.integer(pick_number(analysis, "affected_domain_count"))
affected_domain_impact_score <- clamp01(affected_domain_count / 5.0)

runtime_evidence_score <- clamp01(pick_number(analysis, "runtime_evidence_score"))
batch_evidence_score <- clamp01(pick_number(analysis, "batch_evidence_score"))
stream_evidence_score <- clamp01(pick_number(analysis, "stream_evidence_score"))
operational_evidence_score <- clamp01(pick_number(analysis, "operational_evidence_score"))
realism_evidence_score <- clamp01(pick_number(analysis, "realism_evidence_score"))
dominant_runtime_signal <- pick_character(analysis, "dominant_runtime_signal", "none")
runtime_decision_impact_score <- clamp01(0.35 * runtime_evidence_score + 0.20 * stream_evidence_score + 0.25 * operational_evidence_score + 0.10 * batch_evidence_score + 0.10 * realism_evidence_score)

pattern_impact <- function(pattern) {
  if (pattern == "stable") {
    return(0)
  } else if (pattern == "localized_failure") {
    return(clamp01(0.30 * business_impact_score + 0.20 * kpi_distortion_impact_score + 0.20 * criticality_impact_score + 0.15 * max(identity_integrity_score, semantic_shift_score) + 0.15 * affected_domain_impact_score))
  } else if (pattern == "systemic_failure") {
    return(clamp01(0.30 * business_impact_score + 0.25 * transaction_impact_score + 0.20 * affected_domain_impact_score + 0.15 * runtime_decision_impact_score + 0.10 * criticality_impact_score))
  } else if (pattern == "silent_distortion") {
    return(clamp01(0.30 * criticality_impact_score + 0.30 * kpi_distortion_impact_score + 0.20 * business_impact_score + 0.20 * transaction_impact_score))
  } else if (pattern == "reconciliation_failure") {
    return(clamp01(0.30 * business_impact_score + 0.30 * transaction_impact_score + 0.25 * affected_domain_impact_score + 0.15 * kpi_distortion_impact_score))
  } else if (pattern == "interpretation_failure") {
    return(clamp01(0.35 * criticality_impact_score + 0.35 * business_impact_score + 0.30 * kpi_distortion_impact_score))
  }
  clamp01(0.35 * business_impact_score + 0.25 * transaction_impact_score + 0.20 * kpi_distortion_impact_score + 0.10 * affected_domain_impact_score + 0.10 * runtime_decision_impact_score)
}

impact_score <- pattern_impact(risk_pattern)

# ------------------------------------------------------------------
# Confidence Model - explicitly separate from Risk
# ------------------------------------------------------------------
reconciliation_confidence <- clamp01(pick_number(analysis, "reconciliation_confidence", 0))
root_cause_confidence <- clamp01(max(pattern_confidence, mechanism_confidence, reconciliation_confidence, na.rm = TRUE))
confidence_score <- clamp01(max(reconciliation_confidence, pattern_confidence, root_cause_confidence, na.rm = TRUE))
confidence_level <- if (confidence_score >= 0.80) {
  "high"
} else if (confidence_score >= 0.50) {
  "medium"
} else if (confidence_score > 0) {
  "low"
} else {
  "unknown"
}

# ------------------------------------------------------------------
# Unified Risk = Pattern-conditioned Likelihood x Impact
# ------------------------------------------------------------------
unified_risk_model_score <- clamp01(likelihood_score * impact_score)
overall <- unified_risk_model_score

if (is_baseline_like || risk_pattern == "stable") {
  likelihood_score <- 0
  impact_score <- 0
  unified_risk_model_score <- 0
  overall <- 0
  statistical_likelihood_score <- 0
  baseline_deviation_score <- 0
  propagation_likelihood_score <- 0
  concentration_likelihood_score <- 0
  criticality_impact_score <- 0
  multi_metric_co_movement_score <- 0
  business_impact_score <- 0
  transaction_impact_score <- 0
  kpi_distortion_impact_score <- 0
  affected_domain_impact_score <- 0
  runtime_decision_impact_score <- 0
  runtime_evidence_score <- 0
  batch_evidence_score <- 0
  stream_evidence_score <- 0
  operational_evidence_score <- 0
  realism_evidence_score <- 0
  dominant_runtime_signal <- "none"
  failure_mechanism <- "none"
  mechanism_source <- "none"
  mechanism_confidence <- 1.0
  identity_integrity_score <- 0
  semantic_shift_score <- 0
  visibility_score <- 1
}

level <- risk_level(overall)
risk_classification <- if (overall > 0) "Reliability Risk" else "None"

payload <- make_payload(
  architecture_layer = "AUTHORITY_RISK_LAYER",
  model_version = risk_model_version,
  model_formula = risk_model_formula,
  authority_input = list(
    producer = "build_v05_reliability_analysis.R",
    interface_version = authority_risk_input_version,
    required_bridge = "evidence_to_pattern",
    obs_is_authority_risk_input = FALSE,
    semantic_is_risk_driver = FALSE,
    evidence_direct_to_risk = FALSE
  ),
  pattern_model = list(
    risk_pattern = risk_pattern,
    pattern_confidence = pattern_confidence,
    pattern_reason = pattern_reason,
    pattern_payload_json = pattern_payload,
    pattern_is_not_risk = TRUE,
    failure_mechanism = failure_mechanism,
    mechanism_source = mechanism_source,
    mechanism_confidence = mechanism_confidence
  ),
  likelihood_model = list(
    score = likelihood_score,
    conditioned_by_pattern = risk_pattern,
    components = list(
      statistical_likelihood_score = statistical_likelihood_score,
      baseline_deviation_score = baseline_deviation_score,
      propagation_likelihood_score = propagation_likelihood_score,
      concentration_likelihood_score = concentration_likelihood_score,
      multi_metric_co_movement_score = multi_metric_co_movement_score,
      identity_integrity_score = identity_integrity_score,
      semantic_shift_score = semantic_shift_score,
      pattern_confidence = pattern_confidence,
      mechanism_confidence = mechanism_confidence
    )
  ),
  impact_model = list(
    score = impact_score,
    conditioned_by_pattern = risk_pattern,
    components = list(
      business_impact_score = business_impact_score,
      transaction_impact_score = transaction_impact_score,
      kpi_distortion_impact_score = kpi_distortion_impact_score,
      criticality_impact_score = criticality_impact_score,
      affected_domain_impact_score = affected_domain_impact_score,
      runtime_decision_impact_score = runtime_decision_impact_score,
      visibility_score = visibility_score
    )
  ),
  confidence_model = list(
    confidence_separate_from_risk = TRUE,
    confidence_score = confidence_score,
    confidence_level = confidence_level,
    root_cause_confidence = root_cause_confidence,
    reconciliation_confidence = reconciliation_confidence
  ),
  final = list(
    risk_score = overall,
    risk_level = level,
    risk_classification = risk_classification
  )
)

delete_scoped_rows(con, "unified_reliability_score_day_v05", profile_id, target_date, run_id, source_gen_run_id_int, NULL)
insert_schema_aware(con, "unified_reliability_score_day_v05", list(
  run_id = run_id,
  profile_id = profile_id,
  source_gen_run_id = source_gen_run_id_int,
  target_date = target_date,
  scenario_name = scenario_name,
  semantic_base_score = 0,
  amplification_weight = 0,
  distortion_penalty = statistical_likelihood_score,
  baseline_delta_penalty = baseline_deviation_score,
  reconciliation_gap_weight = clamp01(pick_number(analysis, "reconciliation_gap_score")),
  customer_impact_weight = business_impact_score,
  transaction_loss_weight = transaction_impact_score,
  runtime_evidence_weight = runtime_decision_impact_score,
  dominant_runtime_signal = dominant_runtime_signal,
  overall_risk_score = overall,
  final_risk_level = level,
  risk_model_version = risk_model_version,
  authority_risk_input_version = authority_risk_input_version,
  risk_model_formula = risk_model_formula,
  risk_pattern = risk_pattern,
  pattern_confidence = pattern_confidence,
  pattern_reason = pattern_reason,
  pattern_payload_json = pattern_payload,
  failure_mechanism = failure_mechanism,
  mechanism_source = mechanism_source,
  mechanism_confidence = mechanism_confidence,
  identity_integrity_score = identity_integrity_score,
  semantic_shift_score = semantic_shift_score,
  visibility_score = visibility_score,
  pattern_is_risk_driver = 1,
  evidence_direct_to_risk = 0,
  likelihood_score = likelihood_score,
  impact_score = impact_score,
  unified_risk_model_score = unified_risk_model_score,
  statistical_likelihood_score = statistical_likelihood_score,
  baseline_deviation_score = baseline_deviation_score,
  propagation_likelihood_score = propagation_likelihood_score,
  concentration_likelihood_score = concentration_likelihood_score,
  criticality_impact_score = criticality_impact_score,
  multi_metric_co_movement_score = multi_metric_co_movement_score,
  business_impact_score = business_impact_score,
  kpi_distortion_impact_score = kpi_distortion_impact_score,
  transaction_impact_score = transaction_impact_score,
  affected_domain_impact_score = affected_domain_impact_score,
  runtime_decision_impact_score = runtime_decision_impact_score,
  root_cause_confidence = root_cause_confidence,
  reconciliation_confidence = reconciliation_confidence,
  confidence_score = confidence_score,
  confidence_level = confidence_level,
  confidence_separate_from_risk = 1,
  risk_classification = risk_classification,
  score_payload_json = payload
))

cat(sprintf(
  "[AUTHORITY_RISK_LAYER] version=%s pattern=%s pattern_confidence=%.6f likelihood=%.6f impact=%.6f risk=%.6f level=%s evidence_direct_to_risk=0 confidence_separate=1\n",
  risk_model_version, risk_pattern, pattern_confidence, likelihood_score, impact_score, overall, level
))
