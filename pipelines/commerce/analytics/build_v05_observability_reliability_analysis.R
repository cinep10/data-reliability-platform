#!/usr/bin/env Rscript
# -----------------------------------------------------------------------------
# ARCHITECTURE LAYER: OBSERVABILITY REFERENCE EVIDENCE
#
# This script is NOT the authority risk engine. It materializes developer/ops
# observability evidence such as WebServer/WC collection gaps and canonical
# observability gaps. Downstream authority layers may reference these signals,
# but final operational/marketing risk is decided only by the authority chain:
#   Baseline Science -> Reliability Analysis -> Unified Risk -> KB Action.
# -----------------------------------------------------------------------------
# Native observability reliability analysis.
# Input: v05_observability_measurement_day. Output: r_v05_observability_analysis_day.

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

# ------------------------------------------------------------------
# Database Connection
# ------------------------------------------------------------------

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

scenario <- scenario_name

# ------------------------------------------------------------------
# Load Data
# ------------------------------------------------------------------

obs <- if (table_exists(con, "v05_observability_measurement_day")) {
  read_first_scoped_row(con, "v05_observability_measurement_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
statistical_evidence <- if (table_exists(con, "v05_baseline_science_statistical_evidence_day")) {
  read_scoped_table(con, "v05_baseline_science_statistical_evidence_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else {
  data.frame()
}
obs_stat_rows <- if (nrow(statistical_evidence) > 0) {
  statistical_evidence[statistical_evidence$evidence_domain %in% c("observability_expected"), , drop = FALSE]
} else {
  data.frame()
}
if (nrow(obs) < 1 && nrow(obs_stat_rows) < 1) {
  cat("[OK] build_v05_observability_reliability_analysis skipped: no row
")
  quit(status = 0)
}

collection_gap <- pick_number(obs, "collection_gap_rate")
canonical_gap <- max(pick_number(obs, "canonical_gap_rate"), pick_number(obs, "web_to_canonical_gap_rate"))
uv_gap <- pick_number(obs, "uv_gap_rate")
checkout_gap <- pick_number(obs, "checkout_missing_rate")
product_gap <- pick_number(obs, "product_missing_rate")

statistical_evidence_score <- if (nrow(obs_stat_rows) > 0 && "statistical_score" %in% names(obs_stat_rows)) max(safe_number(obs_stat_rows$statistical_score), na.rm = TRUE) else 0
statistical_evidence_score <- ifelse(is.finite(statistical_evidence_score), statistical_evidence_score, 0)
max_z_score <- if (nrow(obs_stat_rows) > 0 && "z_score" %in% names(obs_stat_rows)) max(abs(safe_number(obs_stat_rows$z_score)), na.rm = TRUE) else 0
max_z_score <- ifelse(is.finite(max_z_score), max_z_score, 0)
max_historical_percentile <- if (nrow(obs_stat_rows) > 0 && "historical_percentile" %in% names(obs_stat_rows)) max(safe_number(obs_stat_rows$historical_percentile), na.rm = TRUE) else 0
max_historical_percentile <- ifelse(is.finite(max_historical_percentile), max_historical_percentile, 0)
control_limit_breach_count <- if (nrow(obs_stat_rows) > 0 && "control_limit_breach" %in% names(obs_stat_rows)) sum(safe_number(obs_stat_rows$control_limit_breach) > 0, na.rm = TRUE) else 0
co_movement_score <- if (nrow(obs_stat_rows) > 0 && "co_movement_score" %in% names(obs_stat_rows)) max(safe_number(obs_stat_rows$co_movement_score), na.rm = TRUE) else 0
co_movement_score <- ifelse(is.finite(co_movement_score), co_movement_score, 0)
statistical_significance <- if (statistical_evidence_score >= 0.75) "critical" else if (statistical_evidence_score >= 0.55) "warning" else if (statistical_evidence_score >= 0.30) "watch" else if (statistical_evidence_score >= 0.08) "low" else "stable"

score_components <- c(
  collection_completeness = clamp01(collection_gap * 3.0),
  canonical_observability_gap = clamp01(canonical_gap * 3.0),
  uv_observability_gap = clamp01(uv_gap * 2.0),
  journey_stage_distortion = clamp01(max(checkout_gap, product_gap) * 2.0),
  baseline_science_statistical_signal = statistical_evidence_score
)
score_components <- c(score_components, kpi_false_degradation = max(score_components[c("collection_completeness", "canonical_observability_gap", "journey_stage_distortion")]))

overall_score <- clamp01(max(score_components) * 0.70 + mean(score_components) * 0.30)
risk_level_label <- if (overall_score >= 0.65) "high" else if (overall_score >= 0.35) "warning" else "low"
dominant_signal <- names(score_components)[which.max(score_components)]
semantic_risk <- if (overall_score < 0.08) {
  "None"
} else if (dominant_signal %in% c("collection_completeness", "canonical_observability_gap")) {
  "WC Collection Completeness Risk"
} else if (dominant_signal == "kpi_false_degradation") {
  "False KPI Degradation Risk"
} else {
  "Operational Observability Distortion"
}
analysis_status <- if (overall_score >= 0.08) "PASS" else "LOW_SIGNAL"
analysis_reason <- sprintf(
  "measurement_driven; collection=%.6f canonical=%.6f uv=%.6f stage=%.6f kpi=%.6f",
  score_components[["collection_completeness"]],
  score_components[["canonical_observability_gap"]],
  score_components[["uv_observability_gap"]],
  score_components[["journey_stage_distortion"]],
  score_components[["kpi_false_degradation"]]
)

detail_json <- make_payload(
  input = "v05_observability_measurement_day",
  collection_gap_rate = collection_gap,
  canonical_gap_rate = canonical_gap,
  uv_gap_rate = uv_gap,
  score_components = as.list(score_components),
  baseline_science_statistical_evidence = list(
    statistical_evidence_score = statistical_evidence_score,
    max_z_score = max_z_score,
    historical_percentile = max_historical_percentile,
    control_limit_breach_count = control_limit_breach_count,
    co_movement_score = co_movement_score,
    statistical_significance = statistical_significance
  ),
  interpretation = "WebServer reality normal but WC/canonical observability degraded"
)


# ------------------------------------------------------------------
# Save Result
# ------------------------------------------------------------------

delete_scoped_rows(con, "r_v05_observability_analysis_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
insert_schema_aware(con, "r_v05_observability_analysis_day", list(
  profile_id = profile_id,
  target_date = target_date,
  scenario_name = scenario_name,
  run_id = run_id,
  source_gen_run_id = source_gen_run_id,
  collection_completeness_score = score_components[["collection_completeness"]],
  canonical_observability_score = score_components[["canonical_observability_gap"]],
  canonical_observability_gap_score = score_components[["canonical_observability_gap"]],
  uv_observability_score = score_components[["uv_observability_gap"]],
  uv_gap_score = score_components[["uv_observability_gap"]],
  journey_stage_distortion_score = score_components[["journey_stage_distortion"]],
  stage_distortion_score = score_components[["journey_stage_distortion"]],
  kpi_false_degradation_score = score_components[["kpi_false_degradation"]],
  observability_overall_score = overall_score,
  observability_risk_level = risk_level_label,
  dominant_observability_signal = dominant_signal,
  recommended_semantic_risk = semantic_risk,
  analysis_status = analysis_status,
  analysis_reason = analysis_reason,
  statistical_evidence_score = statistical_evidence_score,
  max_z_score = max_z_score,
  max_historical_percentile = max_historical_percentile,
  control_limit_breach_count = control_limit_breach_count,
  co_movement_score = co_movement_score,
  statistical_significance = statistical_significance,
  detail_json = detail_json
))


# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(sprintf(
  "[OK] build_v05_observability_reliability_analysis scenario=%s run_id=%d overall=%.6f level=%s semantic=%s dominant=%s stat=%.6f sig=%s\n",
  scenario_name, run_id, overall_score, risk_level_label, semantic_risk, dominant_signal, statistical_evidence_score, statistical_significance
))
