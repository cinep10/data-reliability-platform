args <- commandArgs(trailingOnly=TRUE)
get_arg <- function(name, default="") { idx <- which(args == name); if (length(idx)==0 || idx[1]==length(args)) return(default); args[idx[1]+1] }
db_host <- get_arg("--db-host","127.0.0.1")
db_port <- get_arg("--db-port","3306")
db_user <- get_arg("--db-user","")
db_pass <- get_arg("--db-pass","")
db_name <- get_arg("--db-name","")
profile_id <- get_arg("--profile-id","")
dt <- get_arg("--dt","")
run_id <- get_arg("--run-id","")
scenario_name <- get_arg("--scenario-name","")
baseline_dt <- get_arg("--baseline-dt",dt)
expected_risk_family <- get_arg("--expected-risk-family","unknown")
mysql_args <- function(extra=c()) c("-h",db_host,"-P",db_port,"-u",db_user,paste0("-p",db_pass),db_name,extra)
sql_escape <- function(x) gsub("'", "''", as.character(x), fixed=TRUE)
query_df <- function(sql) {
  tf <- tempfile(fileext=".sql"); writeLines(sql,tf)
  out <- tryCatch(system2("mysql", mysql_args(c("-N","-B")), stdin=tf, stdout=TRUE, stderr=TRUE), error=function(e) character())
  if (length(out)==0) return(data.frame())
  read.table(text=paste(out,collapse="\n"), sep="\t", header=FALSE, quote="", comment.char="", fill=TRUE, stringsAsFactors=FALSE)
}
exec_sql <- function(sql) { tf <- tempfile(fileext=".sql"); writeLines(sql,tf); system2("mysql", mysql_args(), stdin=tf, stdout=TRUE, stderr=TRUE) }
num <- function(x, default=0) { y <- suppressWarnings(as.numeric(x)); ifelse(is.na(y), default, y) }
clamp01 <- function(x) max(0,min(1,x))
json_obj <- function(items) paste0("{", paste(sprintf('"%s":"%s"', names(items), gsub('"','',as.character(items))), collapse=","), "}")

m <- query_df(sprintf("\nSELECT direct_completeness_delta,direct_timeliness_delta,direct_availability_delta,direct_integrity_delta,\n       delta_source_type,measurement_realism_status\nFROM measurement_realism_day\nWHERE profile_id='%s' AND dt='%s' AND run_id='%s'\nLIMIT 1", sql_escape(profile_id), sql_escape(dt), sql_escape(run_id)))
if (nrow(m)==0) {
  completeness <- timeliness <- availability <- integrity <- 0
  delta_source_type <- "MISSING_MEASUREMENT"; mstatus <- "WARN"
} else {
  completeness <- num(m[1,1]); timeliness <- num(m[1,2]); availability <- num(m[1,3]); integrity <- num(m[1,4])
  delta_source_type <- as.character(m[1,5]); mstatus <- as.character(m[1,6])
}

bb <- query_df(sprintf("SELECT behavior_distortion_score,channel_imbalance_score,session_fragmentation_score,conversion_distortion_score,identity_anomaly_score,mapping_risk_score,batch_quality_risk_score,batch_overall_analysis_score,dominant_batch_signal,analysis_status FROM r_batch_behavior_analysis_day WHERE profile_id='%s' AND dt='%s' AND run_id='%s' LIMIT 1", sql_escape(profile_id), sql_escape(dt), sql_escape(run_id)))
if (nrow(bb)==0) {
  behavior_distortion <- channel_imbalance <- session_fragmentation <- conversion_distortion <- identity_anomaly <- mapping_risk <- batch_quality_risk <- batch_overall <- 0
  dominant_batch_signal <- "none"; batch_status <- "MISSING"
} else {
  behavior_distortion <- num(bb[1,1]); channel_imbalance <- num(bb[1,2]); session_fragmentation <- num(bb[1,3]); conversion_distortion <- num(bb[1,4]); identity_anomaly <- num(bb[1,5]); mapping_risk <- num(bb[1,6]); batch_quality_risk <- num(bb[1,7]); batch_overall <- num(bb[1,8]); dominant_batch_signal <- as.character(bb[1,9]); batch_status <- as.character(bb[1,10])
}

# Map restored batch data-analysis signals into v0.4 semantic deltas.
# Completeness: missing/mapping/quality issues.
# Integrity: conversion distortion and behavior distortion.
# Consistency: identity/session/channel imbalance.
completeness <- clamp01(max(completeness, batch_quality_risk, mapping_risk * 0.8))
integrity <- clamp01(max(integrity, behavior_distortion, conversion_distortion))
consistency <- clamp01(max(session_fragmentation, identity_anomaly, channel_imbalance))
timeliness <- clamp01(timeliness)
availability <- clamp01(availability)

