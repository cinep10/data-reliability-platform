# CASE-OBS-001 Phase2-C4 Statistical Evidence Interface Verification

## Purpose

This verification separates two questions:

1. Does `build_v05_reliability_analysis.R` actually read `v05_baseline_science_statistical_evidence_day` with `evidence_domain='reconciliation_measurement'`?
2. Does the current evidence have enough baseline history to be statistically meaningful?

A baseline smoke can pass the pipeline while still being statistically low-sample. That is expected when `sample_days=1`.

## One-day smoke verification

```bash
/opt/homebrew/bin/bash \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

Expected additional reliability log after this patch:

```text
[build_v05_reliability_analysis.R] OK ... stat=0.000000 stat_raw=0.000000 reflected=1 stat_rows=6 sample_days=1..1 sig=stable ...
```

`reflected=1` and `stat_rows=6` prove that the v0.5 reliability analysis read reconciliation statistical evidence. In a baseline run, effective risk contribution remains zero to prevent false positives.

## Validate reliability interface reflection

Use the printed `RUN_ID` and `SOURCE_GEN_RUN_ID` from the smoke log.

```bash
python -m pipelines.commerce.validation.validate_v05_reliability_statistical_evidence_interface \
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
  --allow-baseline-suppression
```

Expected:

```text
[EVIDENCE] domain=reconciliation_measurement rows=6 ...
[RELIABILITY] reflected=1 rows=6 raw=... effective=0.000000 ...
[OK] validate_v05_reliability_statistical_evidence_interface passed
```

## Validate statistical meaning

For the current 1-day smoke, this should be run with `--allow-low-sample`.

```bash
python -m pipelines.commerce.validation.validate_v05_statistical_evidence_meaning \
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
  --domains batch_metric_delta,observability_expected,reconciliation_measurement \
  --min-sample-days 3 \
  --allow-low-sample
```

Expected with 1-day baseline:

```text
[MEANING] ... meaningful=false
[WARN] ... not statistically meaningful yet ...
[OK] validate_v05_statistical_evidence_meaning passed with allow-low-sample
```

After 7-day or 30-day backfill, run the same command without `--allow-low-sample`. At that point, it should pass only if sample days and variance are sufficient.

## SQL checks

```sql
SELECT evidence_domain, COUNT(*) rows,
       MIN(sample_days) min_days,
       MAX(sample_days) max_days,
       MAX(statistical_score) max_score,
       MAX(historical_percentile) max_percentile
FROM v05_baseline_science_statistical_evidence_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND run_id=<RUN_ID>
  AND source_gen_run_id=<SOURCE_GEN_RUN_ID>
GROUP BY evidence_domain;
```

```sql
SELECT statistical_evidence_reflected,
       statistical_evidence_row_count,
       statistical_evidence_raw_score,
       statistical_evidence_effective_score,
       statistical_evidence_min_sample_days,
       statistical_evidence_max_sample_days,
       statistical_significance
FROM reliability_analysis_result_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND run_id=<RUN_ID>
  AND source_gen_run_id=<SOURCE_GEN_RUN_ID>;
```
