# Phase4-C Baseline Evidence v2 Guard Hotfix Test

## Purpose

Fix baseline validation after Criticality Evidence v2.

`traffic_preservation_score=1.0` is normal and should not count as an anomaly signal.
`business_kpi_distortion_score` must not keep a positive floor when there is no conversion/critical-event anomaly.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_baseline_evidence_v2_guard_hotfix.zip
chmod +x deploy/apply_phase4c_baseline_evidence_v2_guard_hotfix.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4c_baseline_evidence_v2_guard_hotfix.py
python -m py_compile pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
```

## Test baseline

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

Expected:

```text
business_kpi_distortion_score=0.000000
traffic_preservation_score=1.000000
[OK] validate_v05_authority_evidence_layer passed
```

## Test purchase event

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_purchase_event_collection_missing 0
```

Expected:

```text
business_kpi_distortion_score >= 0.60
traffic_preservation_score >= 0.30
risk_pattern=silent_distortion
```
