# CASE-OBS-001 Phase4-B Evidence v2 Targeted Scenario + Concentration/Criticality Test

## Purpose

This patch fixes the Phase4-A/Phase4-B issue where iOS detailed scenarios executed successfully but behaved like the broad WC collection missing case.

It makes the chain explicit:

```text
Targeted iOS scenario
↓
Collector segment_targeted drop
↓
Measurement rows prove targeted_page_rows > 0
↓
Authority Evidence Layer computes generic concentration / criticality
↓
Pattern Layer differentiates localized_failure / silent_distortion
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_evidence_v2_targeted_concentration_criticality_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/collect/collector_wc_log_hit_v04.py
chmod +x pipelines/commerce/analytics/build_v05_reliability_analysis.R
chmod +x pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
chmod +x pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
chmod +x pipelines/commerce/validation/validate_v05_authority_pattern_layer.py
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile \
  pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py \
  pipelines/commerce/validation/validate_v05_authority_evidence_layer.py \
  pipelines/commerce/validation/validate_v05_authority_pattern_layer.py
```

## One-day scenario tests

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_app_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_sdk_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Expected collector log

For app-version and SDK scenarios:

```text
wc_missing_rule_mode=segment_targeted
targeted_page_rows > 0
targeted_dropped > 0
```

## Expected Step 4.121

```text
[IOS_COLLECTION_SCENARIO]
targeted_page_rows=...
targeted_missing_rows=...
[OK] validate_v05_ios_collection_missing_scenario passed
```

## Expected Step 6.015

```text
[AUTHORITY_EVIDENCE_LAYER]
concentration_evidence_score > 0   # app/sdk scenarios
criticality_evidence_score > 0     # purchase-event scenario
[OK] validate_v05_authority_evidence_layer passed
```

## Expected Step 6.02

```text
source_ios_app_version_collection_missing -> risk_pattern=localized_failure
source_ios_sdk_version_collection_missing -> risk_pattern=localized_failure
source_ios_purchase_event_collection_missing -> risk_pattern=silent_distortion
```

## SQL checks

```sql
SELECT scenario_name,
       concentration_evidence_score,
       criticality_evidence_score,
       risk_pattern,
       pattern_confidence,
       pattern_reason
FROM reliability_analysis_result_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name IN (
    'source_ios_app_version_collection_missing',
    'source_ios_sdk_version_collection_missing',
    'source_ios_purchase_event_collection_missing'
  )
ORDER BY run_id DESC
LIMIT 10;
```

## Completion criteria

- iOS scenarios are no longer executed as broad WC collection missing.
- `targeted_page_rows > 0` and `targeted_missing_rows > 0` are validated.
- App/SDK scenarios produce concentration evidence.
- Purchase-event scenario produces criticality evidence.
- Pattern Layer differentiates detailed scenarios instead of returning `reconciliation_failure` for all.
- OBS remains reference/explanation; Authority Risk consumes generic Pattern only.
