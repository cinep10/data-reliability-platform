# CASE-OBS-001 Phase2-C4 Final Statistical Reliability Analytics Test

## Purpose

Finalize Phase2-C4 by separating statistical domains from reference domains.

- `batch_metric_delta` becomes a true time-series domain by deriving history from `v05_batch_metric_delta_day` and materializing `v05_batch_metric_delta_history_day`.
- `reconciliation_measurement` remains a true time-series statistical domain.
- `observability_expected` is treated as a reference domain, not a statistical meaning domain.

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c4_final_statistical_analytics_patch.zip
chmod +x deploy/backfill_v05_statistical_reliability_mac_host.sh
chmod +x deploy/compact_v05_backfill_runtime_mac_host.sh
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/analytics/build_v05_baseline_science_statistical_evidence.R
chmod +x pipelines/commerce/validation/validate_v05_statistical_evidence_meaning.py
chmod +x pipelines/commerce/validation/validate_v05_scenario_sensitivity.py
```

## 7-day scenario-calendar test

```bash
/opt/homebrew/bin/bash deploy/backfill_v05_statistical_reliability_mac_host.sh \
  --target-date 2026-06-01 \
  --days 7 \
  --anomaly-days 3 \
  --anomaly-scenarios source_partial_missing,source_wc_collection_missing,source_partial_missing \
  --compact-after-each-run true \
  --remove-source-files true \
  --allow-low-sample true
```

Expected calendar:

```text
baseline
baseline
source_partial_missing
source_wc_collection_missing
source_partial_missing
baseline
baseline
```

## 30-day scenario-calendar test

```bash
/opt/homebrew/bin/bash deploy/backfill_v05_statistical_reliability_mac_host.sh \
  --target-date 2026-06-01 \
  --days 30 \
  --anomaly-days 3 \
  --anomaly-scenarios source_partial_missing,source_wc_collection_missing,source_partial_missing \
  --compact-after-each-run true \
  --remove-source-files true \
  --allow-low-sample false
```

## Direct meaning validation

```bash
python -m pipelines.commerce.validation.validate_v05_statistical_evidence_meaning \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --baseline-window 30d \
  --domains batch_metric_delta,observability_expected,reconciliation_measurement \
  --min-sample-days 3
```

Expected behavior:

```text
[MEANING] domain=batch_metric_delta ... meaningful=true
[REFERENCE] domain=observability_expected ... excluded_from_statistical_meaning
[MEANING] domain=reconciliation_measurement ... meaningful=true
[OK] validate_v05_statistical_evidence_meaning passed
```

## Scenario sensitivity validation

```bash
python -m pipelines.commerce.validation.validate_v05_scenario_sensitivity \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --from-date 2026-05-03 \
  --to-date 2026-06-01 \
  --baseline-scenario baseline \
  --anomaly-scenarios source_partial_missing,source_wc_collection_missing \
  --min-anomaly-days 3
```

## SQL checks

```sql
SELECT evidence_domain,
       scenario_name,
       COUNT(*) AS row_count,
       MIN(sample_days) AS min_sample_days,
       MAX(sample_days) AS max_sample_days,
       MAX(ABS(z_score)) AS max_abs_z,
       MAX(statistical_score) AS max_score
FROM v05_baseline_science_statistical_evidence_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
GROUP BY evidence_domain, scenario_name
ORDER BY evidence_domain, scenario_name;

SELECT metric_scope, metric_name,
       COUNT(DISTINCT history_date) AS history_days,
       AVG(risk_score) AS avg_risk_score,
       STDDEV_SAMP(risk_score) AS sd_risk_score
FROM v05_batch_metric_delta_history_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
GROUP BY metric_scope, metric_name
ORDER BY metric_scope, metric_name;
```

## Completion criteria

- `batch_metric_delta` has `sample_days >= 3` on target baseline.
- `reconciliation_measurement` has `sample_days >= 3` on target baseline.
- `observability_expected` is reported as `REFERENCE`, not failed.
- Scenario sensitivity validation detects anomaly days.
- Heavy raw/canonical/runtime rows are compacted while statistical/baseline/risk/action outputs remain.
