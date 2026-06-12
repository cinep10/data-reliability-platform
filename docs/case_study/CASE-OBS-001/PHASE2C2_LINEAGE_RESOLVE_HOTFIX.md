# CASE-OBS-001 Phase2-C2 Backfill Lineage Resolve Hotfix

## Problem

The backfill runner could finish the target-date pipeline successfully but still fail with:

```text
[ERROR] unable to resolve target lineage for 2026-06-01 after pipeline run
```

The previous lineage resolver depended on a single OBS measurement table/query. If the target row was missing from that table, had nullable scenario metadata, or the query shape did not match the current schema, the runner could not resolve `run_id` and `source_gen_run_id` even though the final pipeline log printed them.

## Fix

`deploy/backfill_v05_obs_baseline_mac_host.sh` now resolves target lineage using a schema-aware Python resolver across multiple tables:

1. `v05_obs_metric_gap_day`
2. `v05_obs_app_version_measurement_day`
3. `v05_obs_sdk_version_measurement_day`
4. `v05_obs_baseline_feature_snapshot_day`
5. `v05_obs_expected_metric_day`
6. `canonical_behavior_events`
7. `v05_runtime_evidence_day`
8. `v05_reconciliation_measurement_day`

The resolver tolerates nullable/blank `scenario_name` and chooses the latest `run_id/source_gen_run_id` for the target date.

## Test

```bash
/opt/homebrew/bin/bash deploy/backfill_v05_obs_baseline_mac_host.sh \
  --target-date 2026-06-01 \
  --days 7
```

Expected log:

```text
[OBS_BACKFILL] target lineage target_date=2026-06-01 run_id=<latest> source_gen_run_id=<latest>
[OBS_BACKFILL] refresh target OBS baseline foundation and expected metric using accumulated history
[OK] validate_v05_obs_expected_metric passed
[DONE] CASE-OBS-001 Phase2-C2 baseline history backfill completed
```
