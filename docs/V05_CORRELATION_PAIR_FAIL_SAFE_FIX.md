# v0.5 Correlation Pair Fail-safe Fix

## Problem

`r_correlation_anomaly_v04.R` failed with:

```text
Error in combn(names(metric_values), 2, ...): n < m
```

The root cause is that the correlation diagnostic tried to build metric pairs when fewer than two named metric inputs were available. This can happen when source tables are empty, schema-aware reads return no rows, or numeric conversion drops names.

## Fix

- Preserve metric names after numeric conversion.
- Keep zero-valued metrics as valid baseline evidence.
- If fewer than two named metrics exist, write one diagnostic row:
  - `metric_pair = insufficient_metrics`
  - `anomaly_score = 0`
  - `anomaly_status = INSUFFICIENT_METRICS`
- The script exits normally instead of aborting the pipeline.

## Expected Result

Baseline should remain PASS/stable. WC collection missing should produce pair diagnostics when metric deltas exist, and should never stop the pipeline because of insufficient pair inputs.
