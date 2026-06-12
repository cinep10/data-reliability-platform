# CASE-OBS-001 Phase2-C3 Threshold Calibration Hotfix

## Problem

`build_v05_obs_threshold_calibration.R` failed with:

```text
Error: Cannot use named parameters for anonymous placeholders
```

The script used anonymous `?` placeholders while calling DBI functions with the named `params=` argument. In the Mac mini RMariaDB runtime this can fail.

## Fix

Use explicit positional binding:

```r
res <- dbSendQuery(con, sql)
dbBind(res, params)
dbFetch(res)
```

and for write statements:

```r
res <- dbSendStatement(con, sql)
dbBind(res, params)
dbGetRowsAffected(res)
```

## Test

Run the pipeline again:

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 baseline 0
```

Or only rerun the threshold step with the latest lineage shown in the previous run log:

```bash
Rscript pipelines/commerce/analytics/build_v05_obs_threshold_calibration.R \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id 569 \
  --source-gen-run-id 562 \
  --baseline-window 30d \
  --baseline-scenario baseline \
  --min-sample-days 3
```

Expected:

```text
[OK] build_v05_obs_threshold_calibration rows=...
```
