#!/usr/bin/env Rscript
source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))
args <- commandArgs(trailingOnly = TRUE)
con <- connect_db(args)
 on.exit(DBI::dbDisconnect(con), add = TRUE)
profile_id <- arg_value(args, "--profile-id")
 dt <- arg_value(args, "--dt")
 run_id <- as.integer(arg_value(args, "--run-id", "0"))
 effective_from <- arg_value(args, "--effective-from", dt)
dist <- read_scoped_table(con, "r_risk_metric_distribution_day", profile_id, dt, run_id, NULL, NULL)
if (nrow(dist) < 1) dist <- data.frame(metric_name="NOT_APPLICABLE", p95_value=0, p99_value=0, mean_value=0, sd_value=0)
if (table_exists(con, "r_risk_threshold_profile_v2")) execute_sql(con, "DELETE FROM r_risk_threshold_profile_v2 WHERE profile_id = ?", list(profile_id))
for (idx in seq_len(nrow(dist))) {
  insert_schema_aware(con, "r_risk_threshold_profile_v2", list(profile_id=profile_id, effective_from=effective_from, run_id=run_id, metric_name=as.character(dist$metric_name[[idx]]), warn_threshold=safe_number(dist$p95_value[[idx]]), critical_threshold=safe_number(dist$p99_value[[idx]]), baseline_mean=safe_number(dist$mean_value[[idx]]), baseline_sd=safe_number(dist$sd_value[[idx]]), threshold_method="r_p95_p99_reengineered_v1", source_distribution_dt=dt))
}

# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(sprintf("[R_OP_THRESHOLD_REENGINEERED_V1] rows=%d\n", nrow(dist)))
