# CASE-OBS-001 Phase2-C4 Hotfix

## Problem

`build_v05_batch_distribution_analysis.R` failed with:

```text
Error: object 'source_gen_run_id' not found
```

The Phase2-C4 patch made the batch distribution R script read `v05_baseline_science_statistical_evidence_day` with `source_gen_run_id`, but the script did not parse `--source-gen-run-id` and the operation shell did not pass it to this R script.

## Fix

1. Add `--source-gen-run-id` parsing to `pipelines/analytics/r/build_v05_batch_distribution_analysis.R`.
2. Use a safe nullable scope variable, `source_gen_run_id_for_scope`, for `read_scoped_table()`.
3. Pass `--source-gen-run-id "$SOURCE_GEN_RUN_ID"` from `deploy/run_v05_reliability_pipeline_commerce_mac_host.sh` to `build_v05_batch_distribution_analysis.R`.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c4_hotfix_batch_distribution_source_gen.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/analytics/r/build_v05_batch_distribution_analysis.R
```

## Run only failed R step

```bash
Rscript pipelines/analytics/r/build_v05_batch_distribution_analysis.R \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --dt 2026-06-01 \
  --run-id 579 \
  --source-gen-run-id 572 \
  --scenario-name baseline \
  --baseline-dt 2026-06-01 \
  --baseline-mode temporal_baseline \
  --baseline-window 30d
```

Expected:

```text
[OK] build_v05_batch_distribution_analysis ...
```

## Continue pipeline from the next failing step

If only this step failed and previous tables are intact, run the remaining analytics manually:

```bash
Rscript pipelines/analytics/r/build_v05_batch_behavior_anomaly.R \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver --dt 2026-06-01 --run-id 579 --source-gen-run-id 572 \
  --scenario-name baseline --baseline-mode temporal_baseline --baseline-window 30d
```

Or rerun the whole pipeline after applying the patch.
