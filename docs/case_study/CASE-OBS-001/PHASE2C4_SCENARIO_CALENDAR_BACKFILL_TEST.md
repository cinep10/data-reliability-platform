# CASE-OBS-001 Phase2-C4 Scenario Calendar Backfill Test

## Why two backfill scripts exist

### `backfill_v05_obs_baseline_mac_host.sh`

Purpose: OBS Baseline Science reference refresh.

Use it when the goal is only to build or refresh baseline/expected/threshold outputs for a baseline target date.

It is baseline-oriented and should not be used as the main statistical anomaly-response test runner.

### `backfill_v05_statistical_reliability_mac_host.sh`

Purpose: Statistical Reliability Analytics test runner.

Use it when the goal is to test whether Baseline Science evidence reacts meaningfully to anomaly days and whether the final baseline target date still remains stable.

This script uses a scenario calendar: one scenario per date. It does not run baseline, source_partial_missing, and source_wc_collection_missing on the same date because that does not create a meaningful time-series distribution.

## Default scenario calendar

For 7 days ending at `2026-06-01`, the default plan is:

```text
2026-05-26 baseline
2026-05-27 baseline
2026-05-28 source_partial_missing
2026-05-29 source_wc_collection_missing
2026-05-30 source_partial_missing
2026-05-31 baseline
2026-06-01 baseline
```

For 30 days, the same principle is used:

```text
early days: baseline
middle 3 days: anomaly scenarios
final days: baseline
last target date: baseline
```

This gives the baseline enough normal days, injects observable abnormal days in the middle, and keeps the final target date clean for final reference validation.

## 7-day run

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

## 30-day run

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

## Custom plan

```bash
/opt/homebrew/bin/bash deploy/backfill_v05_statistical_reliability_mac_host.sh \
  --from-date 2026-05-26 \
  --to-date 2026-06-01 \
  --plan 2026-05-26:baseline,2026-05-27:baseline,2026-05-28:source_partial_missing,2026-05-29:source_wc_collection_missing,2026-05-30:source_partial_missing,2026-05-31:baseline,2026-06-01:baseline
```

## Compaction policy

After each daily run, `compact_v05_backfill_runtime_mac_host.sh` removes heavy runtime/source data:

```text
source files
stg_webserver_log_hit
stg_wc_log_hit
event_log_raw
canonical_events
canonical_behavior_events
canonical_transaction_events
canonical_state_events
mapping detail rows
stream replay/detail rows
```

It preserves statistical and decision evidence tables:

```text
v05_baseline_science_statistical_evidence_day
v05_obs_baseline_* tables
v05_obs_expected_metric_day
v05_obs_threshold_calibration_day
v05_batch_metric_delta_day
v05_reconciliation_measurement_day
reliability_analysis_result_day_v05
semantic_interpretation_day_v05
unified_reliability_score_day_v05
action_recommendation_day_v05
```

## PASS criteria

For 7-day validation:

```text
scenario calendar is printed
one scenario is executed per date
middle anomaly days exist
last target date is baseline
statistical evidence rows exist for expected dates
batch_metric_delta and reconciliation_measurement domains exist
low-sample is allowed only for early 7-day tests
```

For 30-day validation:

```text
--allow-low-sample false should pass
sample_days should exceed the configured threshold
anomaly days should show non-zero statistical movement if anomaly measurement creates measurable deltas
final baseline should remain stable or suppressed
```
