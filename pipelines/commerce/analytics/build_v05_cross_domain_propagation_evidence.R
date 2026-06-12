#!/usr/bin/env Rscript
# CASE-OBS-001 Phase3-B: Cross-domain Propagation Evidence
# Purpose:
#   Convert v0.5 behavior/transaction/state reconciliation measurement into
#   explainable propagation evidence: affected_domains, propagation_strength,
#   and reconciliation_confidence.

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))

args <- commandArgs(trailingOnly = TRUE)
profile_id <- arg_value(args, "--profile-id")
target_date <- arg_value(args, "--target-date")
run_id <- as.integer(arg_value(args, "--run-id"))
source_gen_run_id <- as.integer(arg_value(args, "--source-gen-run-id", "0"))
scenario_name <- arg_value(args, "--scenario-name", "baseline")
baseline_window <- arg_value(args, "--baseline-window", "30d")
is_baseline_like <- tolower(scenario_name) %in% c("baseline", "normal", "stable")

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

if (!table_exists(con, "v05_cross_domain_propagation_evidence_day")) {
  stop("missing v05_cross_domain_propagation_evidence_day; apply sql/081_v05_cross_domain_propagation_evidence_mariadb.sql")
}

# Ensure forward-compatible columns for reliability_analysis_result_day_v05.
if (table_exists(con, "reliability_analysis_result_day_v05")) {
  ensure_column(con, "reliability_analysis_result_day_v05", "affected_domains", "LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(affected_domains))")
  ensure_column(con, "reliability_analysis_result_day_v05", "affected_domain_count", "INT NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "cross_domain_propagation_strength", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "cross_domain_propagation_level", "VARCHAR(64) NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "reconciliation_confidence", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "dominant_propagation_path", "VARCHAR(512) NULL")
}

