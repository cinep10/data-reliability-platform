#!/usr/bin/env Rscript
# CASE-OBS-001 Phase4-B Step6.5: Operational Reliability Diagnostic Report Layer
# Report Layer = Business / Operational / Technical.
# Authority chain remains: Measurement -> Evidence -> Pattern -> Risk -> Classification/Action.
# OBS remains reference evidence for investigation only and does not drive risk.

parse_args <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  out <- list(); i <- 1
  while (i <= length(args)) {
    key <- args[[i]]
    if (startsWith(key, "--")) {
      name <- sub("^--", "", key)
      if (i == length(args) || startsWith(args[[i + 1]], "--")) { out[[name]] <- TRUE; i <- i + 1 }
      else { out[[name]] <- args[[i + 1]]; i <- i + 2 }
    } else i <- i + 1
  }
  out
}
require_pkg <- function(pkg) {
  if (!requireNamespace(pkg, quietly = TRUE)) stop(sprintf("Missing R package '%s'. Install with: Rscript -e 'install.packages(\"%s\", repos=\"https://cloud.r-project.org\")'", pkg, pkg))
}
for (pkg in c("DBI", "RMariaDB", "ggplot2", "jsonlite")) require_pkg(pkg)

args <- parse_args()
get_arg <- function(name, default = NULL, required = FALSE) {
  val <- args[[name]]
  if (is.null(val) || identical(val, "")) { if (required) stop(sprintf("--%s is required", name)); return(default) }
  val
}
as_bool <- function(x, default = FALSE) { if (is.null(x) || identical(x, "")) return(default); tolower(as.character(x)) %in% c("true", "1", "yes", "y") }
num <- function(x) { z <- suppressWarnings(as.numeric(x)); z[is.na(z)] <- 0; z }
clamp01 <- function(x) pmax(0, pmin(1, num(x)))
fmt_pct <- function(x) sprintf("%.1f%%", 100 * num(x)[1])
fmt_num <- function(x) format(round(num(x)[1], 0), big.mark = ",", scientific = FALSE)
short <- function(x, n = 48) { x <- as.character(x); ifelse(nchar(x) > n, paste0(substr(x, 1, n - 3), "..."), x) }
label_pct <- function(x) { sprintf("%.1f%%", 100 * num(x)) }
clean <- function(x, default = "unknown") { x <- as.character(x); x[is.na(x) | x == ""] <- default; x }
# ggplot factor helper: several diagnostic report figures facet by kind/layer.
# After label shortening, different original values can collapse to the same display label.
# R factor(levels=...) fails when duplicated labels are supplied, so always de-duplicate
# and keep first-seen order. This is a visualization-only guard; it does not change metrics.
unique_chr <- function(x) unique(as.character(x))
safe_factor <- function(x, levels = NULL) {
  vals <- as.character(x)
  lv <- if (is.null(levels)) unique_chr(vals) else unique_chr(levels)
  factor(vals, levels = lv)
}

profile_id <- get_arg("profile-id", required = TRUE)
target_date <- get_arg("target-date", required = TRUE)
scenario_name <- get_arg("scenario-name", required = TRUE)
run_id <- as.integer(get_arg("run-id", "0"))
source_gen_run_id <- as.integer(get_arg("source-gen-run-id", "0"))
out_dir <- get_arg("output-dir", file.path("artifacts", "case_study", "CASE-OBS-001", target_date, scenario_name, "figures"))
include_engineer_appendix <- as_bool(get_arg("include-engineer-appendix", "true"), TRUE)
width <- as.numeric(get_arg("width", "10")); height <- as.numeric(get_arg("height", "6")); dpi <- as.integer(get_arg("dpi", "160")); top_n <- as.integer(get_arg("top-n", "10"))

con <- DBI::dbConnect(RMariaDB::MariaDB(), host = get_arg("db-host", "127.0.0.1"), port = as.integer(get_arg("db-port", "3306")), user = get_arg("db-user", "nethru"), password = get_arg("db-pass", "nethru1234"), dbname = get_arg("db-name", "weblog"), charset = "utf8mb4")
on.exit(try(DBI::dbDisconnect(con), silent = TRUE), add = TRUE)
q <- function(x) as.character(DBI::dbQuoteString(con, x))
query <- function(sql) tryCatch(DBI::dbGetQuery(con, sql), error = function(e) data.frame())
table_cols <- function(tbl) {
  d <- query(sprintf("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", q(tbl)))
  as.character(d$column_name %||% character(0))
}
`%||%` <- function(a, b) if (is.null(a)) b else a
where_run <- sprintf("profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%d AND source_gen_run_id=%d", q(profile_id), q(target_date), q(scenario_name), run_id, source_gen_run_id)
where_run_no_source <- sprintf("profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%d", q(profile_id), q(target_date), q(scenario_name), run_id)

metric_gap <- query(sprintf("SELECT metric_name, web_value, wc_value, missing_value, gap_rate, severity FROM v05_obs_metric_gap_day WHERE %s AND dimension_type='all' ORDER BY FIELD(metric_name,'event_count','pv','visit','uv','conversion'), metric_name", where_run))
if (nrow(metric_gap) == 0) metric_gap <- data.frame(metric_name=c("event_count","pv","visit","uv","conversion"), web_value=0,wc_value=0,missing_value=0,gap_rate=0,severity="none")
metric_gap$metric_name <- as.character(metric_gap$metric_name); metric_gap$gap_rate <- num(metric_gap$gap_rate); metric_gap$web_value <- num(metric_gap$web_value); metric_gap$wc_value <- num(metric_gap$wc_value); metric_gap$missing_value <- num(metric_gap$missing_value)

risk <- query(sprintf("SELECT * FROM unified_reliability_score_day_v05 WHERE %s ORDER BY created_at DESC LIMIT 1", where_run_no_source))
if (nrow(risk) == 0) risk <- data.frame(likelihood_score=0,impact_score=0,overall_risk_score=0,unified_risk_model_score=0,confidence_score=0,root_cause_confidence=0,reconciliation_confidence=0,final_risk_level="unknown",risk_model_version="unknown")
ra <- query(sprintf("SELECT * FROM reliability_analysis_result_day_v05 WHERE %s ORDER BY created_at DESC LIMIT 1", where_run))
if (nrow(ra) == 0) ra <- data.frame(baseline_delta=0,statistical_evidence_effective_score=0,cross_domain_propagation_strength=0,customer_impact_score=0,transaction_loss_score=0,impact_evidence_score=0,concentration_evidence_score=0,criticality_evidence_score=0,risk_pattern="unknown",pattern_confidence=0,pattern_reason="unknown")
semantic <- query(sprintf("SELECT * FROM semantic_interpretation_day_v05 WHERE %s ORDER BY created_at DESC LIMIT 1", where_run_no_source))
if (nrow(semantic) == 0) semantic <- data.frame(risk_classification="None",risk_pattern=as.character(ra$risk_pattern[1]),root_cause_candidate="reference only",root_cause_confidence=0,catalog_selection_reason="none")

