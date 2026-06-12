# CASE-OBS-001 Phase4-C Evidence v2 Persistence Hotfix Test

## Purpose

Fix a mismatch where `build_v05_reliability_analysis.R` computes:

- `business_kpi_distortion`
- `traffic_preservation`

and prints them in `[GENERIC_EVIDENCE_V2]`, but the validator reads only persisted table columns and sees zero.

This patch persists Evidence v2 values to `reliability_analysis_result_day_v05` and makes the validator fallback to `evidence_payload_json` during migration.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_evidence_v2_persistence_hotfix.zip
chmod +x deploy/apply_phase4c_evidence_v2_persistence_hotfix.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4c_evidence_v2_persistence_hotfix.py

bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
```

Optional DDL apply:

```bash
mysql -u nethru -pnethru1234 weblog < sql/090_v05_evidence_v2_persistence_mariadb.sql
```

## Test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_purchase_event_collection_missing 0
```

Expected:

```text
[GENERIC_EVIDENCE_V2] ... traffic_preservation>0 business_kpi_distortion>0
[AUTHORITY_EVIDENCE_LAYER] ... business_kpi_distortion_score>0 traffic_preservation_score>0
[OK] validate_v05_authority_evidence_layer passed
risk_pattern=silent_distortion
```