measurement <- read_first_scoped_row(con, "v05_reconciliation_measurement_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
if (nrow(measurement) < 1) stop("missing v05_reconciliation_measurement_day row")

runtime <- read_first_scoped_row(con, "v05_runtime_evidence_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)

statistical_evidence <- if (table_exists(con, "v05_baseline_science_statistical_evidence_day")) {
  read_scoped_table(con, "v05_baseline_science_statistical_evidence_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else data.frame()
recon_stat <- if (nrow(statistical_evidence) > 0 && "evidence_domain" %in% names(statistical_evidence)) {
  statistical_evidence[statistical_evidence$evidence_domain == "reconciliation_measurement", , drop = FALSE]
} else data.frame()
batch_stat <- if (nrow(statistical_evidence) > 0 && "evidence_domain" %in% names(statistical_evidence)) {
  statistical_evidence[statistical_evidence$evidence_domain == "batch_metric_delta", , drop = FALSE]
} else data.frame()

batch_metric <- if (table_exists(con, "v05_batch_metric_delta_day")) {
  read_scoped_table(con, "v05_batch_metric_delta_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else data.frame()
obs_metric <- if (table_exists(con, "v05_obs_metric_gap_day")) {
  read_scoped_table(con, "v05_obs_metric_gap_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
} else data.frame()

num_col <- function(df, candidates, default = 0) {
  if (nrow(df) < 1) return(default)
  for (c in candidates) if (c %in% names(df)) return(max(safe_number(df[[c]]), na.rm = TRUE))
  default
}
num_col_mean <- function(df, candidates, default = 0) {
  if (nrow(df) < 1) return(default)
  for (c in candidates) if (c %in% names(df)) return(mean(safe_number(df[[c]]), na.rm = TRUE))
  default
}
metric_score <- function(df, metric_patterns) {
  if (nrow(df) < 1) return(0)
  metric_col <- intersect(c("metric_name", "metric"), names(df))[1]
  if (is.na(metric_col)) return(num_col(df, c("risk_score", "score", "statistical_score"), 0))
  keep <- rep(FALSE, nrow(df))
  for (p in metric_patterns) keep <- keep | grepl(p, as.character(df[[metric_col]]), ignore.case = TRUE)
  sub <- df[keep, , drop = FALSE]
  if (nrow(sub) < 1) return(0)
  num_col(sub, c("risk_score", "score", "statistical_score", "gap_rate", "missing_rate"), 0)
}

behavior_event_count <- pick_number(measurement, "behavior_event_count")
transaction_event_count <- pick_number(measurement, "transaction_event_count")
state_event_count <- pick_number(measurement, "state_event_count")
behavior_transaction_total_count <- pick_number(measurement, "behavior_transaction_total_count")
behavior_transaction_matched_count <- pick_number(measurement, "behavior_transaction_matched_count")
transaction_state_total_count <- pick_number(measurement, "transaction_state_total_count")
transaction_state_matched_count <- pick_number(measurement, "transaction_state_matched_count")
behavior_only_count <- pick_number(measurement, "behavior_only_count")
transaction_only_count <- pick_number(measurement, "transaction_only_count")
orphan_state_count <- pick_number(measurement, "orphan_state_count")
transaction_without_state_count <- pick_number(measurement, "transaction_without_state_count")
behavior_transaction_match_rate <- pick_number(measurement, "behavior_transaction_match_rate")
transaction_state_match_rate <- pick_number(measurement, "transaction_state_match_rate")
conversion_gap <- pick_number(measurement, "conversion_gap")
payment_order_gap <- pick_number(measurement, "payment_order_gap")
refund_transition_gap <- pick_number(measurement, "refund_transition_gap")
coupon_reconciliation_gap <- pick_number(measurement, "coupon_reconciliation_gap")
propagation_distortion_count <- pick_number(measurement, "propagation_distortion_count")

bt_gap <- clamp01(1 - behavior_transaction_match_rate)
ts_gap <- clamp01(1 - transaction_state_match_rate)
behavior_total <- max(behavior_transaction_total_count, behavior_only_count + behavior_transaction_matched_count + transaction_only_count, 1)
state_total <- max(transaction_state_total_count, orphan_state_count + transaction_without_state_count + transaction_state_matched_count, 1)
behavior_only_rate <- clamp01(behavior_only_count / behavior_total)
transaction_only_rate <- clamp01(transaction_only_count / behavior_total)
orphan_state_rate <- clamp01(orphan_state_count / state_total)
transaction_without_state_rate <- clamp01(transaction_without_state_count / state_total)

batch_behavior_score <- metric_score(batch_metric, c("event_count", "pv", "uv", "visit"))
batch_conversion_score <- metric_score(batch_metric, c("conversion", "order", "purchase"))
obs_gap_score <- metric_score(obs_metric, c("event_count", "pv", "uv", "visit", "conversion"))
recon_stat_score <- num_col(recon_stat, c("statistical_score"), 0)
recon_z <- num_col(recon_stat, c("z_score"), 0)
recon_percentile <- num_col(recon_stat, c("historical_percentile"), 0)
recon_co_movement <- num_col(recon_stat, c("co_movement_score"), 0)
recon_sample_days <- num_col(recon_stat, c("sample_days"), 0)
recon_quality <- num_col_mean(recon_stat, c("baseline_quality_score"), 0)
if (!is.finite(recon_quality) || recon_quality <= 0) recon_quality <- ifelse(recon_sample_days >= 3, 0.8, 0.35)

# Domain impact scores. These are not final risk scores; they explain where the
# anomaly propagated across Behavior -> Transaction -> State -> KPI/Attribution.
behavior_impact_score <- clamp01(max(batch_behavior_score, obs_gap_score, bt_gap * 0.35, behavior_only_rate * 1.20))
transaction_impact_score <- clamp01(max(bt_gap * 0.65, transaction_only_rate * 2.00, payment_order_gap, coupon_reconciliation_gap))
state_impact_score <- clamp01(max(ts_gap * 0.85, orphan_state_rate * 1.25, transaction_without_state_rate * 1.50, refund_transition_gap))
conversion_impact_score <- clamp01(max(abs(conversion_gap), batch_conversion_score, obs_gap_score * 0.75))
attribution_impact_score <- clamp01(max(behavior_only_rate * 1.50, transaction_only_rate * 2.00, coupon_reconciliation_gap, propagation_distortion_count / max(behavior_total, 1)))

# Use runtime evidence as supplemental signal only.
runtime_score <- pick_number(runtime, "runtime_evidence_score")

impact_scores <- c(
  behavior = behavior_impact_score,
  transaction = transaction_impact_score,
  state = state_impact_score,
  conversion = conversion_impact_score,
  attribution = attribution_impact_score
)
affected_threshold <- if (is_baseline_like) 0.08 else 0.10
affected_domains_vec <- names(impact_scores)[impact_scores >= affected_threshold]
if (length(affected_domains_vec) < 1 && !is_baseline_like && max(impact_scores) > 0) {
  affected_domains_vec <- names(impact_scores)[which.max(impact_scores)]
}
affected_domain_count <- length(affected_domains_vec)
affected_domain_ratio <- affected_domain_count / length(impact_scores)

propagation_strength <- clamp01(
  0.30 * behavior_impact_score +
    0.22 * max(transaction_impact_score, attribution_impact_score) +
    0.18 * conversion_impact_score +
    0.15 * state_impact_score +
    0.10 * affected_domain_ratio +
    0.05 * max(recon_stat_score, runtime_score)
)
if (is_baseline_like) {
  propagation_strength <- 0
  affected_domains_vec <- character()
  affected_domain_count <- 0
}
propagation_level <- risk_level(propagation_strength)
if (propagation_strength >= 0.70) propagation_level <- "high"
if (propagation_strength >= 0.85) propagation_level <- "critical"

sample_total <- max(behavior_event_count + transaction_event_count + state_event_count, behavior_transaction_total_count + transaction_state_total_count, 0)
sample_size_score <- clamp01(log10(sample_total + 1) / 4.0)
mapping_coverage <- clamp01((behavior_transaction_matched_count + transaction_state_matched_count) / max(behavior_transaction_total_count + transaction_state_total_count, 1))
# Reconciliation confidence should express confidence in the measurement, not health.
# A low match rate can be a true anomaly; high sample size and complete measurement increase confidence.
stat_sample_score <- clamp01(recon_sample_days / 7)
evidence_presence_score <- ifelse(nrow(recon_stat) > 0, 1, 0)
reconciliation_quality_score <- clamp01(0.45 * sample_size_score + 0.25 * evidence_presence_score + 0.20 * stat_sample_score + 0.10 * mapping_coverage)
baseline_quality_score <- clamp01(recon_quality)
reconciliation_confidence <- clamp01(0.40 * sample_size_score + 0.25 * evidence_presence_score + 0.20 * stat_sample_score + 0.15 * baseline_quality_score)

path_bits <- c()
if (behavior_impact_score >= affected_threshold) path_bits <- c(path_bits, "Behavior Loss")
if (transaction_impact_score >= affected_threshold || attribution_impact_score >= affected_threshold) path_bits <- c(path_bits, "Transaction Attribution Gap")
if (conversion_impact_score >= affected_threshold) path_bits <- c(path_bits, "KPI/Conversion Distortion")
if (state_impact_score >= affected_threshold) path_bits <- c(path_bits, "State Reconciliation Drift")
if (length(path_bits) < 1) path_bits <- c("No Cross-domain Propagation")
source_label <- if (grepl("wc_collection", scenario_name, ignore.case = TRUE)) "WC Collection Missing" else if (grepl("partial_missing", scenario_name, ignore.case = TRUE)) "Source Partial Missing" else "Measurement Evidence"
dominant_propagation_path <- paste(c(source_label, path_bits), collapse = " -> ")

evidence_summary <- sprintf(
  "affected_domains=%s propagation=%.3f(%s) reconciliation_confidence=%.3f sample=%d mapping=%.3f stat=%.3f",
  ifelse(length(affected_domains_vec) > 0, paste(affected_domains_vec, collapse = ","), "none"),
  propagation_strength,
  propagation_level,
  reconciliation_confidence,
  as.integer(sample_total),
  mapping_coverage,
  recon_stat_score
)

payload <- make_payload(
  source_table = "v05_reconciliation_measurement_day",
  statistical_evidence_table = "v05_baseline_science_statistical_evidence_day",
  affected_domains = affected_domains_vec,
  metrics = list(
    behavior_transaction_match_rate = behavior_transaction_match_rate,
    transaction_state_match_rate = transaction_state_match_rate,
    behavior_only_count = behavior_only_count,
    transaction_only_count = transaction_only_count,
    orphan_state_count = orphan_state_count,
    transaction_without_state_count = transaction_without_state_count,
    behavior_only_rate = behavior_only_rate,
    transaction_only_rate = transaction_only_rate,
    orphan_state_rate = orphan_state_rate,
    transaction_without_state_rate = transaction_without_state_rate,
    conversion_gap = conversion_gap,
    batch_behavior_score = batch_behavior_score,
    batch_conversion_score = batch_conversion_score,
    obs_gap_score = obs_gap_score,
    statistical_score = recon_stat_score,
    max_z_score = recon_z,
    historical_percentile = recon_percentile,
    co_movement_score = recon_co_movement
  ),
  confidence = list(
    sample_total = sample_total,
    sample_size_score = sample_size_score,
    mapping_coverage = mapping_coverage,
    reconciliation_quality_score = reconciliation_quality_score,
    baseline_quality_score = baseline_quality_score,
    reconciliation_confidence = reconciliation_confidence
  )
)

delete_scoped_rows(con, "v05_cross_domain_propagation_evidence_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
insert_schema_aware(con, "v05_cross_domain_propagation_evidence_day", list(
  run_id = run_id,
  profile_id = profile_id,
  source_gen_run_id = source_gen_run_id,
  target_date = target_date,
  scenario_name = scenario_name,
  affected_domains = jsonlite::toJSON(as.list(affected_domains_vec), auto_unbox = TRUE),
  affected_domain_count = affected_domain_count,
  behavior_impact_score = behavior_impact_score,
  transaction_impact_score = transaction_impact_score,
  state_impact_score = state_impact_score,
  conversion_impact_score = conversion_impact_score,
  attribution_impact_score = attribution_impact_score,
  propagation_strength = propagation_strength,
  propagation_level = propagation_level,
  mapping_coverage = mapping_coverage,
  sample_size_score = sample_size_score,
  reconciliation_quality_score = reconciliation_quality_score,
  baseline_quality_score = baseline_quality_score,
  reconciliation_confidence = reconciliation_confidence,
  dominant_propagation_path = dominant_propagation_path,
  evidence_summary = evidence_summary,
  evidence_payload_json = payload
))

cat(sprintf(
  "[OK] build_v05_cross_domain_propagation_evidence scenario=%s run_id=%s affected_domains=%s propagation=%.6f level=%s reconciliation_confidence=%.6f path=%s\n",
  scenario_name,
  run_id,
  ifelse(length(affected_domains_vec) > 0, paste(affected_domains_vec, collapse = ","), "none"),
  propagation_strength,
  propagation_level,
  reconciliation_confidence,
  dominant_propagation_path
))
