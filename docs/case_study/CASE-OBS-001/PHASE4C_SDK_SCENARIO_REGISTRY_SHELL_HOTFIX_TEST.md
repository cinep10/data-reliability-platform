# CASE-OBS-001 Phase4-C SDK Scenario Registry/Shell Hotfix Test

## Purpose

Register canonical scenario `source_sdk_version_collection_missing` and keep legacy alias
`source_ios_sdk_version_collection_missing` compatible.

The generic SDK scenario represents SDK-version tagging/dispatch issues across mobile apps,
not only iOS. It should be resolved by the scenario registry and run as segment-targeted
WC missing.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_sdk_scenario_registry_shell_hotfix.zip
chmod +x deploy/apply_phase4c_sdk_scenario_registry_shell_hotfix.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4c_sdk_scenario_registry_shell_hotfix.py
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile pipelines/collect/collector_wc_log_hit_v04.py
```

## Smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_sdk_version_collection_missing 0
```

## Expected

```text
[STEP 0.1] resolve scenario registry
scenario_family=source_observability_anomaly

wc_missing_rule_mode=segment_targeted
target_rule=SDK_VERSION_COLLECTION_MISSING_V1 or sdk_version_collection_missing
target_app=ios_app,android_app/*
target_sdk=wc-ios-3.2.1,wc-android-3.2.1

targeted_page_rows > 0
targeted_missing_rows > 0

risk_pattern=localized_failure
```

Legacy alias should still work:

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_sdk_version_collection_missing 0
```
