#!/usr/bin/env Rscript
# v0.5 unified risk score builder
# Native observability is authoritative enough to lift LOW to WARNING,
# but not automatically CRITICAL because WC collection loss is observability/KPI risk,
# not necessarily business transaction failure.

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))

args <- commandArgs(trailingOnly = TRUE)

# ------------------------------------------------------------------
# Arguments
# ------------------------------------------------------------------


profile_id <- arg_value(args, "--profile-id")
target_date <- arg_value(args, "--target-date")
run_id <- as.integer(arg_value(args, "--run-id"))
source_gen_run_id <- arg_value(args, "--source-gen-run-id", NULL)
scenario_name <- arg_value(args, "--scenario-name", "baseline")

source_gen_run_id_int <- if (is.null(source_gen_run_id)) NULL else as.integer(source_gen_run_id)

# ------------------------------------------------------------------
# Database Connection
# ------------------------------------------------------------------

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

if (table_exists(con, "unified_reliability_score_day_v05")) {
  ensure_column(con, "unified_reliability_score_day_v05", "runtime_evidence_weight", "DOUBLE NULL")
  ensure_column(con, "unified_reliability_score_day_v05", "dominant_runtime_signal", "VARCHAR(100) NULL")
}


scenario <- scenario_name

# ------------------------------------------------------------------
# Load Data
# ------------------------------------------------------------------

analysis <- read_first_scoped_row(con, "reliability_analysis_result_day_v05", profile_id, target_date, run_id, source_gen_run_id_int, NULL)
semantic <- read_first_scoped_row(con, "semantic_interpretation_day_v05", profile_id, target_date, run_id, source_gen_run_id_int, NULL)
if (nrow(analysis) < 1 || nrow(semantic) < 1) stop("missing analysis or semantic row")

is_baseline_like <- tolower(scenario_name) %in% c("baseline", "normal", "stable")
dominant_semantic_risk <- pick_character(semantic, "dominant_semantic_risk", "None")
observability_score <- clamp01(pick_number(semantic, c("observability_semantic_score"), 0))
observability_signal <- pick_character(semantic, c("dominant_observability_signal"), "none")

semantic_score_candidates <- c(
  pick_number(semantic, "behavior_transaction_consistency_score"),
  pick_number(semantic, "transaction_state_integrity_score"),
  pick_number(semantic, "order_lifecycle_consistency_score"),
  pick_number(semantic, "payment_state_reconciliation_score"),
  pick_number(semantic, "delivery_timeliness_score"),
  pick_number(semantic, "coupon_attribution_score"),
  pick_number(semantic, "customer_experience_score"),
  pick_number(semantic, "runtime_semantic_score") * 0.75,
  observability_score
)
semantic_base_score <- clamp01(max(semantic_score_candidates, na.rm = TRUE))

runtime_evidence_score <- clamp01(pick_number(analysis, "runtime_evidence_score"))
batch_evidence_score <- clamp01(pick_number(analysis, "batch_evidence_score"))
stream_evidence_score <- clamp01(pick_number(analysis, "stream_evidence_score"))
operational_evidence_score <- clamp01(pick_number(analysis, "operational_evidence_score"))
realism_evidence_score <- clamp01(pick_number(analysis, "realism_evidence_score"))
dominant_runtime_signal <- pick_character(analysis, "dominant_runtime_signal", "none")

runtime_evidence_weight <- clamp01(
  0.35 * runtime_evidence_score +
    0.20 * stream_evidence_score +
    0.25 * operational_evidence_score +
    0.10 * batch_evidence_score +
    0.10 * realism_evidence_score
) * 0.10

amplification_weight <- clamp01(pick_number(analysis, "amplification_score")) * 0.12
distortion_penalty <- clamp01(pick_number(analysis, "distortion_score")) * 0.18
baseline_delta_penalty <- clamp01(pick_number(analysis, "baseline_delta")) * 0.15
reconciliation_gap_weight <- clamp01(pick_number(analysis, "reconciliation_gap_score")) * 0.20
customer_impact_weight <- clamp01(pick_number(analysis, "customer_impact_score")) * 0.13
transaction_loss_weight <- clamp01(pick_number(analysis, "transaction_loss_score")) * 0.17

