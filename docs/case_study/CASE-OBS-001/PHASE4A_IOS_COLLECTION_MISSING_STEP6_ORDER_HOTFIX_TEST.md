# CASE-OBS-001 Phase4-A iOS Collection Missing Step6 Order Hotfix Test

## Purpose

Fix regression introduced when Phase4-A iOS targeted collection scenarios were applied on top of the Phase3-D4 visualization assets.

The failing path was:

```text
Reliability Analysis -> OBS Analysis -> Semantic
```

This violates the Phase3-C contract because Semantic KB must run after Unified Risk:

```text
Reliability Analysis -> OBS Analysis/Interpretation -> Unified Risk -> Semantic KB -> Action Catalog
```

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4a_ios_step6_order_hotfix.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/collect/collector_wc_log_hit_v04.py
chmod +x pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
chmod +x deploy/apply_phase4a_ios_collection_missing_registry_patch.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4a_ios_collection_missing_registry_patch.py
```

## Test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_app_version_collection_missing 0
```

Expected ordering:

```text
[STEP 6] build_v05_reliability_analysis.R
[STEP 6.01] reliability analysis risk input validation
[STEP 6.05] observability analysis for support only
[STEP 6.06] OBS interpretation / root-cause confidence support
[RUN] build_v05_unified_risk_score.R
[STEP 6.07] likelihood x impact risk model validation
[STEP 6.08] semantic classification / narrative from authority risk
[STEP 6.09] semantic/action catalog validation
```

The previous error must disappear:

```text
Error: missing unified risk row; Step5 semantic must run after build_v05_unified_risk_score.R
```

## Additional scenario tests

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_sdk_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_purchase_event_collection_missing 0
```

Expected iOS validator logs:

```text
[STEP 4.121] CASE-OBS-001 Phase4-A iOS ... validation
[IOS_COLLECTION_SCENARIO]
[OK] validate_v05_ios_collection_missing_scenario passed
```
