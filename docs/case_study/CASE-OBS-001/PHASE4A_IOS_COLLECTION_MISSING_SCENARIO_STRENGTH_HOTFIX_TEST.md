# CASE-OBS-001 Phase4-A iOS Collection Missing Scenario Strength Hotfix Test

## Purpose

Fix the first Phase4-A smoke failure for `source_ios_app_version_collection_missing`.

The previous targeted rule only dropped checkout/payment/order_complete rows for `ios-app-5.2.1`, so `conversion_gap` was visible but overall `app_missing_rate` stayed around 8.5%, below the validator threshold of 20%.

This hotfix separates two validation moments:

1. Step 4.121: measurement-only validation after the gap layer.
2. Step 6.061: interpretation-aware validation after OBS interpretation.

## Expected scenario behavior

### source_ios_app_version_collection_missing

- Target: `ios_app` + `ios-app-5.2.1`
- Rule: app-version-wide WC collection missing
- Expected: `app_missing_rate >= 0.20`, `conversion_gap >= 0.20`

### source_ios_sdk_version_collection_missing

- Target: `ios_app` + `wc-ios-3.2.1`
- Rule: SDK-version-wide WC collection missing
- Expected: `sdk_missing_rate >= 0.20`, `conversion_gap >= 0.20`

### source_ios_purchase_event_collection_missing

- Target: `ios_app` conversion/payment event path
- Rule: conversion-focused WC collection missing
- Expected: `conversion_gap >= 0.20`, PV gap remains bounded

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4a_ios_scenario_strength_hotfix.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x deploy/apply_phase4a_ios_collection_missing_registry_patch.py
chmod +x pipelines/collect/collector_wc_log_hit_v04.py
chmod +x pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4a_ios_collection_missing_registry_patch.py
```

## Test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_app_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_sdk_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Expected logs

Step 4.121 should pass measurement validation. If OBS interpretation has not been built yet, it should log a deferred interpretation check rather than fail.

```text
[INFO] interpretation rows not available yet; ... interpretation check deferred until Step 6.061
[OK] validate_v05_ios_collection_missing_scenario passed
```

Step 6.061 should run after OBS interpretation and require the expected app/sdk signal.

```text
[STEP 6.061] CASE-OBS-001 Phase4-A iOS ... interpretation validation
[OK] validate_v05_ios_collection_missing_scenario passed
```
