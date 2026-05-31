# v05 distribution builder schema-aware fix

Fixes:
- `Unknown column baseline_std in SELECT` by removing static `COALESCE(baseline_ratio_std, baseline_std, 0)` SQL.
- Uses `information_schema` to select only existing baseline std columns.
- Keeps baseline scenario from becoming `BASELINE_MISSING_REVIEW`; it becomes `BASELINE_SELF_REFERENCE` before snapshot exists.
- Collector baseline log shows `wc_missing_rates=not_applied` when runtime mode is `none`.

Run:

```bash
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform bash install_v05_distribution_builder_schema_aware_fix.sh
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_case_obs_001_baseline_then_anomaly_test.sh 2026-05-28 0
```