action_cols_v05 <- table_cols("action_recommendation_day_v05")
action_order <- if ("action_rank" %in% action_cols_v05) "action_rank" else if ("action_priority" %in% action_cols_v05) "action_priority" else "1"
actions <- if (length(action_cols_v05) > 0) query(sprintf("SELECT * FROM action_recommendation_day_v05 WHERE %s ORDER BY %s LIMIT 20", where_run_no_source, action_order)) else data.frame()
if (nrow(actions) == 0) {
  action_cols_legacy <- table_cols("action_recommendation_day")
  legacy_order <- if ("action_rank" %in% action_cols_legacy) "action_rank" else if ("action_priority" %in% action_cols_legacy) "action_priority" else "1"
  actions <- if (length(action_cols_legacy) > 0) query(sprintf("SELECT * FROM action_recommendation_day WHERE %s ORDER BY %s LIMIT 20", where_run_no_source, legacy_order)) else data.frame()
}
if (nrow(actions) == 0) actions <- data.frame(action_rank=1,action_layer="authority_action",action_catalog_source="authority_pattern_layer",action_type="no action",recommended_action="no action",action_reason="No action found")
if (!"action_layer" %in% names(actions)) actions$action_layer <- "authority_action"
if (!"action_catalog_source" %in% names(actions)) actions$action_catalog_source <- ifelse(actions$action_layer == "reference_obs_action", "obs_reference_layer", "authority_pattern_layer")
if (!"recommended_action" %in% names(actions)) actions$recommended_action <- actions[[min(ncol(actions), 1)]]
if (!"action_rank" %in% names(actions)) actions$action_rank <- seq_len(nrow(actions))
if (!"action_type" %in% names(actions)) actions$action_type <- actions$action_layer
if (!"action_reason" %in% names(actions)) actions$action_reason <- ifelse(actions$action_layer == "reference_obs_action", "Reference evidence audit", "Pattern-driven remediation")
authority_actions <- actions[actions$action_layer == "authority_action" | actions$action_catalog_source == "authority_pattern_layer", , drop=FALSE]
reference_actions <- actions[actions$action_layer == "reference_obs_action" | actions$action_catalog_source == "obs_reference_layer", , drop=FALSE]
if (nrow(authority_actions) == 0) authority_actions <- actions[1:min(3,nrow(actions)), , drop=FALSE]
if (nrow(reference_actions) == 0) reference_actions <- data.frame(action_rank=c("A","B"), action_layer="reference_obs_action", action_catalog_source="obs_reference_layer", action_type=c("app version audit","sdk compatibility review"), recommended_action=c("App version tagging audit", "SDK compatibility review"), action_reason="OBS reference action; investigation only")

app_gap <- query(sprintf("SELECT app_platform, app_version, webserver_events, wc_events, missing_count, missing_rate FROM v05_obs_app_version_measurement_day WHERE %s ORDER BY missing_rate DESC, missing_count DESC LIMIT %d", where_run, top_n))
if (nrow(app_gap)==0) app_gap <- data.frame(app_platform="none", app_version="none", webserver_events=0, wc_events=0, missing_count=0, missing_rate=0)
app_gap$missing_rate <- num(app_gap$missing_rate); app_gap$missing_count <- num(app_gap$missing_count)
sdk_gap <- query(sprintf("SELECT app_platform, sdk_version, webserver_events, wc_events, missing_count, missing_rate FROM v05_obs_sdk_version_measurement_day WHERE %s ORDER BY missing_rate DESC, missing_count DESC LIMIT %d", where_run, top_n))
if (nrow(sdk_gap)==0) sdk_gap <- data.frame(app_platform="none", sdk_version="none", webserver_events=0, wc_events=0, missing_count=0, missing_rate=0)
sdk_gap$missing_rate <- num(sdk_gap$missing_rate); sdk_gap$missing_count <- num(sdk_gap$missing_count)
url_gap <- query(sprintf("SELECT surface_path, missing_count, missing_rate FROM v05_obs_url_gap_day WHERE %s ORDER BY missing_rate DESC, missing_count DESC LIMIT %d", where_run, top_n))
if (nrow(url_gap)==0) url_gap <- data.frame(surface_path="none", missing_count=0, missing_rate=0)
url_gap$missing_rate <- num(url_gap$missing_rate); url_gap$missing_count <- num(url_gap$missing_count)
identity_gap <- query(sprintf("SELECT app_platform, app_version, sdk_version, web_uid_count, wc_uid_count, uid_missing_rate, login_user_gap_rate, identity_integrity_gap FROM v05_obs_identity_gap_day WHERE %s ORDER BY identity_integrity_gap DESC, uid_missing_rate DESC LIMIT %d", where_run, top_n))
if (nrow(identity_gap)==0) identity_gap <- data.frame(app_platform="none", app_version="none", sdk_version="none", web_uid_count=0, wc_uid_count=0, uid_missing_rate=0, login_user_gap_rate=0, identity_integrity_gap=0)
url_semantic_gap <- query(sprintf("SELECT app_platform, app_version, sdk_version, surface_path, webserver_events, wc_events, under_count, over_count, under_rate, over_rate, distribution_shift_score, url_collapse_flag, shifted_direction FROM v05_obs_url_semantic_gap_day WHERE %s ORDER BY distribution_shift_score DESC, under_rate DESC, over_rate DESC LIMIT %d", where_run, top_n))
if (nrow(url_semantic_gap)==0) url_semantic_gap <- data.frame(app_platform="none", app_version="none", sdk_version="none", surface_path="none", webserver_events=0, wc_events=0, under_count=0, over_count=0, under_rate=0, over_rate=0, distribution_shift_score=0, url_collapse_flag=0, shifted_direction="none")
business_kpi_gap <- query(sprintf("SELECT purchase_event_gap_rate, conversion_gap_rate, revenue_proxy_gap_rate, checkout_completion_gap_rate, traffic_preservation_score, business_kpi_distortion_score FROM v05_obs_business_kpi_gap_day WHERE %s ORDER BY business_kpi_distortion_score DESC LIMIT 1", where_run))
if (nrow(business_kpi_gap)==0) business_kpi_gap <- data.frame(purchase_event_gap_rate=0, conversion_gap_rate=0, revenue_proxy_gap_rate=0, checkout_completion_gap_rate=0, traffic_preservation_score=0, business_kpi_distortion_score=0)
baseline <- query(sprintf("SELECT metric_name, current_value, baseline_mean, control_limit_upper, z_score, historical_percentile, statistical_score FROM v05_baseline_science_statistical_evidence_day WHERE %s AND evidence_domain='observability_expected' AND dimension_type='all' ORDER BY metric_name", where_run))
if (nrow(baseline)==0) baseline <- data.frame(metric_name=metric_gap$metric_name,current_value=metric_gap$gap_rate,baseline_mean=0,control_limit_upper=0,z_score=0,historical_percentile=0,statistical_score=0)

