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

m <- query_df(sprintf("
SELECT direct_completeness_delta,direct_timeliness_delta,direct_availability_delta,direct_integrity_delta,delta_source_type
FROM measurement_realism_day
WHERE profile_id='%s' AND dt='%s' AND run_id='%s' LIMIT 1", sql_escape(profile_id),sql_escape(dt),sql_escape(run_id)))
if (nrow(m)==0) {
  completeness <- timeliness <- availability <- integrity <- consistency <- 0
  delta_source_type <- "MISSING_MEASUREMENT"
} else {
  completeness <- num(m[1,1]); timeliness <- num(m[1,2]); availability <- num(m[1,3]); integrity <- num(m[1,4]); consistency <- 0
  delta_source_type <- as.character(m[1,5])
}
expected_map <- c(completeness="Completeness", latency_performance="Timeliness", availability="Availability", schema_validation="Integrity", identity_mapping="Consistency", low="None")
expected_sem <- ifelse(expected_risk_family %in% names(expected_map), expected_map[[expected_risk_family]], "Unknown")
scores <- c(Integrity=integrity, Completeness=completeness, Timeliness=timeliness, Consistency=consistency, Availability=availability)
# Calibration rule:
# expected semantic remains primary when its direct score exists.
if (expected_sem!="None" && expected_sem!="Unknown" && scores[[expected_sem]] > 0) {
  dominant <- expected_sem
  confidence <- scores[[expected_sem]]
} else if (max(scores) <= 0.0001) {
  dominant <- "None"; confidence <- 0
} else {
  dominant <- names(which.max(scores)); confidence <- max(scores)
}
secondary <- "None"
tmp <- sort(scores[names(scores)!=dominant], decreasing=TRUE)
if (length(tmp)>0 && tmp[1] > 0.05) secondary <- names(tmp)[1]
reason <- paste0("delta_source_type=",delta_source_type,"; dominant=",dominant,"; secondary=",secondary,"; expected_family=",expected_risk_family,"; calibrated_primary=",expected_sem)
detail <- json_obj(c(delta_source_type=delta_source_type, dominant=dominant, secondary=secondary, expected=expected_sem))
exec_sql(sprintf("DELETE FROM semantic_interpretation_day WHERE profile_id='%s' AND dt='%s' AND run_id='%s';", sql_escape(profile_id), sql_escape(dt), sql_escape(run_id)))
exec_sql(sprintf("
INSERT INTO semantic_interpretation_day (
 profile_id,dt,run_id,scenario_name,dominant_semantic_risk,secondary_semantic_risk,semantic_confidence,
 integrity_score,completeness_score,timeliness_score,consistency_score,availability_score,
 delta_source_type,fallback_used,interpretation_reason,detail_json
) VALUES (
 '%s','%s','%s','%s','%s','%s',%.10f,
 %.10f,%.10f,%.10f,%.10f,%.10f,
 '%s',0,'%s','%s'
);",
 sql_escape(profile_id),sql_escape(dt),sql_escape(run_id),sql_escape(scenario_name),sql_escape(dominant),sql_escape(secondary),confidence,
 integrity,completeness,timeliness,consistency,availability,sql_escape(delta_source_type),sql_escape(reason),sql_escape(detail)
))
cat(sprintf("[R_SEMANTIC_COMPLETION] scenario=%s dominant=%s secondary=%s confidence=%.6f delta_source_type=%s\n", scenario_name, dominant, secondary, confidence, delta_source_type))