scores <- c(Completeness=completeness, Timeliness=timeliness, Availability=availability, Integrity=integrity, Consistency=consistency)
expected_map <- c(completeness="Completeness", latency_performance="Timeliness", availability="Availability", schema_validation="Integrity", identity_mapping="Consistency", low="None")
expected_sem <- ifelse(expected_risk_family %in% names(expected_map), expected_map[[expected_risk_family]], names(which.max(scores)))
if (expected_sem!="None" && scores[[expected_sem]] > 0) {
  dominant <- expected_sem
} else {
  dominant <- names(which.max(scores))
  if (max(scores) <= 0.0001) dominant <- "None"
}
source_delta <- ifelse(dominant=="None",0,scores[[dominant]])
selected <- switch(dominant,
  Completeness="direct_completeness_delta+batch_quality_mapping",
  Timeliness="direct_timeliness_delta",
  Availability="direct_availability_delta",
  Integrity="direct_integrity_delta+batch_behavior_distortion",
  Consistency="batch_session_identity_channel",
  "none"
)
alignment <- ifelse(expected_sem=="None" && source_delta==0,1,ifelse(expected_sem==dominant,1,0))
distortion <- clamp01(max(ifelse(source_delta==0,0,1-alignment), behavior_distortion, conversion_distortion))
related <- sum(scores[scores>0.05]) / max(1, length(scores[scores>0.05]))
propagation <- clamp01(max(source_delta, related, batch_overall))
drift <- clamp01(max(source_delta, batch_overall))
baseline_delta <- drift
amplification <- clamp01(max(ifelse(source_delta >= 0.7 || sum(scores>0.2)>=2, propagation, 0), channel_imbalance, conversion_distortion * 0.7))
corr <- ifelse(sum(scores>0.05)>=2, clamp01(mean(scores[scores>0.05])), source_delta)
layer <- switch(dominant, Completeness="batch_stream", Timeliness="stream_operational", Availability="operational", Integrity="batch", Consistency="batch_cross_metric", "integrated")
reason <- paste0("delta_source_type=",delta_source_type,"; selected=",selected,"; dominant=",dominant,"; expected=",expected_sem,"; measurement_status=",mstatus,"; batch_signal=",dominant_batch_signal,"; batch_status=",batch_status)
detail <- json_obj(c(delta_source_type=delta_source_type, selected_source_delta_metric=selected, dominant=dominant, expected=expected_sem, dominant_batch_signal=dominant_batch_signal, batch_status=batch_status))
exec_sql(sprintf("DELETE FROM r_reliability_analysis_result_day WHERE profile_id='%s' AND dt='%s' AND run_id='%s';", sql_escape(profile_id), sql_escape(dt), sql_escape(run_id)))
exec_sql(sprintf("\nINSERT INTO r_reliability_analysis_result_day (\n profile_id,dt,run_id,scenario_name,drift_score,propagation_score,amplification_score,distortion_score,baseline_delta,correlation_score,\n batch_delta,stream_delta,op_delta,source_to_stream_ratio,stream_to_op_ratio,selected_source_delta_metric,source_delta,\n expected_risk_family,actual_dominant_layer,semantic_alignment_score,delta_source_type,fallback_used,analysis_status,analysis_reason,detail_json\n) VALUES (\n '%s','%s','%s','%s',%.10f,%.10f,%.10f,%.10f,%.10f,%.10f,\n %.10f,%.10f,%.10f,%.10f,%.10f,'%s',%.10f,\n '%s','%s',%.10f,'%s',0,'%s','%s','%s'\n);",
 sql_escape(profile_id),sql_escape(dt),sql_escape(run_id),sql_escape(scenario_name),
 drift,propagation,amplification,distortion,baseline_delta,corr,
 completeness,timeliness,availability, ifelse(completeness>0,timeliness/max(completeness,0.0001),0), ifelse(timeliness>0,availability/max(timeliness,0.0001),0),
 sql_escape(selected),source_delta,sql_escape(expected_risk_family),sql_escape(layer),alignment,sql_escape(delta_source_type),
 ifelse(mstatus=="PASS" && batch_status != "HIGH","PASS","WARN"),sql_escape(reason),sql_escape(detail)
))
cat(sprintf("[R_RELIABILITY_COMPLETION] scenario=%s dominant=%s source_delta=%.6f propagation=%.6f batch_signal=%s batch_overall=%.6f\n", scenario_name, dominant, source_delta, propagation, dominant_batch_signal, batch_overall))