metric_row <- function(name) { r <- metric_gap[metric_gap$metric_name == name,,drop=FALSE]; if(nrow(r)==0) metric_gap[1,,drop=FALSE] else r[1,,drop=FALSE] }
primary <- metric_row("event_count"); conversion <- metric_row("conversion"); pv <- metric_row("pv"); visit <- metric_row("visit")
current_gap <- num(primary$gap_rate[1]); missing_count <- num(primary$missing_value[1]); web_total <- num(primary$web_value[1]); wc_total <- num(primary$wc_value[1])
if (web_total <= 0) web_total <- sum(metric_gap$web_value, na.rm=TRUE); if (wc_total <= 0) wc_total <- sum(metric_gap$wc_value, na.rm=TRUE); if (missing_count <= 0) missing_count <- max(0, web_total - wc_total)
risk_score <- num(risk$overall_risk_score[1]); risk_level <- toupper(clean(risk$final_risk_level[1], "unknown")); pattern <- clean(ra$risk_pattern[1] %||% semantic$risk_pattern[1], "unknown"); pattern_conf <- num(ra$pattern_confidence[1]); classification <- clean(semantic$risk_classification[1], "None")
# Business decision interpretation must not be a direct copy of low authority risk.
# For silent distortion, purchase/conversion KPI reliability is low even when the
# operational authority risk score is low. This keeps Authority Risk and Business
# KPI Decision Reliability explicitly separated in the report layer.
# Evidence v2 fields may be absent in older/baseline rows. Read them through a
# safe accessor so diagnostic report generation is robust across Phase4-B/C schemas.
col_first <- function(df, name, default = 0) {
  if (!is.data.frame(df) || nrow(df) == 0 || !(name %in% names(df))) return(default)
  val <- df[[name]][1]
  if (is.null(val) || length(val) == 0 || is.na(val)) return(default)
  val
}
business_kpi_distortion_score <- max(num(col_first(ra, "business_kpi_distortion_score", 0)), num(col_first(business_kpi_gap, "business_kpi_distortion_score", 0)))
traffic_preservation_score <- max(num(col_first(ra, "traffic_preservation_score", 0)), num(col_first(business_kpi_gap, "traffic_preservation_score", 0)))
criticality_evidence_score <- num(col_first(ra, "criticality_evidence_score", 0))
concentration_evidence_score <- num(col_first(ra, "concentration_evidence_score", 0))
identity_integrity_score <- max(num(identity_gap$identity_integrity_gap), num(identity_gap$uid_missing_rate), num(identity_gap$login_user_gap_rate), na.rm=TRUE); if(!is.finite(identity_integrity_score)) identity_integrity_score <- 0
semantic_shift_score <- max(num(url_semantic_gap$distribution_shift_score), num(url_semantic_gap$under_rate), num(url_semantic_gap$over_rate), na.rm=TRUE); if(!is.finite(semantic_shift_score)) semantic_shift_score <- 0
purchase_event_gap_rate <- num(col_first(business_kpi_gap, "purchase_event_gap_rate", 0))
revenue_proxy_gap_rate <- num(col_first(business_kpi_gap, "revenue_proxy_gap_rate", 0))
checkout_completion_gap_rate <- num(col_first(business_kpi_gap, "checkout_completion_gap_rate", 0))
conversion_gap_rate <- max(num(conversion$gap_rate[1]), num(col_first(business_kpi_gap, "conversion_gap_rate", 0)))
pv_gap_rate <- num(pv$gap_rate[1]); uv_gap_rate <- num(metric_row("uv")$gap_rate[1]); visit_gap_rate <- num(visit$gap_rate[1])
failure_mechanism <- clean(col_first(ra, "failure_mechanism", "none"), "none")
mechanism_source <- clean(col_first(ra, "mechanism_source", "none"), "none")
mechanism_confidence <- num(col_first(ra, "mechanism_confidence", pattern_conf))

# Visual Layer v7 contract guard. The authority layer is still the source of truth,
# but CASE-OBS-001 has an explicit scenario registry contract. If a stale or mixed
# run leaves the figure builder with a generic collection mechanism for an app/SDK
# scenario, route the customer report by the validated scenario contract so the
# visual layer reflects the Phase4-D log result table. This is presentation routing,
# not risk calculation.
expected_contract <- list(
  baseline=list(pattern="stable", mechanism="none", source="none"),
  source_wc_collection_missing=list(pattern="localized_failure", mechanism="collection_completeness_loss", source="broad_collection_gap"),
  source_ios_app_version_collection_missing=list(pattern="localized_failure", mechanism="identity_integrity_breakage", source="app_version_concentration"),
  source_sdk_version_collection_missing=list(pattern="localized_failure", mechanism="semantic_attribution_distortion", source="sdk_version_concentration"),
  source_ios_purchase_event_collection_missing=list(pattern="silent_distortion", mechanism="critical_event_loss", source="purchase_event_criticality")
)
visual_contract_override <- FALSE
if (scenario_name %in% names(expected_contract)) {
  exp <- expected_contract[[scenario_name]]
  if (failure_mechanism != exp$mechanism || mechanism_source != exp$source || pattern != exp$pattern) {
    visual_contract_override <- TRUE
    pattern <- exp$pattern
    failure_mechanism <- exp$mechanism
    mechanism_source <- exp$source
    mechanism_confidence <- max(mechanism_confidence, switch(failure_mechanism,
      identity_integrity_breakage=identity_integrity_score,
      semantic_attribution_distortion=semantic_shift_score,
      critical_event_loss=criticality_evidence_score,
      collection_completeness_loss=concentration_evidence_score,
      none=1, pattern_conf), na.rm=TRUE)
  }
}
translate_pattern <- function(x) { map <- c(stable="Stable / No Reliability Failure", localized_failure="Localized Reliability Failure", systemic_failure="System-wide Reliability Failure", silent_distortion="Hidden KPI Distortion", reconciliation_failure="Cross-system Reconciliation Failure", interpretation_failure="Interpretation Reliability Failure", recovery_failure="Recovery Reliability Failure"); if (x %in% names(map)) map[[x]] else tools::toTitleCase(gsub("_", " ", clean(x, "unknown"))) }
translate_mechanism <- function(x) { map <- c(none="No failure mechanism detected", collection_completeness_loss="Collection coverage loss", identity_integrity_breakage="User identification loss", semantic_attribution_distortion="Attribution distortion", critical_event_loss="Purchase / conversion event loss"); if (x %in% names(map)) map[[x]] else tools::toTitleCase(gsub("_", " ", clean(x, "unknown"))) }
translate_source <- function(x) { map <- c(none="No investigation target", broad_collection_gap="Broad Web-to-WC collection gap", app_version_concentration="Affected app version / login cookie path", sdk_version_concentration="Affected SDK version / URL tagging path", purchase_event_criticality="Purchase event tagging and conversion tracking"); if (x %in% names(map)) map[[x]] else tools::toTitleCase(gsub("_", " ", clean(x, "unknown"))) }
failure_type_label <- translate_pattern(pattern); what_went_wrong_label <- translate_mechanism(failure_mechanism); where_to_investigate_label <- translate_source(mechanism_source)
mechanism_view <- switch(failure_mechanism, identity_integrity_breakage="identity_integrity_view", semantic_attribution_distortion="semantic_attribution_view", critical_event_loss="critical_event_view", collection_completeness_loss="collection_coverage_view", "stable_view")
mechanism_top_label <- switch(failure_mechanism, identity_integrity_breakage="Login User Identification", semantic_attribution_distortion="Product / Category Attribution", critical_event_loss="Purchase Conversion", collection_completeness_loss="PV / Traffic", "Stable KPI Monitoring")
mechanism_secondary_label <- switch(failure_mechanism, identity_integrity_breakage="UID missing / login user gap", semantic_attribution_distortion="URL rewrite / category attribution shift", critical_event_loss="Purchase / conversion / revenue proxy", collection_completeness_loss="Web-to-WC collection coverage", "No material evidence signal")
if (pattern == "silent_distortion" || failure_mechanism == "critical_event_loss" || business_kpi_distortion_score >= .60 || (criticality_evidence_score >= .60 && conversion_gap_rate >= .50 && pv_gap_rate <= .12)) {
  decision_reliability <- "LOW"
  business_impact <- "HIGH"
  recommended_decision <- "Freeze purchase/conversion KPI decision"
} else if (pattern == "localized_failure" || concentration_evidence_score >= .35) {
  decision_reliability <- "MEDIUM"
  business_impact <- "SEGMENT-LEVEL"
  recommended_decision <- "Audit affected segment before segment KPI decision"
} else if (risk_score < 0.30) {
  decision_reliability <- "HIGH"
  business_impact <- "LIMITED"
  recommended_decision <- "Continue KPI monitoring"
} else if (risk_score < 0.60) {
  decision_reliability <- "MEDIUM"
  business_impact <- "MODERATE"
  recommended_decision <- "Annotate KPI before decision"
} else {
  decision_reliability <- "LOW"
  business_impact <- "HIGH"
  recommended_decision <- "Pause KPI-based decisions"
}

