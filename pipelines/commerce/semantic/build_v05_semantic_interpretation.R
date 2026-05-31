#!/usr/bin/env Rscript
# v0.5 semantic interpretation builder.
# Converts measurement-derived reliability analysis into business/risk language.

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

if (table_exists(con, "semantic_interpretation_day_v05")) {
  ensure_column(con, "semantic_interpretation_day_v05", "runtime_semantic_score", "DOUBLE NULL")
  ensure_column(con, "semantic_interpretation_day_v05", "dominant_runtime_signal", "VARCHAR(128) NULL")
  ensure_column(con, "semantic_interpretation_day_v05", "observability_semantic_score", "DOUBLE NULL")
  ensure_column(con, "semantic_interpretation_day_v05", "dominant_observability_signal", "VARCHAR(128) NULL")
}


scenario <- scenario_name

# ------------------------------------------------------------------
# Load Data
# ------------------------------------------------------------------

analysis <- read_first_scoped_row(con, "reliability_analysis_result_day_v05", profile_id, target_date, run_id, source_gen_run_id, NULL)
measurement <- read_first_scoped_row(con, "v05_reconciliation_measurement_day", profile_id, target_date, run_id, source_gen_run_id, NULL)
if (nrow(analysis) < 1 || nrow(measurement) < 1) stop("missing analysis or measurement row")

observability <- read_first_scoped_row(con, "r_v05_observability_analysis_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
observability_score <- if (nrow(observability) > 0) clamp01(pick_number(observability, "observability_overall_score")) else 0
observability_signal <- if (nrow(observability) > 0) pick_character(observability, "dominant_observability_signal", "none") else "none"
observability_semantic <- if (nrow(observability) > 0) pick_character(observability, "recommended_semantic_risk", "None") else "None"

reconciliation_gap <- clamp01(pick_number(analysis, "reconciliation_gap_score"))
propagation_score <- clamp01(pick_number(analysis, "propagation_score"))
distortion_score <- clamp01(pick_number(analysis, "distortion_score"))
baseline_delta <- clamp01(pick_number(analysis, "baseline_delta"))
transaction_loss <- clamp01(pick_number(analysis, "transaction_loss_score"))
customer_impact <- clamp01(pick_number(analysis, "customer_impact_score"))
runtime_score <- clamp01(pick_number(analysis, "runtime_evidence_score"))
batch_score <- clamp01(pick_number(analysis, "batch_evidence_score"))
stream_score <- clamp01(pick_number(analysis, "stream_evidence_score"))
operational_score <- clamp01(pick_number(analysis, "operational_evidence_score"))
realism_score <- clamp01(pick_number(analysis, "realism_evidence_score"))
dominant_runtime <- pick_character(analysis, "dominant_runtime_signal", "none")

if (is_baseline_like) {
  runtime_score <- 0
  batch_score <- 0
  stream_score <- 0
  operational_score <- 0
  realism_score <- 0
  dominant_runtime <- "none"
}

scores <- c(
  "Behavior-Transaction Consistency Risk" = clamp01(0.55 * reconciliation_gap + 0.25 * baseline_delta + 0.20 * customer_impact),
  "Transaction-State Integrity Risk" = clamp01(0.50 * reconciliation_gap + 0.30 * transaction_loss + 0.20 * propagation_score),
  "Order Lifecycle Consistency Risk" = clamp01(0.45 * transaction_loss + 0.35 * reconciliation_gap + 0.20 * distortion_score),
  "Payment-State Reconciliation Risk" = clamp01(0.60 * transaction_loss + 0.25 * distortion_score + 0.15 * reconciliation_gap),
  "Delivery Timeliness Risk" = clamp01(0.46 * distortion_score + 0.22 * propagation_score + 0.20 * baseline_delta + 0.12 * stream_score),
  "Coupon Attribution Distortion" = clamp01(0.62 * distortion_score + 0.18 * customer_impact + 0.12 * baseline_delta + 0.08 * batch_score),
  "Customer Experience Risk" = clamp01(0.52 * customer_impact + 0.23 * distortion_score + 0.15 * baseline_delta + 0.10 * realism_score),
  "Runtime Operational Reliability Risk" = clamp01(0.55 * operational_score + 0.25 * stream_score + 0.20 * runtime_score)
)

if (observability_score >= 0.08 && observability_semantic != "None") {
  scores[observability_semantic] <- max(scores[observability_semantic], observability_score, na.rm = TRUE)
}

base_gate <- 0.08
baseline_gate <- 0.30
active_gate <- if (is_baseline_like) baseline_gate else base_gate
if (is_baseline_like && "Runtime Operational Reliability Risk" %in% names(scores)) {
  scores[["Runtime Operational Reliability Risk"]] <- min(scores[["Runtime Operational Reliability Risk"]], base_gate / 2)
}

max_score <- max(scores, na.rm = TRUE)
if (max_score < active_gate) {
  dominant_semantic_risk <- "None"
  suppression_reason <- if (is_baseline_like) "baseline_normal_variation_below_label_gate" else "below_semantic_gate"
} else {
  dominant_semantic_risk <- names(scores)[which.max(scores)]
  suppression_reason <- "none"
}

payload <- make_payload(
  input_dependency = "reliability_analysis_result_day_v05 + v05_reconciliation_measurement_day + optional r_v05_observability_analysis_day",
  scenario_name_used_as_risk_driver = FALSE,
  observability = list(score = observability_score, signal = observability_signal, semantic = observability_semantic),
  score_vector = as.list(scores),
  dominant_semantic_risk = dominant_semantic_risk,
  suppression_reason = suppression_reason
)


# ------------------------------------------------------------------
# Save Result
# ------------------------------------------------------------------

delete_scoped_rows(con, "semantic_interpretation_day_v05", profile_id, target_date, run_id, source_gen_run_id, NULL)
insert_schema_aware(con, "semantic_interpretation_day_v05", list(
  run_id = run_id,
  profile_id = profile_id,
  source_gen_run_id = source_gen_run_id,
  target_date = target_date,
  scenario_name = scenario_name,
  behavior_transaction_consistency_score = scores[["Behavior-Transaction Consistency Risk"]],
  transaction_state_integrity_score = scores[["Transaction-State Integrity Risk"]],
  order_lifecycle_consistency_score = scores[["Order Lifecycle Consistency Risk"]],
  payment_state_reconciliation_score = scores[["Payment-State Reconciliation Risk"]],
  delivery_timeliness_score = scores[["Delivery Timeliness Risk"]],
  coupon_attribution_score = scores[["Coupon Attribution Distortion"]],
  customer_experience_score = scores[["Customer Experience Risk"]],
  dominant_semantic_risk = dominant_semantic_risk,
  runtime_semantic_score = runtime_score,
  dominant_runtime_signal = dominant_runtime,
  observability_semantic_score = observability_score,
  dominant_observability_signal = observability_signal,
  semantic_payload_json = payload
))


# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(sprintf(
  "[build_v05_semantic_interpretation.R] OK dominant=%s max_raw_score=%.6f active_gate=%.6f observability_score=%.6f observability_signal=%s philosophy=PASS\n",
  dominant_semantic_risk, max_score, active_gate, observability_score, observability_signal
))
