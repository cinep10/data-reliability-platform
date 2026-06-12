# CASE-OBS-001 Phase4-A OBS Interpretation Duplicate Candidate Hotfix

## Purpose

Fix duplicate primary key failures in `build_v05_observability_interpretation.R` for iOS app-version / SDK-version targeted collection missing scenarios.

The iOS targeted scenarios can create the same `root_cause_dimension + root_cause_value` candidate from multiple OBS evidence sources. The table primary key treats that pair as the stable candidate identity, so the R script must collapse duplicates before insert.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4a_obs_interpretation_dedup_hotfix.zip
chmod +x pipelines/commerce/analytics/build_v05_observability_interpretation.R
```

## Test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_app_version_collection_missing 0
```

Then run the other Phase4-A scenarios:

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_sdk_version_collection_missing 0

/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Expected

No duplicate key failure at STEP 6.06.

```text
[STEP 6.06] Reference Evidence Layer: OBS interpretation / root-cause confidence support
[OK] build_v05_observability_interpretation ...
```

For app-version scenario:

```text
[STEP 6.061] CASE-OBS-001 Phase4-A iOS app-version interpretation validation
[OK] validate_v05_ios_collection_missing_scenario passed
```
