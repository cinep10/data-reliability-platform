# CASE-OBS-001 Phase2-C1 Baseline Foundation Test Guide

## Scope

This patch adds an OBS-only Baseline Science Foundation layer on top of the Phase2-B Gap Measurement outputs.

It does not modify the v0.5 core baseline tables:

- `v05_baseline_metric_snapshot_day`
- `v05_baseline_distribution_snapshot_day`
- `v05_baseline_reference_run_day`

## New tables

- `v05_obs_baseline_reference_day`
- `v05_obs_baseline_feature_snapshot_day`
- `v05_obs_baseline_stat_profile_day`
- `v05_obs_baseline_compare_day`

## Required prerequisite

Phase2-B Gap Measurement must already be built.

Example confirmed Phase2-B command:

```bash
python -m pipelines.commerce.observability.build_v05_obs_gap_measurement_layer \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id 518 \
  --source-gen-run-id 513 \
  --truncate-target \
  --apply-schema
```

## Apply patch by zip

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c1_baseline_foundation_patch.zip
```

## Build Baseline Foundation

For a one-day smoke test, use `--include-target-date` and `--allow-low-sample` in validation.

```bash
python -m pipelines.commerce.observability.build_v05_obs_baseline_foundation \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id 518 \
  --source-gen-run-id 513 \
  --baseline-window 30d \
  --baseline-scenario baseline \
  --include-target-date \
  --truncate-target \
  --apply-schema
```

## Validate Baseline Foundation

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
  --run-id 518 \
  --source-gen-run-id 513 \
  --baseline-window 30d \
  --baseline-scenario baseline \
  --require-native \
  --allow-low-sample
```

## Expected smoke-test result

- `v05_obs_baseline_reference_day`: PASS
- `v05_obs_baseline_feature_snapshot_day`: PASS
- `v05_obs_baseline_stat_profile_day`: PASS
- `v05_obs_baseline_compare_day`: PASS
- native baseline features present: `ios_app/android_app`
- baseline compare severity should remain `normal` for baseline scenario when the target date seeds the baseline.

## Production-style usage

After multiple baseline days exist, remove `--include-target-date` and remove `--allow-low-sample`.

```bash
python -m pipelines.commerce.observability.build_v05_obs_baseline_foundation \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-15 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --baseline-window 30d \
  --baseline-scenario baseline \
  --truncate-target \
  --apply-schema
```

## Design note

Phase2-C1 intentionally builds baseline features from the Phase2-B measurement tables:

- `v05_obs_app_version_measurement_day`
- `v05_obs_sdk_version_measurement_day`
- `v05_obs_url_gap_day`
- `v05_obs_client_gap_day`
- `v05_obs_metric_gap_day`

The normalized long-format feature table is the foundation for later:

- Expected Model
- ML Forecast interface
- Statistical Reliability Analytics
- Visualization
- Risk Score Breakdown