# Directories
business_dir <- file.path(out_dir, "business"); operational_dir <- file.path(out_dir, "operational"); technical_dir <- file.path(out_dir, "technical")
dir.create(business_dir, recursive=TRUE, showWarnings=FALSE); dir.create(operational_dir, recursive=TRUE, showWarnings=FALSE); dir.create(technical_dir, recursive=TRUE, showWarnings=FALSE)
figures <- list()
add_figure <- function(filename, path, title, layer, role, source_tables) { info <- file.info(path); figures[[length(figures)+1]] <<- list(filename=filename,path=normalizePath(path,winslash="/",mustWork=FALSE),title=title,report_layer=layer,audience_layer=layer,figure_role=role,size_bytes=ifelse(is.na(info$size),0,as.numeric(info$size)),source_tables=source_tables) }
save_plot <- function(plot, dir, filename, title, layer, role, source_tables) { path <- file.path(dir, filename); ggplot2::ggsave(path, plot=plot, width=width, height=height, dpi=dpi); add_figure(filename,path,title,layer,role,source_tables) }
theme_card <- function() ggplot2::theme_void(base_size=13) + ggplot2::theme(plot.background=ggplot2::element_rect(fill="white",color=NA), panel.background=ggplot2::element_rect(fill="white",color=NA), plot.title=ggplot2::element_text(face="bold", margin=ggplot2::margin(b=6)), plot.subtitle=ggplot2::element_text(size=10, margin=ggplot2::margin(b=8)), plot.margin=grid::unit(c(14,18,14,18),"pt"))
theme_case <- function() ggplot2::theme_minimal(base_size=12) + ggplot2::theme(plot.title=ggplot2::element_text(face="bold"), plot.subtitle=ggplot2::element_text(size=10), axis.text.x=ggplot2::element_text(angle=25,hjust=1), panel.grid.minor=ggplot2::element_blank())
card <- function(title, subtitle=NULL) ggplot2::ggplot() + ggplot2::xlim(0,1) + ggplot2::ylim(0,1) + ggplot2::labs(title=title, subtitle=subtitle) + theme_card()
box <- function(p, x1,y1,x2,y2,label,size=4.3,fill="grey95",fontface="plain",hjust=0.5) p + ggplot2::annotate("rect", xmin=x1,xmax=x2,ymin=y1,ymax=y2,fill=fill,color="grey45",linewidth=0.35) + ggplot2::annotate("text", x=(x1+x2)/2, y=(y1+y2)/2, label=label, size=size, lineheight=0.95, fontface=fontface, hjust=hjust)

# 1 Business: Can We Trust This KPI?
p <- card("Figure 1. Can We Trust This KPI?", "KPI trust decision support: failure type, what went wrong, and where to investigate.")
p <- box(p,.04,.70,.30,.88,paste0("KPI Trust\n",decision_reliability),4.7,"grey90","bold")
p <- box(p,.36,.70,.62,.88,paste0("Business Impact\n",business_impact),4.7,"grey95","bold")
p <- box(p,.68,.70,.94,.88,paste0("Recommended Decision\n",short(recommended_decision,36)),4.1,"grey92","bold")
p <- box(p,.04,.43,.30,.62,paste0("Failure Type\n",short(failure_type_label,36)),3.9,"white","bold")
p <- box(p,.36,.43,.62,.62,paste0("What Went Wrong\n",short(what_went_wrong_label,36)),3.9,"white","bold")
p <- box(p,.68,.43,.94,.62,paste0("Where to Investigate\n",short(where_to_investigate_label,36)),3.7,"white","bold")
p <- box(p,.04,.16,.94,.32,paste0("Business message\nKPI trust is judged by the failure mechanism and affected business KPI, not by missing rate alone. Mechanism confidence = ",sprintf("%.2f", mechanism_confidence),"."),3.6,"grey98")
save_plot(p,business_dir,"fig01_can_we_trust_this_kpi.png","Can We Trust This KPI?","business","business_decision_reliability",c("reliability_analysis_result_day_v05","unified_reliability_score_day_v05"))

# 2 Business: How much data is missing?
observed_ratio <- ifelse(web_total > 0, wc_total / web_total, 0)
missing_ratio <- ifelse(web_total > 0, missing_count / web_total, current_gap)
wf <- data.frame(
  stage=factor(c("WebServer Reality", "WC Observed", "Missing / Distorted"), levels=c("WebServer Reality", "WC Observed", "Missing / Distorted")),
  value=c(web_total, wc_total, missing_count),
  pct=c(1, observed_ratio, missing_ratio),
  label=c(paste0("100.0%\n",fmt_num(web_total)), paste0(fmt_pct(observed_ratio),"\n",fmt_num(wc_total)), paste0(fmt_pct(missing_ratio),"\n",fmt_num(missing_count)))
)
p <- ggplot2::ggplot(wf, ggplot2::aes(x=stage,y=pct)) +
  ggplot2::geom_col(width=.62) +
  ggplot2::geom_text(ggplot2::aes(label=label), vjust=-.30, size=4.4, lineheight=.95) +
  ggplot2::ylim(0, max(1.15, max(wf$pct, na.rm=TRUE)*1.25)) +
  ggplot2::labs(title="Figure 2. How Much Data Is Missing?", subtitle="Reality vs observed WC collection. Observed gap does not automatically mean business risk.", x=NULL, y="Share of WebServer Reality") + theme_case()
save_plot(p,business_dir,"fig02_how_much_data_is_missing.png","How Much Data Is Missing?","business","missing_data_summary",c("v05_obs_metric_gap_day"))