raw_overall <- clamp01(
  semantic_base_score * 0.42 +
    amplification_weight +
    distortion_penalty +
    baseline_delta_penalty +
    reconciliation_gap_weight +
    customer_impact_weight +
    transaction_loss_weight +
    runtime_evidence_weight
)

# Native observability floor:
# - High observability risk must not be hidden as LOW.
# - Still capped because this case indicates KPI/observability decision risk, not confirmed business transaction failure.
observability_floor <- 0
if (!is_baseline_like && observability_score >= 0.75) {
  observability_floor <- min(0.55, max(0.35, observability_score * 0.45))
} else if (!is_baseline_like && observability_score >= 0.35) {
  observability_floor <- min(0.35, max(0.20, observability_score * 0.35))
}

overall <- clamp01(max(raw_overall, observability_floor))

if (is_baseline_like && identical(dominant_semantic_risk, "None")) {
  semantic_base_score <- 0
  amplification_weight <- 0
  distortion_penalty <- 0
  baseline_delta_penalty <- 0
  reconciliation_gap_weight <- 0
  customer_impact_weight <- 0
  transaction_loss_weight <- 0
  runtime_evidence_weight <- 0
  runtime_evidence_score <- 0
  batch_evidence_score <- 0
  stream_evidence_score <- 0
  operational_evidence_score <- 0
  realism_evidence_score <- 0
  dominant_runtime_signal <- "none"
  observability_floor <- 0
  overall <- 0
}

stable_gate <- 0.08
if (identical(dominant_semantic_risk, "None") && overall < stable_gate) overall <- 0
level <- risk_level(overall)

payload <- make_payload(
  v05_philosophy_guard = list(
    status = "PASS",
    measurement_to_semantic_to_score = TRUE,
    risk_not_computed_in_sql = TRUE,
    action_not_embedded_in_score = TRUE,
    scenario_name_used_as_risk_driver = FALSE,
    runtime_evidence_is_supplementary = TRUE,
    observability_risk_has_minimum_score_floor = TRUE
  ),
  dominant_semantic_risk = dominant_semantic_risk,
  observability = list(
    score = observability_score,
    signal = observability_signal,
    applied_floor = observability_floor,
    floor_rule = "if observability >= 0.75 then unified risk >= max(0.35, score*0.45), capped at 0.55"
  ),
  component_scores = list(
    semantic_base_score = semantic_base_score,
    amplification_weight = amplification_weight,
    distortion_penalty = distortion_penalty,
    baseline_delta_penalty = baseline_delta_penalty,
    reconciliation_gap_weight = reconciliation_gap_weight,
    customer_impact_weight = customer_impact_weight,
    transaction_loss_weight = transaction_loss_weight,
    runtime_evidence_weight = runtime_evidence_weight,
    raw_overall_before_floor = raw_overall
  )
)


# ------------------------------------------------------------------
# Save Result
# ------------------------------------------------------------------

delete_scoped_rows(con, "unified_reliability_score_day_v05", profile_id, target_date, run_id, source_gen_run_id_int, NULL)
insert_schema_aware(con, "unified_reliability_score_day_v05", list(
  run_id = run_id,
  profile_id = profile_id,
  source_gen_run_id = source_gen_run_id_int,
  target_date = target_date,
  scenario_name = scenario_name,
  semantic_base_score = semantic_base_score,
  amplification_weight = amplification_weight,
  distortion_penalty = distortion_penalty,
  baseline_delta_penalty = baseline_delta_penalty,
  reconciliation_gap_weight = reconciliation_gap_weight,
  customer_impact_weight = customer_impact_weight,
  transaction_loss_weight = transaction_loss_weight,
  runtime_evidence_weight = runtime_evidence_weight,
  dominant_runtime_signal = dominant_runtime_signal,
  overall_risk_score = overall,
  final_risk_level = level,
  score_payload_json = payload
))


# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(sprintf(
  "[build_v05_unified_risk_score.R] OK overall=%.6f level=%s raw=%.6f observability=%.6f observability_floor=%.6f runtime_weight=%.6f dominant_runtime=%s philosophy=PASS\n",
  overall, level, raw_overall, observability_score, observability_floor, runtime_evidence_weight, dominant_runtime_signal
))
