#!/usr/bin/env Rscript
# -----------------------------------------------------------------------------
# ARCHITECTURE LAYER: KNOWLEDGE BASE - PATTERN CLASSIFICATION / NARRATIVE
#
# Semantic is not a risk engine. It consumes:
#   Authority Pattern Layer + Authority Risk Layer
# and maps generic risk_pattern into a business-facing risk classification and
# narrative. OBS remains Reference Evidence for explanation/root-cause context.
# -----------------------------------------------------------------------------

source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))

args <- commandArgs(trailingOnly = TRUE)
profile_id <- arg_value(args, "--profile-id")
target_date <- arg_value(args, "--target-date")
run_id <- as.integer(arg_value(args, "--run-id"))
source_gen_run_id <- as.integer(arg_value(args, "--source-gen-run-id", "0"))
scenario_name <- arg_value(args, "--scenario-name", "baseline")
is_baseline_like <- tolower(scenario_name) %in% c("baseline", "normal", "stable")

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)

if (!table_exists(con, "semantic_interpretation_day_v05")) stop("missing semantic_interpretation_day_v05")

# Existing Knowledge Base output contract.
ensure_column(con, "semantic_interpretation_day_v05", "runtime_semantic_score", "DOUBLE NULL")
ensure_column(con, "semantic_interpretation_day_v05", "dominant_runtime_signal", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "observability_semantic_score", "DOUBLE NULL")
ensure_column(con, "semantic_interpretation_day_v05", "dominant_observability_signal", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "semantic_kb_version", "VARCHAR(80) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "semantic_role", "VARCHAR(80) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "semantic_is_risk_driver", "TINYINT NULL")
ensure_column(con, "semantic_interpretation_day_v05", "risk_classification", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "narrative_template_id", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "risk_narrative", "TEXT NULL")
ensure_column(con, "semantic_interpretation_day_v05", "likelihood_score", "DOUBLE NULL")
ensure_column(con, "semantic_interpretation_day_v05", "likelihood_level", "VARCHAR(64) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "impact_score", "DOUBLE NULL")
ensure_column(con, "semantic_interpretation_day_v05", "impact_level", "VARCHAR(64) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "authority_risk_score", "DOUBLE NULL")
ensure_column(con, "semantic_interpretation_day_v05", "authority_risk_level", "VARCHAR(64) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "root_cause_candidate", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "root_cause_confidence", "DOUBLE NULL")
ensure_column(con, "semantic_interpretation_day_v05", "confidence_level", "VARCHAR(64) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "action_catalog_key", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "evidence_signal", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "evidence_metric", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "evidence_value", "DOUBLE NULL")
ensure_column(con, "semantic_interpretation_day_v05", "evidence_threshold", "DOUBLE NULL")
ensure_column(con, "semantic_interpretation_day_v05", "mapping_rule_id", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "catalog_selection_reason", "TEXT NULL")
ensure_column(con, "semantic_interpretation_day_v05", "catalog_selection_payload_json", "LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL")

# Phase4-B Step4: Classification is explicit and pattern-driven.
ensure_column(con, "semantic_interpretation_day_v05", "classification_layer_version", "VARCHAR(80) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "classification_role", "VARCHAR(80) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "classification_source", "VARCHAR(80) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "risk_pattern", "VARCHAR(80) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "pattern_confidence", "DOUBLE NULL")
ensure_column(con, "semantic_interpretation_day_v05", "pattern_reason", "VARCHAR(1024) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "classification_is_risk_engine", "TINYINT NULL")
ensure_column(con, "semantic_interpretation_day_v05", "pattern_to_classification_rule_id", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "failure_mechanism", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "mechanism_source", "VARCHAR(128) NULL")
ensure_column(con, "semantic_interpretation_day_v05", "mechanism_confidence", "DOUBLE NULL")

level_from_score <- function(x) {
  s <- clamp01(x)
  if (s >= 0.75) "critical" else if (s >= 0.55) "high" else if (s >= 0.30) "warning" else if (s >= 0.08) "low" else "stable"
}

short_text <- function(x, n = 1000) {
  x <- as.character(ifelse(is.na(x), "", x))
  if (nchar(x, type = "chars") <= n) return(x)
  paste0(substr(x, 1, n - 3), "...")
}

root_candidate <- function(dim, label) {
  d <- tolower(as.character(dim))
  if (!is.null(label) && !is.na(label) && nzchar(as.character(label)) && as.character(label) != "none") return(as.character(label))
  if (grepl("app_version", d)) return("APP_VERSION_TAGGING_BREAKAGE")
  if (grepl("sdk", d)) return("SDK_COMPATIBILITY_OR_COLLECTION_BREAKAGE")
  if (grepl("url", d)) return("URL_TAGGING_BREAKAGE")
  if (grepl("client|browser|os", d)) return("CLIENT_COVERAGE_GAP")
  "UNKNOWN_ROOT_CAUSE"
}

classification_for_pattern <- function(pattern, risk_level) {
  if (pattern == "stable" || risk_level == "stable") {
    return(list(
      classification = "None",
      catalog_key = "none",
      narrative_template_id = "NO_RISK",
      rule_id = "PATTERN_STABLE_TO_NO_CLASSIFICATION_V1",
      evidence_signal = "stable_pattern",
      evidence_metric = "risk_pattern",
      threshold = 0,
      narrative = "정상 기준선 범위 내에 있어 별도 운영 판단 보류나 조치가 필요하지 않다."
    ))
  }
  if (pattern == "localized_failure") {
    return(list(
      classification = "Operational Observability Reliability",
      catalog_key = "localized_reliability",
      narrative_template_id = "PATTERN_LOCALIZED_FAILURE",
      rule_id = "PATTERN_LOCALIZED_FAILURE_TO_OBSERVABILITY_RELIABILITY_V1",
      evidence_signal = "localized_failure_pattern",
      evidence_metric = "pattern_confidence",
      threshold = 0.20,
      narrative = "특정 segment에 reliability failure가 집중된 localized failure 패턴이다. 전체 장애로 단정하기보다 affected segment를 분리해 검증해야 한다."
    ))
  }
  if (pattern == "systemic_failure") {
    return(list(
      classification = "Operational Observability Reliability",
      catalog_key = "systemic_reliability",
      narrative_template_id = "PATTERN_SYSTEMIC_FAILURE",
      rule_id = "PATTERN_SYSTEMIC_FAILURE_TO_OBSERVABILITY_RELIABILITY_V1",
      evidence_signal = "systemic_failure_pattern",
      evidence_metric = "pattern_confidence",
      threshold = 0.20,
      narrative = "여러 지표와 도메인으로 전파된 systemic failure 패턴이다. collector/pipeline/service 계층의 광범위한 이상 가능성을 우선 점검해야 한다."
    ))
  }
  if (pattern == "silent_distortion") {
    return(list(
      classification = "Business Semantic Distortion",
      catalog_key = "critical_kpi_distortion",
      narrative_template_id = "PATTERN_SILENT_DISTORTION",
      rule_id = "PATTERN_SILENT_DISTORTION_TO_BUSINESS_SEMANTIC_DISTORTION_V1",
      evidence_signal = "silent_distortion_pattern",
      evidence_metric = "pattern_confidence",
      threshold = 0.20,
      narrative = "전체 볼륨 변화는 제한적이지만 중요한 KPI/event가 훼손되는 silent distortion 패턴이다. 운영 의사결정에 쓰이는 KPI 해석을 보류해야 한다."
    ))
  }
  if (pattern == "reconciliation_failure") {
    return(list(
      classification = "Cross-Domain Reconciliation Reliability",
      catalog_key = "reconciliation_reliability",
      narrative_template_id = "PATTERN_RECONCILIATION_FAILURE",
      rule_id = "PATTERN_RECONCILIATION_FAILURE_TO_RECONCILIATION_RELIABILITY_V1",
      evidence_signal = "reconciliation_failure_pattern",
      evidence_metric = "pattern_confidence",
      threshold = 0.20,
      narrative = "관측/행동/거래/상태 간 운영 사실이 일치하지 않는 reconciliation failure 패턴이다. 단일 gap 수치보다 cross-domain mismatch를 우선 검증해야 한다."
    ))
  }
  if (pattern == "interpretation_failure") {
    return(list(
      classification = "AI Reliability",
      catalog_key = "interpretation_reliability",
      narrative_template_id = "PATTERN_INTERPRETATION_FAILURE",
      rule_id = "PATTERN_INTERPRETATION_FAILURE_TO_AI_RELIABILITY_V1",
      evidence_signal = "interpretation_failure_pattern",
      evidence_metric = "pattern_confidence",
      threshold = 0.20,
      narrative = "증거와 해석 사이의 불일치가 의심되는 interpretation failure 패턴이다. 설명과 조치 추천은 evidence-bound review가 필요하다."
    ))
  }
  list(
    classification = "Operational Decision Reliability",
    catalog_key = "reliability_investigation",
    narrative_template_id = "PATTERN_EMERGING_RELIABILITY_DEGRADATION",
    rule_id = "PATTERN_EMERGING_DEGRADATION_TO_OPERATIONAL_DECISION_RELIABILITY_V1",
    evidence_signal = "emerging_reliability_degradation_pattern",
    evidence_metric = "pattern_confidence",
    threshold = 0.20,
    narrative = "명확한 단일 실패 유형으로 확정되기 전의 emerging reliability degradation 패턴이다. 추가 evidence 수집과 운영 검토가 필요하다."
  )
}

risk <- read_first_scoped_row(con, "unified_reliability_score_day_v05", profile_id, target_date, run_id, source_gen_run_id, NULL)
analysis <- read_first_scoped_row(con, "reliability_analysis_result_day_v05", profile_id, target_date, run_id, source_gen_run_id, NULL)
obs <- read_scoped_table(con, "r_v05_observability_interpretation_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name, limit = 1)
obs_analysis <- read_first_scoped_row(con, "r_v05_observability_analysis_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)
obs_measurement <- read_first_scoped_row(con, "v05_observability_measurement_day", profile_id, target_date, run_id, source_gen_run_id, scenario_name)

if (nrow(risk) < 1) stop("missing unified risk row; semantic classification must run after build_v05_unified_risk_score.R")
if (nrow(analysis) < 1) stop("missing reliability analysis row; pattern classification requires Authority Analytics output")

risk_score <- clamp01(pick_number(risk, c("overall_risk_score", "unified_risk_model_score")))
risk_level_value <- pick_character(risk, "final_risk_level", "stable")
likelihood_score <- clamp01(pick_number(risk, "likelihood_score"))
impact_score <- clamp01(pick_number(risk, "impact_score"))
confidence_score <- clamp01(pick_number(risk, "confidence_score"))
confidence_level_value <- pick_character(risk, "confidence_level", level_from_score(confidence_score))
reconciliation_confidence <- clamp01(pick_number(risk, "reconciliation_confidence"))
root_cause_confidence <- clamp01(pick_number(risk, "root_cause_confidence"))
risk_pattern <- pick_character(risk, "risk_pattern", pick_character(analysis, "risk_pattern", if (is_baseline_like) "stable" else "emerging_reliability_degradation"))
pattern_confidence <- clamp01(pick_number(risk, "pattern_confidence", pick_number(analysis, "pattern_confidence", 0)))
pattern_reason <- pick_character(risk, "pattern_reason", pick_character(analysis, "pattern_reason", "pattern reason unavailable"))
failure_mechanism <- pick_character(risk, "failure_mechanism", pick_character(analysis, "failure_mechanism", if (is_baseline_like) "none" else "unknown"))
mechanism_source <- pick_character(risk, "mechanism_source", pick_character(analysis, "mechanism_source", if (is_baseline_like) "none" else "unknown"))
mechanism_confidence <- clamp01(pick_number(risk, "mechanism_confidence", pick_number(analysis, "mechanism_confidence", 0)))

obs_confidence <- if (nrow(obs) > 0) clamp01(pick_number(obs, "root_cause_confidence")) else 0
obs_dim <- if (nrow(obs) > 0) pick_character(obs, "root_cause_dimension", "none") else "none"
obs_label <- if (nrow(obs) > 0) pick_character(obs, "root_cause_label", "none") else "none"
obs_signal <- if (nrow(obs_analysis) > 0) pick_character(obs_analysis, c("dominant_observability_signal", "dominant_signal"), "none") else "none"
obs_score <- if (nrow(obs_analysis) > 0) clamp01(pick_number(obs_analysis, c("observability_overall_score", "overall_observability_risk_score", "overall_score"))) else 0
obs_web_hits <- pick_number(obs_measurement, "web_hits")
obs_wc_hits <- pick_number(obs_measurement, "wc_hits")
obs_collection_gap_rate <- clamp01(pick_number(obs_measurement, "collection_gap_rate"))
obs_collection_gap_count <- pick_number(obs_measurement, "collection_gap_count")

if (obs_confidence > root_cause_confidence) root_cause_confidence <- obs_confidence
if (mechanism_confidence > root_cause_confidence) root_cause_confidence <- mechanism_confidence
root_cause_candidate <- root_candidate(obs_dim, obs_label)
if (failure_mechanism == "identity_integrity_breakage") root_cause_candidate <- "IDENTITY_INTEGRITY_BREAKAGE"
if (failure_mechanism == "semantic_attribution_distortion") root_cause_candidate <- "SEMANTIC_ATTRIBUTION_DISTORTION"
if (failure_mechanism == "critical_event_loss") root_cause_candidate <- "CRITICAL_EVENT_LOSS"
if (failure_mechanism == "collection_completeness_loss") root_cause_candidate <- "COLLECTION_COMPLETENESS_LOSS"
if (risk_pattern == "stable" || is_baseline_like || risk_score < 0.08) {
  root_cause_candidate <- "NONE"
  root_cause_confidence <- 0
  confidence_level_value <- "none"
}

mapping <- classification_for_pattern(risk_pattern, risk_level_value)
classification <- mapping$classification
catalog_key <- mapping$catalog_key
narrative_template_id <- mapping$narrative_template_id
pattern_to_classification_rule_id <- mapping$rule_id
evidence_signal <- mapping$evidence_signal
evidence_metric <- mapping$evidence_metric
evidence_value <- if (risk_pattern == "stable") risk_score else pattern_confidence
evidence_threshold <- mapping$threshold
mapping_rule_id <- pattern_to_classification_rule_id

catalog_selection_reason <- paste0(
  "classification/action catalog selected from risk_pattern=", risk_pattern,
  "; pattern_confidence=", sprintf("%.6f", pattern_confidence),
  "; risk_level=", risk_level_value,
  "; semantic_is_risk_driver=false; OBS is reference explanation only",
  if (!is.na(obs_dim) && obs_dim != "none") paste0("; obs_reference_dimension=", obs_dim, "; obs_reference_candidate=", root_cause_candidate) else "",
  "."
)

narrative <- paste0(
  mapping$narrative,
  " Authority Risk 결과는 pattern=", risk_pattern,
  ", likelihood=", sprintf("%.3f", likelihood_score),
  ", impact=", sprintf("%.3f", impact_score),
  ", risk=", sprintf("%.3f", risk_score),
  ", mechanism=", failure_mechanism,
  ", mechanism_source=", mechanism_source,
  ", confidence=", sprintf("%.3f", root_cause_confidence),
  "이다. OBS는 원인 후보 설명에만 사용된다."
)

catalog_selection_payload <- make_payload(
  architecture_layer = "KNOWLEDGE_BASE_CLASSIFICATION",
  principle = "Pattern + risk drive classification; OBS is reference explanation; classification is not risk.",
  pattern_mapping = list(
    risk_pattern = risk_pattern,
    pattern_confidence = pattern_confidence,
    pattern_reason = pattern_reason,
    failure_mechanism = failure_mechanism,
    mechanism_source = mechanism_source,
    mechanism_confidence = mechanism_confidence,
    classification = classification,
    catalog_key = catalog_key,
    pattern_to_classification_rule_id = pattern_to_classification_rule_id
  ),
  authority_risk = list(
    table = "unified_reliability_score_day_v05",
    risk_model_version = pick_character(risk, "risk_model_version", "unknown"),
    likelihood_score = likelihood_score,
    impact_score = impact_score,
    risk_score = risk_score,
    risk_level = risk_level_value,
    pattern_is_risk_driver = pick_number(risk, "pattern_is_risk_driver") == 1,
    evidence_direct_to_risk = pick_number(risk, "evidence_direct_to_risk")
  ),
  obs_reference = list(
    use = "root_cause_candidate_explanation_only",
    top_dimension = obs_dim,
    top_label = obs_label,
    root_cause_candidate = root_cause_candidate,
    root_cause_confidence = root_cause_confidence,
    observability_score = obs_score,
    web_hits = obs_web_hits,
    wc_hits = obs_wc_hits,
    collection_gap_rate = obs_collection_gap_rate,
    collection_gap_count = obs_collection_gap_count
  )
)

semantic_scores <- list(
  behavior_transaction_consistency_score = 0,
  transaction_state_integrity_score = 0,
  order_lifecycle_consistency_score = 0,
  payment_state_reconciliation_score = 0,
  delivery_timeliness_score = 0,
  coupon_attribution_score = 0,
  customer_experience_score = 0,
  runtime_semantic_score = 0,
  observability_semantic_score = obs_score
)

payload <- make_payload(
  architecture_layer = "KNOWLEDGE_BASE",
  semantic_role = "pattern_classification_and_narrative",
  semantic_is_risk_driver = FALSE,
  classification_is_risk_engine = FALSE,
  classification_source = "authority_pattern_layer",
  risk_source = list(
    table = "unified_reliability_score_day_v05",
    risk_model_version = pick_character(risk, "risk_model_version", "unknown"),
    formula = pick_character(risk, "risk_model_formula", "unknown"),
    confidence_separate_from_risk = pick_number(risk, "confidence_separate_from_risk") == 1
  ),
  pattern = list(
    risk_pattern = risk_pattern,
    pattern_confidence = pattern_confidence,
    pattern_reason = pattern_reason,
    failure_mechanism = failure_mechanism,
    mechanism_source = mechanism_source,
    mechanism_confidence = mechanism_confidence
  ),
  classification = classification,
  narrative_template_id = narrative_template_id,
  action_catalog_key = catalog_key,
  root_cause = list(candidate = root_cause_candidate, confidence = root_cause_confidence, confidence_level = confidence_level_value),
  authority_scores = list(likelihood = likelihood_score, impact = impact_score, risk = risk_score, risk_level = risk_level_value),
  evidence_signal = evidence_signal,
  evidence_metric = evidence_metric,
  evidence_value = evidence_value,
  evidence_threshold = evidence_threshold,
  mapping_rule_id = mapping_rule_id,
  catalog_selection_reason = catalog_selection_reason,
  catalog_selection_payload_json = catalog_selection_payload,
  obs_reference_use = "root_cause_candidate_and_report_explanation_only"
)

delete_scoped_rows(con, "semantic_interpretation_day_v05", profile_id, target_date, run_id, source_gen_run_id, NULL)
insert_schema_aware(con, "semantic_interpretation_day_v05", c(list(
  run_id = run_id,
  profile_id = profile_id,
  source_gen_run_id = source_gen_run_id,
  target_date = target_date,
  scenario_name = scenario_name,
  dominant_semantic_risk = classification,
  dominant_runtime_signal = pick_character(risk, "dominant_runtime_signal", "none"),
  dominant_observability_signal = obs_signal,
  semantic_kb_version = "v05_phase4b_step4_pattern_classification_v1",
  semantic_role = "pattern_classification_and_narrative",
  semantic_is_risk_driver = 0,
  classification_layer_version = "v05_phase4b_step4_pattern_classification_v1",
  classification_role = "risk_pattern_to_business_classification",
  classification_source = "authority_pattern_layer",
  risk_pattern = risk_pattern,
  pattern_confidence = pattern_confidence,
  pattern_reason = short_text(pattern_reason, 1000),
  failure_mechanism = failure_mechanism,
  mechanism_source = mechanism_source,
  mechanism_confidence = mechanism_confidence,
  classification_is_risk_engine = 0,
  pattern_to_classification_rule_id = pattern_to_classification_rule_id,
  risk_classification = classification,
  narrative_template_id = narrative_template_id,
  risk_narrative = narrative,
  likelihood_score = likelihood_score,
  likelihood_level = level_from_score(likelihood_score),
  impact_score = impact_score,
  impact_level = level_from_score(impact_score),
  authority_risk_score = risk_score,
  authority_risk_level = risk_level_value,
  root_cause_candidate = root_cause_candidate,
  root_cause_confidence = root_cause_confidence,
  confidence_level = confidence_level_value,
  action_catalog_key = catalog_key,
  evidence_signal = evidence_signal,
  evidence_metric = evidence_metric,
  evidence_value = evidence_value,
  evidence_threshold = evidence_threshold,
  mapping_rule_id = mapping_rule_id,
  catalog_selection_reason = catalog_selection_reason,
  catalog_selection_payload_json = catalog_selection_payload,
  semantic_payload_json = payload
), semantic_scores))

cat(sprintf(
  "[KNOWLEDGE_BASE_CLASSIFICATION] version=v05_phase4b_step4_pattern_classification_v1 pattern=%s pattern_confidence=%.6f classification=%s catalog=%s semantic_is_risk_driver=0 classification_is_risk_engine=0 source=authority_pattern_layer obs_reference_only=1 rule=%s\n",
  risk_pattern, pattern_confidence, classification, catalog_key, pattern_to_classification_rule_id
))
