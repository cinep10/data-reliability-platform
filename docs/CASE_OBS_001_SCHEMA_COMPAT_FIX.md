# CASE-OBS-001 Schema Compatibility Fix

## Problem

Installation failed while creating `v05_wc_collection_reconciliation_day`:

```text
Unknown column 'observability_signal_score' in 'SELECT'
```

The current `v05_observability_measurement_day` table has measurement columns, but not the native semantic/risk columns referenced by the view.

## Fix

This package updates:

- `sql/036_v05_observability_measurement_schema_mariadb.sql`
  - Adds missing columns with idempotent ALTERs:
    - `observability_signal_score`
    - `observability_risk_level`
    - `recommended_semantic_risk`
    - `dominant_observability_signal`
    - compatibility `web_to_canonical_gap_*` columns when missing
- `sql/067_v05_observability_core_absorb_schema_mariadb.sql`
  - Adds missing R analysis compatibility columns:
    - `canonical_observability_gap_score`
    - `collection_completeness_score`
    - `baseline_collection_gap_rate`
    - `baseline_delta_score`
    - `analysis_status`
- `sql/035_v05_wc_collection_reconciliation_view_mariadb.sql`
  - Recreates the view after the table is compatible.

## Apply

```bash
unzip v05_observability_schema_compat_fix.zip
cd v05_observability_schema_compat_fix_pkg
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform bash install_v05_observability_schema_compat_fix.sh
```

## Test

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_case_obs_001_baseline_then_anomaly_test.sh 2026-05-28 0
```

## Expected

- Baseline run collector log should show `runtime_mode=none` and no WC missing options.
- WC anomaly run collector log should show `runtime_mode=wc_collection_missing` and WC missing options.
- `v05_wc_collection_reconciliation_day` should be queryable.
- `build_v05_observability_reliability_analysis.R` should not fail on `canonical_observability_gap_score`.
