# CASE-OBS-001 Phase3-A: R Analytics Enhancement + Root Cause Confidence Test

## Purpose

Phase3-A connects the already-built Statistical Reliability Analytics evidence to an operational explanation layer.

The target explanation is no longer only:

```text
collection_gap_rate = 0.21
```

It should become:

```text
app_version_gap_delta = 0.21
z_score = 4.7
historical_percentile = 99.2%
affected_metrics = 4
co_movement_score = high
root_cause_confidence = high

=> Normal variation was exceeded by a multi-metric observability failure concentrated in a specific app/sdk/client/url segment.
```

## New assets

```text
sql/080_v05_observability_interpretation_mariadb.sql
pipelines/commerce/analytics/build_v05_observability_interpretation.R
pipelines/commerce/validation/validate_v05_observability_interpretation.py
```

## Operating shell integration

`deploy/run_v05_reliability_pipeline_commerce_mac_host.sh` now includes:

```text
STEP 6.06
CASE-OBS-001 Phase3-A observability interpretation / root cause confidence
```

This step runs after:

```text
STEP 6.05 build_v05_observability_reliability_analysis.R
```

and before semantic interpretation.

## Reset/truncate integration

The following table is reset by normal reset/truncate scripts:

```text
r_v05_observability_interpretation_day
```

The backfill compaction script preserves it as a decision/interpretation output.

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase3a_obs_interpretation_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x deploy/reset_v05_commerce_pipeline_mac_host.sh
chmod +x deploy/truncate_v05_runtime_tables_mac_host.sh
chmod +x deploy/compact_v05_backfill_runtime_mac_host.sh
chmod +x pipelines/commerce/analytics/build_v05_observability_interpretation.R
chmod +x pipelines/commerce/validation/validate_v05_observability_interpretation.py
```

## One-day smoke

Baseline:

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

WC missing:

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

Expected log:

```text
[STEP 6.06] CASE-OBS-001 Phase3-A observability interpretation / root cause confidence
[OK] build_v05_observability_interpretation ... confidence=...
[OK] validate_v05_observability_interpretation passed
```

## Direct rerun for a known run

```bash
Rscript pipelines/commerce/analytics/build_v05_observability_interpretation.R \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --baseline-window 30d \
  --top-n 20
```

Validation:

```bash
python -m pipelines.commerce.validation.validate_v05_observability_interpretation \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --require-signal \
  --min-confidence 0.20
```

## SQL review

```sql
SELECT root_cause_rank,
       root_cause_dimension,
       root_cause_value,
       segment_concentration,
       affected_metrics,
       propagation_level,
       statistical_severity_level,
       root_cause_confidence,
       confidence_level,
       analysis_status
FROM r_v05_observability_interpretation_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='source_wc_collection_missing'
ORDER BY root_cause_rank
LIMIT 20;
```

```sql
SELECT root_cause_dimension,
       root_cause_value,
       root_cause_confidence,
       affected_metrics,
       propagation_level,
       statistical_severity_level
FROM r_v05_observability_analysis_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='source_wc_collection_missing'
ORDER BY created_at DESC
LIMIT 1;
```

## Completion criteria

- `r_v05_observability_interpretation_day` has rows for each run.
- Baseline may produce `NO_SIGNAL` or low confidence rows.
- `source_wc_collection_missing` should produce at least one `WATCH` or `SIGNAL` row when collection gap exists.
- Top rows expose:
  - `affected_metrics`
  - `propagation_strength` / `propagation_level`
  - `segment_concentration`
  - `root_cause_confidence`
  - `statistical_severity_level`
- `r_v05_observability_analysis_day` is enriched with the top interpretation values.
