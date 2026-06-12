# Phase4-C Baseline Evidence Validator Signal Hotfix Test

## Purpose

Baseline validation must not fail because `traffic_preservation_score=1.0`.
Traffic preservation is a normal-state indicator, not an anomaly signal.

The validator now uses `baseline_anomaly_signal` for `--allow-baseline-zero` and excludes:

- `traffic_preservation_score`
- `business_kpi_distortion_score` unless paired with non-zero criticality/impact/concentration evidence

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_baseline_validator_signal_hotfix.zip
chmod +x deploy/apply_phase4c_baseline_validator_signal_hotfix.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4c_baseline_validator_signal_hotfix.py
python -m py_compile pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
```

## Smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

## Expected

```text
traffic_preservation_score=1.000000
[OK] validate_v05_authority_evidence_layer passed
```
