# CASE-OBS-001 Phase4-B Evidence v2.1 Pattern Differentiation Hotfix Test

## Purpose

Fix the false failure where targeted iOS app/sdk scenarios produced valid generic concentration evidence around 0.17, but validation required 0.20. Also make the Pattern Layer prefer generic concentration/criticality evidence before broad reconciliation evidence.

This preserves the architecture:

```text
Measurement -> Evidence -> Pattern -> Risk
OBS = reference explanation only
```

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_evidence_v21_pattern_differentiation_hotfix.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/analytics/build_v05_reliability_analysis.R
chmod +x pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
chmod +x pipelines/commerce/validation/validate_v05_authority_pattern_layer.py
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
python -m py_compile pipelines/commerce/validation/validate_v05_authority_pattern_layer.py
```

## Tests

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_app_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_sdk_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Expected

App / SDK scenarios:

```text
[GENERIC_EVIDENCE_V2] concentration >= 0.15
[OK] validate_v05_authority_evidence_layer passed
risk_pattern=localized_failure
[OK] validate_v05_authority_pattern_layer passed
```

Purchase-event scenario:

```text
[GENERIC_EVIDENCE_V2] criticality >= 0.50
risk_pattern=silent_distortion
```

## Notes

- `0.15` is a generic concentration threshold, not an app-version-specific rule.
- Authority Pattern never stores `app_version`, `sdk_version`, URL, browser, or campaign tokens.
- OBS remains reference explanation for the concrete candidate segment.
