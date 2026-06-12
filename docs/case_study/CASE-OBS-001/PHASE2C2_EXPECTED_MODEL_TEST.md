# CASE-OBS-001 Phase2-C2: Baseline History + Expected Model v1 Test Guide

## Scope

This patch adds and stabilizes:

1. 7-day / 30-day OBS baseline backfill runner
2. `v05_obs_expected_metric_day`
3. Rule-based expected model v1
4. URL / Client / SDK baseline quality fields
5. Operational validation for expected metrics

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c2_expected_model_repatch.zip
chmod +x deploy/backfill_v05_obs_baseline_mac_host.sh
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x deploy/reset_v05_commerce_pipeline_mac_host.sh
chmod +x deploy/truncate_v05_runtime_tables_mac_host.sh
```

## One-day smoke

```bash
/opt/homebrew/bin/bash \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

Expected log:

```text
[STEP 4.14] CASE-OBS-001 Phase2-C2 expected metric model v1
[OK] build_v05_obs_expected_metric rows=...
[OK] validate_v05_obs_expected_metric passed
```

## 7-day backfill

```bash
/opt/homebrew/bin/bash \
  deploy/backfill_v05_obs_baseline_mac_host.sh \
  --target-date 2026-06-01 \
  --days 7
```

Default behavior:

- Runs baseline pipeline for history dates.
- Skips target pipeline if target OBS gap rows already exist.
- Resolves the latest target-date `run_id/source_gen_run_id` from `v05_obs_metric_gap_day`.
- Refreshes target-date Baseline Foundation and Expected Model using accumulated history.
- Validates target-date expected metrics using target-date lineage, not the previous day's lineage.

## 30-day backfill

```bash
/opt/homebrew/bin/bash \
  deploy/backfill_v05_obs_baseline_mac_host.sh \
  --target-date 2026-06-01 \
  --days 30
```

## Force target pipeline rerun

Use this only when target-date source/canonical/gap rows should be regenerated.

```bash
/opt/homebrew/bin/bash \
  deploy/backfill_v05_obs_baseline_mac_host.sh \
  --target-date 2026-06-01 \
  --days 7 \
  --rerun-target-pipeline true
```

## Manual validation

After backfill, use the target lineage printed by the script:

```bash
python -m pipelines.commerce.validation.validate_v05_obs_expected_metric \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id <TARGET_RUN_ID> \
  --source-gen-run-id <TARGET_SOURCE_GEN_RUN_ID> \
  --baseline-window 30d \
  --require-native \
  --allow-low-sample
```

## Notes

- If a backfill run is interrupted with `Ctrl+C`, it is not a validation failure. Rerun the backfill script; scoped reset will clean the affected date and rebuild it.
- Intermediate date validation uses that date's run/source lineage inside the normal operation script.
- Final target validation must use the target date's latest lineage. The repatched backfill script now resolves this automatically.
