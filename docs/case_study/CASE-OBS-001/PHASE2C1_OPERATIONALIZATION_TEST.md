# CASE-OBS-001 Phase2-C1 Operationalization Test

## Purpose

This patch operationalizes OBS Phase2-B/C1 so the Mac Host pipeline no longer requires manual post-run commands.

It adds:

- Pipeline step 4.12: `build_v05_obs_gap_measurement_layer`
- Pipeline step 4.13: `build_v05_obs_baseline_foundation`
- Optional validations
- Reset/truncate coverage for OBS gap and baseline output tables
- R-based baseline statistics/compare to preserve language responsibility boundaries

## Apply Patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c1_operationalization_patch.zip
```

## Run Pipeline

Single-day smoke / current test-room mode:

```bash
/opt/homebrew/bin/bash \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

Expected log snippets:

```text
[STEP 4.12] CASE-OBS-001 Phase2-B gap measurement layer
[OK] build_v05_obs_gap_measurement_layer ... app_rows=14 sdk_rows=6 url_rows=134 client_rows=15 metric_rows=165

[STEP 4.13] CASE-OBS-001 Phase2-C1 baseline foundation
[RUN_R] Rscript pipelines/commerce/analytics/build_v05_obs_baseline_stat_profile.R ...
[RUN_R] Rscript pipelines/commerce/analytics/build_v05_obs_baseline_compare.R ...
[PASS] v05_obs_baseline_compare_day
```

## Manual Validation

```bash
python -m pipelines.commerce.validation.validate_v05_obs_gap_measurement_layer \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --require-native
```

```bash
python -m pipelines.commerce.validation.validate_v05_obs_baseline_foundation \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --baseline-window 30d \
  --baseline-scenario baseline \
  --require-native \
  --allow-low-sample
```

## Operational Flags

Default values are smoke-test friendly.

```bash
RUN_V05_OBS_GAP_MEASUREMENT=true
RUN_V05_OBS_GAP_VALIDATION=true
RUN_V05_OBS_BASELINE_FOUNDATION=true
RUN_V05_OBS_BASELINE_VALIDATION=true
OBS_BASELINE_INCLUDE_TARGET_DATE=true
OBS_BASELINE_ALLOW_LOW_SAMPLE=true
OBS_BASELINE_MIN_SAMPLE_DAYS=3
```

For multi-day baseline operation, consider:

```bash
OBS_BASELINE_INCLUDE_TARGET_DATE=false
OBS_BASELINE_ALLOW_LOW_SAMPLE=false
```

## Reset Policy

Runtime-reset deletes regenerated OBS outputs:

```text
v05_obs_app_version_measurement_day
v05_obs_sdk_version_measurement_day
v05_obs_url_gap_day
v05_obs_client_gap_day
v05_obs_metric_gap_day
v05_obs_baseline_feature_snapshot_day
v05_obs_baseline_stat_profile_day
v05_obs_baseline_compare_day
```

OBS baseline reference is preserved by default:

```text
v05_obs_baseline_reference_day
```

Delete it only with:

```bash
RESET_OBS_BASELINE_REFERENCE=true
```

or in truncate mode:

```bash
--preserve-obs-baseline-reference false
```

## Language Boundary

- SQL: table persistence only.
- Python: schema apply, feature snapshot materialization, orchestration.
- R: rolling baseline, same-weekday baseline, statistics, z-score, severity, compare.
