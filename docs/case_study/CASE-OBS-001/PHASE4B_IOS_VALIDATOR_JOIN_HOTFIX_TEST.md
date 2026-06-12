# CASE-OBS-001 Phase4-B iOS Targeted Validator Join Hotfix Test

## Purpose

Fix `validate_v05_ios_collection_missing_scenario.py` when validating targeted iOS scenarios against the current `stg_wc_log_hit` schema.

Current schema uses:

```text
stg_wc_log_hit.wc_log_id
```

as the primary key. It does **not** have `stg_wc_log_hit.id`.

Therefore this validation query is invalid:

```sql
LEFT JOIN stg_wc_log_hit w ON w.id = s.id
```

The validator now uses independent aggregate counts with equivalent predicates:

```text
targeted_page_rows    = matching rows in stg_webserver_log_hit
targeted_wc_rows      = matching rows in stg_wc_log_hit
targeted_missing_rows = targeted_page_rows - targeted_wc_rows
```

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_ios_validator_targeted_counts_hotfix.zip
chmod +x pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
python -m py_compile pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
```

## Re-test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_app_version_collection_missing 0
```

Expected validator output:

```text
[IOS_COLLECTION_SCENARIO]
targeted_page_rows > 0
targeted_wc_rows >= 0
targeted_missing_rows > 0
[OK] validate_v05_ios_collection_missing_scenario passed
```

## Completion Criteria

- No `Unknown column 'w.id'` error.
- `--require-targeted-page-rows` validates with aggregate counts.
- Targeted app/sdk/purchase event scenarios continue to validate missing-rate and conversion-gap thresholds.
