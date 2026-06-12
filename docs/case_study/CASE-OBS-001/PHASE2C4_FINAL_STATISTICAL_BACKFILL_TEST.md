# CASE-OBS-001 Phase2-C4 Final Statistical Reliability Analytics Backfill Test

## Purpose

Finalize Phase2-C4 by validating the statistical domains with a scenario-calendar backfill while keeping disk usage under control.

Key domain policy:

- `batch_metric_delta` is a statistical domain only after it is materialized into `v05_batch_metric_delta_history_day`.
- `reconciliation_measurement` is a statistical domain and should have real `sample_days` after 7d/30d backfill.
- `observability_expected` is a reference domain. It is created and validated as an interface, but it is not a statistical meaning failure target.

## Script roles

### `backfill_v05_obs_baseline_mac_host.sh`

Use this for baseline-only OBS reference refresh.

It is for:

- OBS baseline foundation
- expected metric
- threshold calibration
- target-date reference refresh

It should not be used for anomaly sensitivity testing.

### `backfill_v05_statistical_reliability_mac_host.sh`

Use this for Phase2-C4 final validation.

It uses a scenario calendar, not `all scenarios per day`.

Example 7-day calendar:

```text
baseline
baseline
source_partial_missing
source_wc_collection_missing
source_partial_missing
baseline
baseline
```

This is required because running all scenarios on the same date does not create a meaningful time series.

### `compact_v05_backfill_runtime_mac_host.sh`

This script is intentionally destructive for heavy runtime tables.

It deletes after each daily scenario run:

```text
source files
source lineage/catalog rows
raw/stage/canonical rows
pipeline_run_registry / pipeline_run_control / source_generation_run
stream/replay/operational detail rows
measurement detail rows
v0.4 batch delta/anomaly daily rows after C4 history/evidence has been written
```

It preserves:

```text
v05_baseline_science_statistical_evidence_day
v05_batch_metric_delta_history_day
v05_obs_baseline_* / v05_obs_expected_metric_day / v05_obs_threshold_calibration_day
v05_reconciliation_measurement_day
reliability_analysis_result_day_v05
semantic_interpretation_day_v05
unified_reliability_score_day_v05
action_recommendation_day_v05
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c4_backfill_compaction_test_patch.zip
chmod +x deploy/backfill_v05_statistical_reliability_mac_host.sh
chmod +x deploy/compact_v05_backfill_runtime_mac_host.sh
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
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

Expected compaction log after each day:

```text
[COMPACT_DELETE] canonical_behavior_events ...
[COMPACT_DELETE] canonical_events ...
[COMPACT_DELETE] pipeline_run_registry ...
[COMPACT_DELETE] v05_batch_metric_delta_day ...
[COMPACT_VERIFY] heavy table counts after compaction
  canonical_behavior_events=0
  canonical_events=0
  stg_webserver_log_hit=0
  stg_wc_log_hit=0
  pipeline_run_registry=0
  v05_batch_metric_delta_day=0
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

Resolve the target baseline run from the log, then run:

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

Expected:

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

### Statistical evidence summary

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
```

### Batch metric delta history

```sql
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

### Heavy runtime compaction check

```sql
SELECT 'canonical_behavior_events' AS table_name, COUNT(*) AS cnt
FROM canonical_behavior_events
WHERE profile_id='commerce_deliver' AND target_date BETWEEN '2026-05-03' AND '2026-06-01'
UNION ALL
SELECT 'canonical_events', COUNT(*)
FROM canonical_events
WHERE profile_id='commerce_deliver' AND dt BETWEEN '2026-05-03' AND '2026-06-01'
UNION ALL
SELECT 'stg_webserver_log_hit', COUNT(*)
FROM stg_webserver_log_hit
WHERE profile_id='commerce_deliver' AND target_date BETWEEN '2026-05-03' AND '2026-06-01'
UNION ALL
SELECT 'stg_wc_log_hit', COUNT(*)
FROM stg_wc_log_hit
WHERE profile_id='commerce_deliver' AND target_date BETWEEN '2026-05-03' AND '2026-06-01'
UNION ALL
SELECT 'pipeline_run_registry', COUNT(*)
FROM pipeline_run_registry
WHERE profile_id='commerce_deliver' AND dt_from BETWEEN '2026-05-03' AND '2026-06-01';
```

Expected: these counts should be `0` or near `0` after compacted backfill, while the statistical/evidence/decision tables remain populated.

## Completion criteria

- `batch_metric_delta` has `sample_days >= 3` on target baseline.
- `reconciliation_measurement` has `sample_days >= 3` on target baseline.
- `observability_expected` is reported as `REFERENCE`, not failed.
- Scenario sensitivity validation detects anomaly days.
- Heavy source/raw/stage/canonical/pipeline runtime rows are deleted by compaction.
- Statistical/baseline/reliability/semantic/risk/action outputs remain.
