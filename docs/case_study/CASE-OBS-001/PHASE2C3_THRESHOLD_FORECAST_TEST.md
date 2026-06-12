# CASE-OBS-001 Phase2-C3 Threshold Calibration + Forecast Interface Test

## Scope

Phase2-C3 runs after Phase2-C2 Expected Metric Model v1.

Implemented scope:

1. `v05_obs_threshold_calibration_day`
2. R-based threshold calibration
3. threshold validation
4. `v05_obs_forecast_metric_day`
5. forecast interface validation
6. operation shell / reset / truncate / backfill integration

Forecast is interface-only. Actual ML model training is intentionally out of scope.

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c3_threshold_forecast_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x deploy/backfill_v05_obs_baseline_mac_host.sh
chmod +x deploy/reset_v05_commerce_pipeline_mac_host.sh
chmod +x deploy/truncate_v05_runtime_tables_mac_host.sh
chmod +x pipelines/commerce/analytics/build_v05_obs_threshold_calibration.R
```

## One-day smoke

```bash
/opt/homebrew/bin/bash \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

Expected log markers:

```text
[STEP 4.14] CASE-OBS-001 Phase2-C2 expected metric model v1
[STEP 4.145] CASE-OBS-001 Phase2-C3 threshold calibration
[OK] build_v05_obs_threshold_calibration rows=...
[OK] validate_v05_obs_threshold_calibration passed
[STEP 4.146] CASE-OBS-001 Phase2-C3 forecast interface validation
[OK] validate_v05_obs_forecast_interface passed
```

## 7-day backfill

```bash
/opt/homebrew/bin/bash \
  deploy/backfill_v05_obs_baseline_mac_host.sh \
  --target-date 2026-06-01 \
  --days 7
```

The backfill runner refreshes target-date baseline foundation, expected metric, threshold calibration, and forecast interface validation using the resolved target-date lineage.

## Manual target-date refresh only

Use this when the 7-day pipeline already finished and only the final target refresh needs to be rerun.

```bash
RUN_ID=539
SOURCE_GEN_RUN_ID=532

python -m pipelines.commerce.observability.build_v05_obs_baseline_foundation \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver --target-date 2026-06-01 --scenario-name baseline \
  --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" \
  --baseline-window 30d --baseline-scenario baseline --min-sample-days 3 \
  --truncate-target --apply-schema --rscript-bin Rscript --include-target-date true

Rscript pipelines/commerce/analytics/build_v05_obs_expected_metric.R \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver --target-date 2026-06-01 --scenario-name baseline \
  --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" \
  --baseline-window 30d --baseline-scenario baseline --recent-days 7 --min-sample-days 3

Rscript pipelines/commerce/analytics/build_v05_obs_threshold_calibration.R \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver --target-date 2026-06-01 --scenario-name baseline \
  --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" \
  --baseline-window 30d --baseline-scenario baseline --min-sample-days 3

python -m pipelines.commerce.validation.validate_v05_obs_threshold_calibration \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver --target-date 2026-06-01 --scenario-name baseline \
  --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" \
  --baseline-window 30d --require-native --allow-low-sample

python -m pipelines.commerce.validation.validate_v05_obs_forecast_interface \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver --target-date 2026-06-01 --scenario-name baseline \
  --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" \
  --baseline-window 30d
```

## DB checks

```sql
SELECT dimension_type, metric_name, COUNT(*) AS rows,
       MIN(sample_days) AS min_days,
       MAX(sample_days) AS max_days,
       MIN(watch_threshold) AS min_watch,
       MIN(warning_threshold) AS min_warning,
       MIN(critical_threshold) AS min_critical
FROM v05_obs_threshold_calibration_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
GROUP BY dimension_type, metric_name
ORDER BY dimension_type, metric_name;
```

```sql
SELECT calibration_status, dimension_policy, COUNT(*) AS rows
FROM v05_obs_threshold_calibration_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
GROUP BY calibration_status, dimension_policy
ORDER BY calibration_status, dimension_policy;
```

```sql
SELECT COUNT(*) AS forecast_rows
FROM v05_obs_forecast_metric_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01';
```

Forecast rows may be zero in Phase2-C3 because forecast is interface-only.

## PASS criteria

1. `v05_obs_threshold_calibration_day` exists and has rows.
2. Dimensions include `all`, `app_platform`, `app_version`, `app_sdk`, `sdk_version`, `client`, and `url`.
3. `watch_threshold <= warning_threshold <= critical_threshold`.
4. Native expected metrics are available for calibration.
5. `v05_obs_forecast_metric_day` exists with required interface columns.
6. Forecast validation passes even when no ML forecast rows exist.
