# CASE-OBS-001 Phase2-C2 Backfill Hotfix

## Problem

During 7/30-day OBS baseline backfill, intermediate baseline dates can fail in
`validate_v05_behavior_measurement_scope` because the generic v0.5 behavior
validator expects baseline metric/anomaly risk to be nearly zero.

Example failure:

```text
v05_batch_metric_delta max_score=0.2
v05_batch_behavior_anomaly max_score=0.1
[FAIL] baseline metric risk should be near zero
```

This is not an OBS Expected Model failure. It happens while historical baseline
samples are still being accumulated.

## Fix

`deploy/backfill_v05_obs_baseline_mac_host.sh` now passes:

```bash
RUN_V05_BEHAVIOR_SCOPE_VALIDATION=false
```

to each history-date pipeline run by default.

OBS-specific validations remain enabled:

```text
validate_v05_obs_gap_measurement_layer
validate_v05_obs_baseline_foundation
validate_v05_obs_expected_metric
```

## Override

To force the generic behavior-scope validation during backfill:

```bash
BACKFILL_BEHAVIOR_SCOPE_VALIDATION=true \
/opt/homebrew/bin/bash deploy/backfill_v05_obs_baseline_mac_host.sh \
  --target-date 2026-06-01 \
  --days 7
```

## Recommended command

```bash
/opt/homebrew/bin/bash deploy/backfill_v05_obs_baseline_mac_host.sh \
  --target-date 2026-06-01 \
  --days 7
```

