# Phase2-C4 Backfill Validation Hotfix

## What changed

1. `validate_v05_statistical_evidence_meaning` now validates `batch_metric_delta` as a history-backed domain.
   - It no longer requires every row in the target run to have `sample_days >= min_sample_days`.
   - It checks aggregated target-date evidence and `v05_batch_metric_delta_history_day`.
   - `observability_expected` remains a reference domain and is excluded from statistical meaning failure.

2. `validate_v05_scenario_sensitivity` no longer uses `rows` as a SQL alias.
   - MariaDB treats `rows` as a problematic alias in this environment.
   - The alias is now `row_count`.

## Operating shell note

`validate_v05_baseline_science_statistical_evidence` is already part of the operating shell at:

- `STEP 4.147` for `batch,observability`
- `STEP 5.1` for `reconciliation`

`validate_v05_statistical_evidence_meaning` and `validate_v05_scenario_sensitivity` should remain backfill/test validators, not one-day operating-shell validators.

## Re-run after applying

```bash
python -m pipelines.commerce.validation.validate_v05_statistical_evidence_meaning \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id 669 \
  --source-gen-run-id 662 \
  --baseline-window 30d \
  --domains batch_metric_delta,observability_expected,reconciliation_measurement \
  --min-sample-days 3
```

```bash
python -m pipelines.commerce.validation.validate_v05_scenario_sensitivity \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --from-date 2026-05-03 \
  --to-date 2026-06-01 \
  --baseline-scenario baseline \
  --anomaly-scenarios source_partial_missing,source_wc_collection_missing \
  --min-anomaly-days 3 \
  --allow-no-sensitivity
```
