# CASE-OBS-001 Phase4-B Purchase Event Targeting Hotfix Test

## Purpose

Fix `source_ios_purchase_event_collection_missing` so it is truly conversion/purchase-event targeted:

- `segment_targeted` collector mode is used.
- Target rows are conversion/event rows, not all iOS PV rows.
- Non-target PV rows are not dropped.
- Validator checks all-level PV gap for purchase-event contract.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_purchase_event_targeting_hotfix.zip
chmod +x deploy/apply_phase4b_purchase_event_targeting_hotfix.py
chmod +x pipelines/collect/collector_wc_log_hit_v04.py
chmod +x pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py

PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4b_purchase_event_targeting_hotfix.py

bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
python -m py_compile pipelines/collect/collector_wc_log_hit_v04.py
```

## Test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Expected

```text
rule_mode=segment_targeted
target_rule=ios_purchase_event_collection_missing
conversion_only=true
targeted_page_rows > 0
targeted_missing_rows > 0
metric_conversion_gap >= 0.50
all_pv_gap <= 0.12
risk_pattern=silent_distortion
```
