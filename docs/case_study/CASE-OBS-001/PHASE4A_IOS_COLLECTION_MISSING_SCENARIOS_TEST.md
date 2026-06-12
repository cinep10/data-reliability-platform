# CASE-OBS-001 Phase4-A iOS App/SDK Version Specific Collection Missing Scenarios

## Purpose

Add three realistic WC collection missing scenarios on top of the completed base case:

1. `source_ios_app_version_collection_missing` — iOS app 5.2.1 tagging initialization failure.
2. `source_ios_sdk_version_collection_missing` — `wc-ios-3.2.1` SDK beacon dispatch failure.
3. `source_ios_purchase_event_collection_missing` — iOS payment/order_complete conversion events are dropped while PV remains comparatively normal.

The implementation is intentionally simulation/collector-rule based. It reuses the existing CASE-OBS-001 measurement, baseline, risk, semantic/action, and visualization chain.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4a_ios_collection_missing_scenarios_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x deploy/apply_phase4a_ios_collection_missing_registry_patch.py
chmod +x pipelines/collect/collector_wc_log_hit_v04.py
chmod +x pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform   python deploy/apply_phase4a_ios_collection_missing_registry_patch.py
```

## Smoke tests

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_app_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_sdk_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Expected validator signals

```text
[IOS_COLLECTION_SCENARIO]
[OK] validate_v05_ios_collection_missing_scenario passed
```

Expected behavior:

- App version case: `ios-app-5.2.1` missing rate >= 0.20 and conversion gap >= 0.20.
- SDK version case: `wc-ios-3.2.1` missing rate >= 0.20 and conversion gap >= 0.20.
- Purchase event case: conversion gap >= 0.20 while PV gap <= 0.12.
- Existing Semantic/Action KB still maps to `Operational Observability Reliability` and `collection_reliability`.
