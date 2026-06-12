# CASE-OBS-001 Phase4-C Visualization Silent Distortion Manifest Hotfix Test

## Purpose
Fix the remaining Diagnostic Report mismatch for `source_ios_purchase_event_collection_missing`:

- `silent_distortion` must set `decision_reliability=LOW`.
- `silent_distortion` must set `business_impact=HIGH`.
- `recommended_decision` must mention purchase/conversion.
- `fig06` role must be `obs_reference_concentration_analysis`.
- `appendix04` role must be `evidence_pattern_risk_decomposition`.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_visualization_silent_distortion_manifest_hotfix.zip
chmod +x deploy/apply_phase4c_visualization_silent_distortion_manifest_hotfix.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4c_visualization_silent_distortion_manifest_hotfix.py
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## Smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Expected

```text
[CASE_OBS_001_DIAGNOSTIC_REPORT] ... decision_reliability=LOW business_impact=HIGH risk_pattern=silent_distortion
[OK] validate_case_obs_001_figures passed
```
