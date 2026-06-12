# CASE-OBS-001 Phase2-C1 include-target-date Hotfix

## Problem

Operational shell passed `--include-target-date` as a flag. Python accepted it, but then forwarded it to the R baseline scripts as a value-less flag. The R common CLI parser expects key/value pairs, so the R step failed with:

```text
'names' attribute [14] must be the same length as the vector [13]
```

## Fix

- `deploy/run_v05_reliability_pipeline_commerce_mac_host.sh`
  - passes `--include-target-date true` to the Python orchestrator.
- `pipelines/commerce/observability/build_v05_obs_baseline_foundation.py`
  - accepts both flag style and explicit true/false style.
  - forwards `--include-target-date true` to R.

## Test

```bash
/opt/homebrew/bin/bash \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

Expected:

```text
[STEP 4.12] CASE-OBS-001 Phase2-B gap measurement layer
[STEP 4.13] CASE-OBS-001 Phase2-C1 baseline foundation
[RUN_R] Rscript ... --include-target-date true
[OK] build_v05_obs_baseline_foundation ... compare>0
```
