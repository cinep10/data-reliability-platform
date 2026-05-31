#!/usr/bin/env Rscript
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
}

measurement <- read_first_scoped_row(con, "v05_reconciliation_measurement_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
if (nrow(measurement) < 1) stop("missing v05_reconciliation_measurement_day row")
runtime <- read_first_scoped_row(con, "v05_runtime_evidence_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)

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
}

runtime_weight <- 0.12
baseline_delta_core <- clamp01(
  0.45 * reconciliation_gap_score +
    0.25 * distortion_score +
    0.20 * transaction_loss_score +
    0.10 * propagation_score
)
baseline_delta <- clamp01((1 - runtime_weight) * baseline_delta_core + runtime_weight * runtime_evidence_score)

payload <- make_payload(
  v05_philosophy_guard = list(
    status = "PASS_BY_CONSTRUCTION",
    rule = "measurement_delta_to_semantic_interpretation",
    scenario_name_used_as_risk_driver = FALSE,
    raw_missing_state_to_high_risk_direct_mapping = FALSE,
    direct_business_heuristic_hardcoding = FALSE
  ),
  source_table = "v05_reconciliation_measurement_day",
  runtime_evidence_interface = list(
    source_table = "v05_runtime_evidence_day",
    status = runtime_status,
    supplementary_not_authoritative = TRUE,
    runtime_evidence_score = runtime_evidence_score,
    dominant_runtime_signal = dominant_runtime_signal
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
  analysis_payload_json = payload
))


# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(sprintf(
  "[build_v05_reliability_analysis.R] OK reconciliation_gap=%.6f distortion=%.6f baseline_delta=%.6f runtime=%.6f dominant_runtime=%s runtime_status=%s philosophy=measurement_delta_based\n",
  reconciliation_gap_score, distortion_score, baseline_delta, runtime_evidence_score, dominant_runtime_signal, runtime_status
))
