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
mysql_args <- function(extra=c()) c("-h",db_host,"-P",db_port,"-u",db_user,paste0("-p",db_pass),db_name,extra)
sql_escape <- function(x) gsub("'", "''", as.character(x), fixed=TRUE)
query_df <- function(sql) { tf <- tempfile(fileext=".sql"); writeLines(sql,tf); out <- tryCatch(system2("mysql", mysql_args(c("-N","-B")), stdin=tf, stdout=TRUE, stderr=TRUE), error=function(e) character()); if(length(out)==0) return(data.frame()); read.table(text=paste(out,collapse="\n"),sep="\t",header=FALSE,quote="",comment.char="",fill=TRUE,stringsAsFactors=FALSE) }
exec_sql <- function(sql) { tf <- tempfile(fileext=".sql"); writeLines(sql,tf); system2("mysql", mysql_args(), stdin=tf, stdout=TRUE, stderr=TRUE) }
num <- function(x, default=0) { y <- suppressWarnings(as.numeric(x)); ifelse(is.na(y), default, y) }
clamp01 <- function(x) max(0,min(1,x))
json_obj <- function(items) paste0("{", paste(sprintf('"%s":"%s"', names(items), gsub('"','',as.character(items))), collapse=","), "}")

s <- query_df(sprintf("
SELECT dominant_semantic_risk,semantic_confidence,delta_source_type
FROM semantic_interpretation_day
WHERE profile_id='%s' AND dt='%s' AND run_id='%s' LIMIT 1", sql_escape(profile_id),sql_escape(dt),sql_escape(run_id)))
r <- query_df(sprintf("
SELECT amplification_score,distortion_score,baseline_delta,delta_source_type
FROM r_reliability_analysis_result_day
WHERE profile_id='%s' AND dt='%s' AND run_id='%s' LIMIT 1", sql_escape(profile_id),sql_escape(dt),sql_escape(run_id)))
if(nrow(s)==0){ dom <- "None"; conf <- 0; delta_source_type <- "MISSING_SEMANTIC" } else { dom <- as.character(s[1,1]); conf <- num(s[1,2]); delta_source_type <- as.character(s[1,3]) }
amp <- ifelse(nrow(r)>0,num(r[1,1]),0)
dist <- ifelse(nrow(r)>0,num(r[1,2]),0)
base_delta <- ifelse(nrow(r)>0,num(r[1,3]),conf)
base_risk <- clamp01(conf)
amplification_weight <- clamp01(amp*0.15)
distortion_penalty <- clamp01(dist*0.10)
baseline_delta_penalty <- clamp01(base_delta*0.10)
overall <- clamp01(base_risk+amplification_weight+distortion_penalty+baseline_delta_penalty)
level <- ifelse(overall>=0.8,"CRITICAL",ifelse(overall>=0.5,"HIGH",ifelse(overall>=0.2,"WARN","STABLE")))
reason <- sprintf("base=%.4f amplification=%.4f distortion=%.4f baseline_delta=%.4f delta_source_type=%s", base_risk, amplification_weight, distortion_penalty, baseline_delta_penalty, delta_source_type)
detail <- json_obj(c(delta_source_type=delta_source_type, dominant=dom, level=level))
exec_sql(sprintf("DELETE FROM unified_reliability_score_day WHERE profile_id='%s' AND dt='%s' AND run_id='%s';",sql_escape(profile_id),sql_escape(dt),sql_escape(run_id)))
exec_sql(sprintf("
INSERT INTO unified_reliability_score_day (
 profile_id,dt,run_id,scenario_name,overall_risk_score,overall_reliability_risk_score,dominant_semantic_risk,
 base_risk_score,amplification_weight,distortion_penalty,baseline_delta_penalty,confidence_weight,confidence_score,
 final_risk_level,risk_level,delta_source_type,score_reason,detail_json
) VALUES (
 '%s','%s','%s','%s',%.10f,%.10f,'%s',
 %.10f,%.10f,%.10f,%.10f,1,%.10f,
 '%s','%s','%s','%s','%s'
);",sql_escape(profile_id),sql_escape(dt),sql_escape(run_id),sql_escape(scenario_name),overall,overall,sql_escape(dom),
base_risk,amplification_weight,distortion_penalty,baseline_delta_penalty,conf,sql_escape(level),sql_escape(level),sql_escape(delta_source_type),sql_escape(reason),sql_escape(detail)))
cat(sprintf("[R_SCORE_COMPLETION] scenario=%s dominant=%s overall=%.6f level=%s delta_source_type=%s\n", scenario_name, dom, overall, level, delta_source_type))