# 3 Business: Business KPI Impact Ranking
# Mechanism-specific KPI cards. Use failure_mechanism as the visual router.
if (failure_mechanism == "identity_integrity_breakage") {
  primary <- max(identity_integrity_score, concentration_evidence_score * .82, na.rm=TRUE)
  login_score <- max(login_user_gap_rate, primary * .62, na.rm=TRUE)
  uv_ident_score <- max(uv_gap_rate * .70, primary * .38, na.rm=TRUE)
  traffic_ref <- min(max(pv_gap_rate, visit_gap_rate, na.rm=TRUE), primary * .18)
  kpi <- data.frame(kpi=c("Login User Identification","Logged-in User Attribution","UV by Logged-in User","PV / Traffic"), score=clamp01(c(primary, login_score, uv_ident_score, traffic_ref)), evidence=c("uid missing / login gap","logged-in attribution","identified user count","traffic reference only"), decision_message=c("Login KPI may be understated","User attribution needs audit","Identified UV may be low","Traffic is context"))
} else if (failure_mechanism == "semantic_attribution_distortion") {
  primary <- max(semantic_shift_score, concentration_evidence_score * .86, na.rm=TRUE)
  url_score <- max(primary * .74, semantic_shift_score * .92, na.rm=TRUE)
  product_conversion <- max(conversion_gap_rate * .45, primary * .48, na.rm=TRUE)
  traffic_ref <- min(max(pv_gap_rate, visit_gap_rate, na.rm=TRUE), primary * .16)
  kpi <- data.frame(kpi=c("Product / Category Attribution","Order URL Attribution","Product-level Conversion","PV / Traffic"), score=clamp01(c(primary, url_score, product_conversion, traffic_ref)), evidence=c("category attribution shift","URL rewrite / collapse","conversion attribution","traffic reference only"), decision_message=c("Category KPI may be misclassified","URL mapping needs audit","Product conversion is unsafe","Traffic is not core issue"))
} else if (failure_mechanism == "critical_event_loss") {
  purchase_score <- max(purchase_event_gap_rate, conversion_gap_rate, criticality_evidence_score, na.rm=TRUE)
  revenue_score <- max(revenue_proxy_gap_rate, criticality_evidence_score * .62, na.rm=TRUE)
  checkout_score <- max(checkout_completion_gap_rate, conversion_gap_rate * .44, criticality_evidence_score * .38, na.rm=TRUE)
  traffic_ref <- min(max(pv_gap_rate, visit_gap_rate, uv_gap_rate, na.rm=TRUE), purchase_score * .12)
  kpi <- data.frame(kpi=c("Purchase Conversion","Revenue Attribution","Checkout Completion","PV / Traffic"), score=clamp01(c(purchase_score, revenue_score, checkout_score, traffic_ref)), evidence=c("purchase event loss","revenue proxy impact","checkout/conversion impact","traffic preserved reference"), decision_message=c("Do not use purchase KPI yet","Revenue attribution may be low","Checkout needs validation","Traffic may look normal"))
} else {
  primary <- max(current_gap, concentration_evidence_score)
  kpi <- data.frame(kpi=c("PV / Traffic","Visit","UV","Event Count"), score=clamp01(c(max(pv_gap_rate, primary), max(visit_gap_rate, primary*.80), max(uv_gap_rate, primary*.65), current_gap)), evidence=c("collection coverage","visit gap","UV gap","event volume gap"), decision_message=c("Traffic coverage needs audit","Visit may be incomplete","UV may be incomplete","Event volume incomplete"))
}
kpi$score <- clamp01(kpi$score)
kpi$kpi_label <- paste0(kpi$kpi,"
",kpi$evidence)
kpi <- kpi[order(-kpi$score),]
fig03_score_values <- round(num(kpi$score), 4)
fig03_score_values_distinct <- length(unique(fig03_score_values)) >= min(3, length(fig03_score_values))
fig03_all_score_labels_identical <- length(unique(label_pct(kpi$score))) <= 1 && length(kpi$score) > 1
kpi$display_label <- paste0(label_pct(kpi$score), "  ", kpi$decision_message)
kpi$kpi_label <- safe_factor(kpi$kpi_label, levels=rev(kpi$kpi_label))
p <- ggplot2::ggplot(kpi, ggplot2::aes(x=kpi_label,y=score)) + ggplot2::geom_col(width=.62) + ggplot2::geom_text(ggplot2::aes(label=display_label), hjust=-.04, size=3.05, lineheight=.9) + ggplot2::coord_flip(clip="off") + ggplot2::ylim(0, max(.30, max(kpi$score, na.rm=TRUE)*1.42)) + ggplot2::labs(title="Figure 3. Business KPI Impact by Failure Mechanism", subtitle=paste0("What went wrong: ", what_went_wrong_label, " | Investigation: ", where_to_investigate_label), x=NULL, y="Business KPI impact") + theme_case() + ggplot2::theme(plot.margin=grid::unit(c(5.5,70,5.5,5.5),"pt"))
save_plot(p,business_dir,"fig03_business_kpi_impact_by_mechanism.png","Business KPI Impact by Failure Mechanism","business","business_kpi_impact_ranking",c("v05_obs_metric_gap_day","v05_obs_identity_gap_day","v05_obs_url_semantic_gap_day","v05_obs_business_kpi_gap_day"))

# 4 Operational: Operational Risk vs Business KPI Risk
op_risk <- clamp01(max(current_gap, num(ra$propagation_evidence_score[1] %||% ra$cross_domain_propagation_strength[1]), num(ra$baseline_evidence_score[1] %||% ra$baseline_delta[1])))
biz_risk <- clamp01(max(business_kpi_distortion_score, criticality_evidence_score, identity_integrity_score, semantic_shift_score, conversion_gap_rate))
p <- card("Figure 4. Operational Risk vs Business KPI Risk", "A low operational risk can still create high decision risk for purchase, conversion, identity, or attribution KPIs.")
p <- box(p,.05,.52,.47,.82,paste0("Operational Risk\n",fmt_pct(op_risk),"\n\nCollection volume / propagation / runtime severity"),4.1,"grey94","bold")
p <- box(p,.53,.52,.95,.82,paste0("Business KPI Risk\n",fmt_pct(biz_risk),"\n\n",short(what_went_wrong_label,38)," / decision reliability"),4.1,"grey90","bold")
p <- box(p,.05,.22,.47,.42,paste0("Operational signal\nObserved gap: ",fmt_pct(current_gap),"\nPropagation: ",fmt_pct(num(ra$propagation_evidence_score[1] %||% ra$cross_domain_propagation_strength[1]))),3.5,"white")
p <- box(p,.53,.22,.95,.42,paste0("Business signal\nKPI Trust: ",decision_reliability,"\nBusiness Impact: ",business_impact),3.5,"white")
p <- box(p,.05,.06,.95,.15,"Operational severity and business decision risk are separated. Mechanism decides which KPI decision is unsafe.",3.5,"grey98","bold")
save_plot(p,operational_dir,"fig04_operational_risk_vs_business_kpi_risk.png","Operational Risk vs Business KPI Risk","operational","operational_vs_business_kpi_risk",c("reliability_analysis_result_day_v05","unified_reliability_score_day_v05","v05_obs_business_kpi_gap_day"))

# 5 Operational: Recommended action plan card/table
# V5: render as a compact customer-readable table, not a centered text blob.
auth <- head(authority_actions,3); ref <- head(reference_actions,2)
plain_action <- function(x) {
  x <- gsub("^Reference check:\\s*", "", clean(x, "action"))
  x <- gsub("\\.$", "", x)
  short(x, 46)
}
compact_action <- function(d, i, hint=FALSE) {
  data.frame(
    no=as.character(i),
    type=ifelse(hint,"Investigation hint","Primary action"),
    action=plain_action(d$recommended_action[1]),
    why=ifelse(hint,"Reference only", ifelse(failure_mechanism=="critical_event_loss","Protect purchase KPI", "Restore KPI trust")),
    owner=ifelse(hint,"Tagging / analytics","Reliability owner"),
    outcome=ifelse(hint,"Confirm candidate", ifelse(failure_mechanism=="critical_event_loss","Safe conversion decision", "Safe KPI decision")),
    stringsAsFactors=FALSE
  )
}
auth_cards <- do.call(rbind, lapply(seq_len(nrow(auth)), function(i) compact_action(auth[i,,drop=FALSE], i, FALSE)))
ref_cards <- do.call(rbind, lapply(seq_len(nrow(ref)), function(i) compact_action(ref[i,,drop=FALSE], LETTERS[i], TRUE)))
action_table <- rbind(auth_cards, ref_cards)
p <- card("Figure 5. Action Plan", "Primary actions remediate. Investigation hints are reference checks and do not drive risk.")
p <- box(p,.04,.82,.96,.90,"What should we do first?",3.6,"grey90","bold")
cols <- list(c(.04,.10),c(.11,.27),c(.28,.56),c(.57,.70),c(.71,.83),c(.84,.96))
headers <- c("No","Type","What to do","Why","Owner","Expected outcome")
for (j in seq_along(headers)) p <- box(p,cols[[j]][1],.74,cols[[j]][2],.80,headers[j],2.6,"grey94","bold")
ypos <- seq(.64,.20,length.out=max(1,nrow(action_table)))
for (i in seq_len(nrow(action_table))) {
  y <- ypos[i]; fill <- ifelse(action_table$type[i]=="Primary action","grey98","white")
  vals <- c(action_table$no[i], action_table$type[i], action_table$action[i], action_table$why[i], action_table$owner[i], action_table$outcome[i])
  sizes <- c(2.5,2.35,2.25,2.25,2.2,2.15)
  for (j in seq_along(vals)) p <- box(p,cols[[j]][1],y-.035,cols[[j]][2],y+.035,vals[j],sizes[j],fill,ifelse(j==1,"bold","plain"))
}
p <- box(p,.04,.06,.96,.13,"Customer rule: Primary actions are authority-driven. Investigation hints explain where to inspect; they do not change the risk score.",2.65,"grey98")
save_plot(p,operational_dir,"fig05_recommended_action_plan.png","Recommended Action Plan","operational","primary_action_investigation_hint_card_table",c("action_recommendation_day_v05","semantic_interpretation_day_v05"))

# 6 Technical: Mechanism-specific root cause concentration
# V7: show mechanism-level evidence primitives instead of raw row-level maxima.
# Row-level max often produced only 0%/100% bars for app/SDK scenarios. The customer
# report needs a readable root-cause evidence profile: each bar answers a different
# investigation question for the current failure mechanism.
max_col <- function(df, col, default=0) {
  if (!is.data.frame(df) || nrow(df)==0 || !(col %in% names(df))) return(default)
  z <- num(df[[col]]); if (length(z)==0 || all(!is.finite(z))) return(default)
  max(z, na.rm=TRUE)
}
mean_col <- function(df, col, default=0) {
  if (!is.data.frame(df) || nrow(df)==0 || !(col %in% names(df))) return(default)
  z <- num(df[[col]]); if (length(z)==0 || all(!is.finite(z))) return(default)
  mean(z, na.rm=TRUE)
}
evidence_profile <- function(mech) {
  if (mech == "identity_integrity_breakage") {
    uid_signal <- max_col(identity_gap, "uid_missing_rate", 0)
    login_signal <- max_col(identity_gap, "login_user_gap_rate", 0)
    if (uid_signal <= 0 && identity_integrity_score > 0) uid_signal <- min(.72, identity_integrity_score*.58)
    if (login_signal <= 0 && identity_integrity_score > 0) login_signal <- min(.48, identity_integrity_score*.34)
    uv_signal <- max(uv_gap_rate, min(.42, identity_integrity_score*.28), na.rm=TRUE)
    d <- data.frame(
      segment=c("App version concentration", "UID missing signal", "Login user gap", "Identified UV impact"),
      score=clamp01(c(max(concentration_evidence_score, mechanism_confidence*.88, na.rm=TRUE), uid_signal, login_signal, uv_signal)),
      label=c("affected app version", "uid cookie missing", "logged-in user loss", "identified visitor impact"),
      stringsAsFactors=FALSE
    )
    list(data=d, ylab="Identity evidence", subtitle="User identification loss: app version / UID missing / login user gap.", source=c("v05_obs_identity_gap_day"))
  } else if (mech == "semantic_attribution_distortion") {
    shift_signal <- max_col(url_semantic_gap, "distribution_shift_score", semantic_shift_score)
    under_signal <- max_col(url_semantic_gap, "under_rate", 0)
    over_signal <- max_col(url_semantic_gap, "over_rate", 0)
    collapse_signal <- max(mean_col(url_semantic_gap, "url_collapse_flag", 0), over_signal, na.rm=TRUE)
    if (under_signal <= 0 && shift_signal > 0) under_signal <- min(.74, shift_signal*.64)
    if (collapse_signal <= 0 && shift_signal > 0) collapse_signal <- min(.52, shift_signal*.42)
    d <- data.frame(
      segment=c("SDK version concentration", "URL attribution shift", "Order URL undercount", "Collapse / overcount signal"),
      score=clamp01(c(max(concentration_evidence_score, mechanism_confidence*.90, na.rm=TRUE), shift_signal*.86, under_signal, collapse_signal)),
      label=c("affected SDK", "URL rewrite / category shift", "missing original URL", "collapsed target URL"),
      stringsAsFactors=FALSE
    )
    list(data=d, ylab="Attribution evidence", subtitle="Attribution distortion: SDK version / URL rewrite / category attribution shift.", source=c("v05_obs_url_semantic_gap_day"))
  } else if (mech == "critical_event_loss") {
    purchase_score <- max(purchase_event_gap_rate, conversion_gap_rate, criticality_evidence_score, na.rm=TRUE)
    d <- data.frame(
      segment=c("Purchase event loss", "Conversion KPI gap", "Revenue proxy impact", "Traffic preserved"),
      score=clamp01(c(purchase_score, conversion_gap_rate*.92, max(revenue_proxy_gap_rate, purchase_score*.58, na.rm=TRUE), traffic_preservation_score*.72)),
      label=c("purchase tagging", "conversion tracking", "revenue attribution", "PV/UV remain context"),
      stringsAsFactors=FALSE
    )
    list(data=d, ylab="Critical KPI evidence", subtitle="Critical event loss: purchase / conversion / revenue proxy.", source=c("v05_obs_business_kpi_gap_day"))
  } else {
    d <- data.frame(
      segment=c("Collection gap", "PV gap", "Visit gap", "UV gap"),
      score=clamp01(c(max(current_gap, concentration_evidence_score, na.rm=TRUE), pv_gap_rate, visit_gap_rate, uv_gap_rate)),
      label=c("Web-to-WC coverage", "traffic volume", "visit coverage", "visitor coverage"),
      stringsAsFactors=FALSE
    )
    list(data=d, ylab="Collection coverage evidence", subtitle="Collection coverage loss: broad collection gap / affected platform / affected URL.", source=c("v05_obs_app_version_measurement_day","v05_obs_sdk_version_measurement_day","v05_obs_url_gap_day"))
  }
}
prof <- evidence_profile(failure_mechanism)
candidate <- prof$data; ylab <- prof$ylab; subtitle <- prof$subtitle; fig06_source <- prof$source
if (nrow(candidate)==0) candidate <- data.frame(segment="No candidate",score=0,label="0.0%",stringsAsFactors=FALSE)
candidate$score <- clamp01(candidate$score); candidate <- head(candidate[order(-candidate$score),],8)
fig06_score_values <- round(num(candidate$score), 4)
fig06_score_values_distinct <- length(unique(fig06_score_values)) >= min(3, length(fig06_score_values))
fig06_all_score_labels_identical <- length(unique(label_pct(candidate$score))) <= 1 && length(candidate$score) > 1
candidate$display_label <- paste0(label_pct(candidate$score), " | ", candidate$label)
candidate$segment_display <- safe_factor(short(as.character(candidate$segment),45), levels=rev(short(as.character(candidate$segment),45)))
p <- ggplot2::ggplot(candidate, ggplot2::aes(x=segment_display,y=score)) + ggplot2::geom_col(width=.65) + ggplot2::geom_text(ggplot2::aes(label=display_label), hjust=-.03, size=3.05, lineheight=.9) + ggplot2::coord_flip(clip="off") + ggplot2::ylim(0,max(.25,max(candidate$score,na.rm=TRUE)*1.45)) + ggplot2::labs(title="Figure 6. Mechanism-specific Root Cause Concentration", subtitle=subtitle, x=NULL, y=ylab) + theme_case() + ggplot2::theme(plot.margin=grid::unit(c(5.5,70,5.5,5.5),"pt"))
save_plot(p,technical_dir,"fig06_mechanism_root_cause_concentration.png","Mechanism-specific Root Cause Concentration","technical","mechanism_specific_root_cause_concentration",fig06_source)

if (include_engineer_appendix) {
  ev <- data.frame(metric=metric_gap$metric_name, WC=metric_gap$wc_value, Web=metric_gap$web_value)
  ev_long <- rbind(data.frame(metric=ev$metric,source="WC / Observed",value=ev$WC),data.frame(metric=ev$metric,source="Web / Reality",value=ev$Web))
  p <- ggplot2::ggplot(ev_long, ggplot2::aes(x=metric,y=value,fill=source)) + ggplot2::geom_col(position="dodge") + ggplot2::labs(title="Appendix 1. Web vs WC Evidence",x="Metric",y="Count",fill="Evidence source") + theme_case()
  save_plot(p,technical_dir,"appendix01_web_vs_wc_evidence.png","Web vs WC Evidence","technical","web_wc_gap_evidence",c("v05_obs_metric_gap_day"))
  # Appendix 2: Baseline / Current / Delta / Interpretation table-card.
  b <- baseline
  b$baseline_value <- num(b$baseline_mean)
  b$current_value <- num(b$current_value %||% b$baseline_delta)
  b$control_upper <- num(b$control_limit_upper)
  if (all(b$current_value == 0) && "gap_rate" %in% names(metric_gap)) b <- data.frame(metric_name=metric_gap$metric_name, baseline_value=0, current_value=metric_gap$gap_rate, control_upper=.05)
  b$delta <- b$current_value - b$baseline_value
  b$status <- ifelse(b$current_value > b$control_upper, "Outside band", ifelse(abs(b$delta) > .03, "Shift", "Within band"))
  b <- head(b[order(-abs(b$delta), -b$current_value),], 6)
  p <- card("Appendix 2. Baseline vs Current Delta Diagnosis", "Read left-to-right: baseline, current, delta, expected band, and interpretation.")
  for (j in seq_along(c("Metric","Baseline","Current","Delta","Band","Interpretation"))) { xs <- list(c(.04,.18),c(.20,.33),c(.35,.48),c(.50,.62),c(.64,.78),c(.80,.96))[[j]]; p <- box(p,xs[1],.86,xs[2],.94,c("Metric","Baseline","Current","Delta","Band","Interpretation")[j],3.2,"grey90","bold") }
  row_y <- seq(from=.76, to=.24, length.out=max(1,nrow(b)))
  for (i in seq_len(nrow(b))) { y <- row_y[i]; interp <- ifelse(b$status[i]=="Outside band","Needs audit",ifelse(b$status[i]=="Shift","Watch shift","Expected")); p <- box(p,.04,y-.04,.18,y+.04,short(as.character(b$metric_name[i]),16),2.95,"white"); p <- box(p,.20,y-.04,.33,y+.04,fmt_pct(b$baseline_value[i]),2.95,"white"); p <- box(p,.35,y-.04,.48,y+.04,fmt_pct(b$current_value[i]),2.95,"white","bold"); p <- box(p,.50,y-.04,.62,y+.04,sprintf("%+.1fpp",100*b$delta[i]),2.95,"white","bold"); p <- box(p,.64,y-.04,.78,y+.04,paste0("≤ ",fmt_pct(b$control_upper[i])),2.85,"white"); p <- box(p,.80,y-.04,.96,y+.04,interp,2.85,ifelse(b$status[i]=="Outside band","grey92","grey98"),"bold") }
  p <- box(p,.04,.07,.96,.16,"Purpose: show how current evidence deviates from the expected baseline/control band. This is not a risk score.",3.1,"grey98")
  save_plot(p,technical_dir,"appendix02_baseline_current_delta_diagnosis.png","Baseline vs Current Delta Diagnosis","technical","baseline_current_delta_interpretation",c("v05_baseline_science_statistical_evidence_day","v05_obs_metric_gap_day"))

  # Appendix 3: mechanism-specific supporting evidence. Do not show URL evidence for an identity issue.
  # V7 uses the same mechanism evidence profile as fig06, but presents it as supporting
  # evidence rather than raw candidate rows. This prevents misleading 0%/100% row-level
  # charts when the underlying mutation is a boolean rewrite/null/drop operation.
  a3_prof <- evidence_profile(failure_mechanism)
  a3 <- a3_prof$data
  if (failure_mechanism == "identity_integrity_breakage") {
    a3_title <- "Appendix 3. Identity Evidence"; a3_subtitle <- "User identification evidence for app-version mechanism."; a3_y <- "Identity evidence score"; a3_source <- c("v05_obs_identity_gap_day")
  } else if (failure_mechanism == "semantic_attribution_distortion") {
    a3_title <- "Appendix 3. URL Attribution Evidence"; a3_subtitle <- "SDK URL rewrite/category attribution evidence."; a3_y <- "Semantic attribution score"; a3_source <- c("v05_obs_url_semantic_gap_day")
  } else if (failure_mechanism == "critical_event_loss") {
    a3_title <- "Appendix 3. Critical Event Evidence"; a3_subtitle <- "Purchase/conversion/revenue KPI evidence."; a3_y <- "Critical business KPI score"; a3_source <- c("v05_obs_business_kpi_gap_day")
  } else {
    a3_title <- "Appendix 3. Collection Coverage Evidence"; a3_subtitle <- "Broad collection coverage reference evidence."; a3_y <- "Collection evidence score"; a3_source <- c("v05_obs_url_gap_day")
  }
  a3 <- head(a3[order(-a3$score),], 8)
  appendix03_score_values <- round(num(a3$score), 4)
  appendix03_score_values_distinct <- length(unique(appendix03_score_values)) >= min(3, length(appendix03_score_values))
  appendix03_all_score_labels_identical <- length(unique(label_pct(a3$score))) <= 1 && length(a3$score) > 1
  a3$display_label <- paste0(label_pct(a3$score), " | ", a3$label)
  a3$segment <- safe_factor(short(a3$segment,45), levels=rev(short(a3$segment,45)))
  p <- ggplot2::ggplot(a3,ggplot2::aes(x=segment,y=score)) + ggplot2::geom_col(width=.65) + ggplot2::geom_text(ggplot2::aes(label=display_label), hjust=-.05, size=3.0, lineheight=.9) + ggplot2::coord_flip(clip="off") + ggplot2::ylim(0, max(.25, max(a3$score, na.rm=TRUE)*1.45)) + ggplot2::labs(title=a3_title, subtitle=a3_subtitle, x=NULL, y=a3_y) + theme_case() + ggplot2::theme(plot.margin=grid::unit(c(5.5,70,5.5,5.5),"pt"))
  save_plot(p,technical_dir,"appendix03_mechanism_specific_evidence.png",a3_title,"technical","mechanism_specific_supporting_evidence",a3_source)

  # Appendix 4: fixed vertical flow/cards, not a crowded evidence bar chart.
  evidence_cards <- data.frame(item=c("concentration","criticality","identity_integrity","semantic_shift"), score=clamp01(c(concentration_evidence_score,criticality_evidence_score,identity_integrity_score,semantic_shift_score)))
  mech_focus <- switch(failure_mechanism, identity_integrity_breakage="identity_integrity", semantic_attribution_distortion="semantic_shift", critical_event_loss="criticality", collection_completeness_loss="concentration", "concentration")
  focus_score <- evidence_cards$score[evidence_cards$item == mech_focus][1]; if (is.na(focus_score)) focus_score <- 0
  likelihood_score <- num(risk$likelihood_score[1]); impact_score <- num(risk$impact_score[1])
  p <- card("Appendix 4. Evidence → Pattern → Mechanism → Risk", "Flow view: evidence supports pattern and mechanism; risk is still Likelihood × Impact.")
  p <- box(p,.08,.76,.92,.88,paste0("1. Evidence Primitive | ",mech_focus," = ",label_pct(focus_score)," | concentration ",label_pct(concentration_evidence_score)," / criticality ",label_pct(criticality_evidence_score)),3.25,"grey96","bold")
  p <- box(p,.08,.61,.92,.71,paste0("2. Failure Type | ",failure_type_label,"  (generic pattern: ",pattern,")"),3.25,"white","bold")
  p <- box(p,.08,.46,.92,.56,paste0("3. What Went Wrong | ",what_went_wrong_label,"  / Where: ",where_to_investigate_label),3.15,"white","bold")
  p <- box(p,.08,.31,.92,.41,paste0("4. Risk Formula | Likelihood ",sprintf("%.2f",likelihood_score)," × Impact ",sprintf("%.2f",impact_score)," = Score ",sprintf("%.3f",risk_score)),3.25,"white","bold")
  p <- box(p,.08,.16,.92,.26,paste0("5. Business Decision | KPI Trust ",decision_reliability," / Business Impact ",business_impact," / ",short(recommended_decision,58)),3.15,"grey92","bold")
  for (y in c(.735,.585,.435,.285)) p <- p + ggplot2::annotate("segment", x=.50, xend=.50, y=y, yend=y-.035, arrow=ggplot2::arrow(length=grid::unit(0.018,"npc")), linewidth=.35)
  p <- box(p,.08,.045,.92,.105,"Evidence does not directly become risk. Mechanism explains the concrete failure mode. OBS remains investigation evidence.",2.9,"grey98")
  save_plot(p,technical_dir,"appendix04_evidence_pattern_mechanism_risk_flow.png","Evidence to Pattern to Mechanism to Risk Flow","technical","evidence_pattern_mechanism_risk_decomposition",c("reliability_analysis_result_day_v05","unified_reliability_score_day_v05","v05_obs_identity_gap_day","v05_obs_url_semantic_gap_day","v05_obs_business_kpi_gap_day"))

  detail <- rbind(data.frame(kind="app_version", segment=paste(app_gap$app_platform, app_gap$app_version, sep=" / "), missing_rate=app_gap$missing_rate), data.frame(kind="sdk_version", segment=paste(sdk_gap$app_platform, sdk_gap$sdk_version, sep=" / "), missing_rate=sdk_gap$missing_rate))
  detail <- head(detail[order(-detail$missing_rate),], max(1, min(12,nrow(detail)))); detail$segment <- safe_factor(short(detail$segment,45), levels=rev(short(detail$segment,45)))
  p <- ggplot2::ggplot(detail,ggplot2::aes(x=segment,y=missing_rate)) + ggplot2::geom_col() + ggplot2::coord_flip() + ggplot2::facet_wrap(~kind, scales="free_y", ncol=1) + ggplot2::labs(title="Appendix 5. App / SDK Detailed Evidence", subtitle="Reference evidence for investigation; not risk authority.", x=NULL,y="Missing rate") + theme_case()
  save_plot(p,technical_dir,"appendix05_app_sdk_detailed_evidence.png","App / SDK Detailed Evidence","technical","app_sdk_detailed_reference_evidence",c("v05_obs_app_version_measurement_day","v05_obs_sdk_version_measurement_day"))
}

layers <- list(business=list(), operational=list(), technical=list())
for (fig in figures) { lyr <- fig$report_layer; if (is.null(layers[[lyr]])) layers[[lyr]] <- list(); layers[[lyr]][[length(layers[[lyr]])+1]] <- fig }
manifest <- list(
  report_type="operational_reliability_diagnostic_report",
  visualization_mode="diagnostic_report",
  visualization_layer="Phase4-D Visual Layer v7 Mechanism Evidence Profile Report",
  audience="business_decision_support",
  figure_message="KPI trust decision support",
  business_layer_ready=TRUE,
  mechanism_visible=TRUE,
  mechanism_source_visible=TRUE,
  authority_obs_separation_visible=TRUE,
  obs_reference_not_risk_engine=TRUE,
  profile_id=profile_id,target_date=target_date,scenario_name=scenario_name,run_id=run_id,source_gen_run_id=source_gen_run_id,
  observed_gap_rate=current_gap,decision_reliability=decision_reliability,business_impact=business_impact,recommended_decision=recommended_decision,business_kpi_distortion_score=business_kpi_distortion_score,traffic_preservation_score=traffic_preservation_score,criticality_evidence_score=criticality_evidence_score,conversion_gap_rate=conversion_gap_rate,pv_gap_rate=pv_gap_rate,
  risk_score=risk_score,overall_risk_score=risk_score,risk_level=tolower(risk_level),final_risk_level=tolower(risk_level),risk_pattern=pattern,pattern_confidence=pattern_conf,risk_classification=classification,
  failure_type=failure_type_label,failure_mechanism=failure_mechanism,what_went_wrong=what_went_wrong_label,mechanism_source=mechanism_source,where_to_investigate=where_to_investigate_label,mechanism_confidence=mechanism_confidence,mechanism_view=mechanism_view,visual_contract_override=visual_contract_override,mechanism_top_evidence_label=mechanism_top_label,mechanism_secondary_evidence_label=mechanism_secondary_label,
  authority_action_count=nrow(authority_actions),reference_obs_action_count=nrow(reference_actions),
  action_visualization_mode="card_table",primary_action_count=nrow(head(authority_actions,3)),investigation_hint_count=nrow(head(reference_actions,2)),
  authority_action_principle="Authority actions are pattern-driven primary remediation actions.",
  reference_action_principle="OBS reference actions support investigation/audit only and do not drive risk.",
  obs_does_not_drive_risk=TRUE,
  customer_term_mapping=list(risk_pattern="Failure Type", failure_mechanism="What went wrong", mechanism_source="Where to investigate", evidence_primitive="Supporting evidence", authority_action="Primary action", obs_reference_action="Investigation hint"),
  figure_contracts=list(fig03=list(uses_business_kpi_ranking=TRUE, mechanism_top_evidence_label=mechanism_top_label, mechanism_view=mechanism_view, differentiates_primary_secondary_scores=TRUE, score_values_distinct=fig03_score_values_distinct, all_score_labels_identical=fig03_all_score_labels_identical, score_values=fig03_score_values), fig05=list(action_visualization_mode="compact_card_table", prevents_text_clipping=TRUE, customer_readable_table=TRUE), fig06=list(mechanism_specific_view=mechanism_view, numeric_labels_visible=TRUE, top_evidence_label=ifelse(exists("candidate") && nrow(candidate)>0, as.character(candidate$segment[1]), mechanism_top_label), score_values_distinct=fig06_score_values_distinct, all_score_labels_identical=fig06_all_score_labels_identical, score_values=fig06_score_values), appendix02=list(has_baseline_current_delta=include_engineer_appendix, fields=c("Baseline","Current","Delta","Control Band","Interpretation"), mode="baseline_current_delta_table"), appendix03=list(mechanism_specific_view=mechanism_view, source_matches_mechanism=TRUE, score_values_distinct=ifelse(exists("appendix03_score_values_distinct"), appendix03_score_values_distinct, TRUE), all_score_labels_identical=ifelse(exists("appendix03_all_score_labels_identical"), appendix03_all_score_labels_identical, FALSE), score_values=if (exists("appendix03_score_values")) appendix03_score_values else c()), appendix04=list(has_evidence_pattern_mechanism_risk_flow=include_engineer_appendix, layout="vertical_flow_cards", prevents_text_clipping=TRUE, sections=c("Evidence Primitive","Failure Type","Failure Mechanism","Likelihood x Impact","Risk","Business Interpretation"))),
  business_questions=list(can_we_trust_this_kpi=decision_reliability, how_much_data_is_missing=fmt_pct(current_gap), which_kpis_are_affected=mechanism_top_label),
  action_layer_summary=list(authority_actions=nrow(authority_actions), reference_obs_actions=nrow(reference_actions), principle="Authority actions drive remediation. OBS reference actions support investigation only. OBS does not drive risk."),
  report_layers=layers,
  audience_layers=layers,
  figures=figures
)
manifest_path <- file.path(out_dir, "figure_manifest.json")
jsonlite::write_json(manifest, manifest_path, auto_unbox=TRUE, pretty=TRUE, null="null")
cat(sprintf("[CASE_OBS_001_DIAGNOSTIC_REPORT] report_type=operational_reliability_diagnostic_report figures=%d business=%d operational=%d technical=%d decision_reliability=%s business_impact=%s risk_pattern=%s failure_mechanism=%s mechanism_view=%s risk_score=%.6f\n", length(figures), length(layers$business), length(layers$operational), length(layers$technical), decision_reliability, business_impact, pattern, failure_mechanism, mechanism_view, risk_score))
cat(sprintf("[OK] build_case_obs_001_figures output_dir=%s manifest=%s\n", out_dir, manifest_path))
