#!/usr/bin/env Rscript
source(file.path(getwd(), "pipelines/analytics/r/r_baseline_common_v05.R"))
args <- commandArgs(trailingOnly = TRUE)
con <- connect_db(args)
 on.exit(DBI::dbDisconnect(con), add = TRUE)
profile_id <- arg_value(args, "--profile-id")
 dt <- arg_value(args, "--dt")
 run_id <- as.integer(arg_value(args, "--run-id", "0"))
source_table <- "measurement_operational_day"
operational <- read_scoped_table(con, source_table, profile_id, dt, run_id, NULL, NULL)
if (nrow(operational) < 1) { operational <- data.frame(NOT_APPLICABLE = 0)
 source_table <- "NOT_APPLICABLE" }
metrics <- intersect(c("throughput_per_minute", "lag_p50_ms", "lag_p95_ms", "lag_max_ms", "availability_ratio", "processed_count", "event_count", "NOT_APPLICABLE"), names(operational))

# ------------------------------------------------------------------
# Save Result
# ------------------------------------------------------------------

delete_scoped_rows(con, "r_risk_metric_distribution_day", profile_id, dt, run_id, NULL, NULL)
for (metric in metrics) {
  values <- safe_number(operational[[metric]])
  if (length(values) < 1) values <- 0
  insert_schema_aware(con, "r_risk_metric_distribution_day", list(profile_id=profile_id, dt=dt, run_id=run_id, metric_name=metric, source_table=source_table, sample_count=length(values), mean_value=mean(values), sd_value=ifelse(length(values)>1, sd(values), 0), min_value=min(values), p50_value=as.numeric(quantile(values, .50)), p75_value=as.numeric(quantile(values, .75)), p90_value=as.numeric(quantile(values, .90)), p95_value=as.numeric(quantile(values, .95)), p99_value=as.numeric(quantile(values, .99)), max_value=max(values)))
}

# ------------------------------------------------------------------
# Console Output
# ------------------------------------------------------------------

cat(sprintf("[R_OP_DISTRIBUTION_REENGINEERED_V1] source=%s metrics=%d\n", source_table, length(metrics)))
