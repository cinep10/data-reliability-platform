# CASE-OBS-001 Phase4-B Purchase Event Targeting v2 Hotfix Test

## Purpose

Fix `source_ios_purchase_event_collection_missing` so it drops only iOS conversion/purchase rows instead of broad PV/page rows.

Expected behavior:

```text
rule_mode=segment_targeted
conversion_only=true
targeted_page_rows > 0
targeted_dropped > 0
targeted_missing_rows > 0
conversion_gap >= 0.50
all_pv_gap <= 0.12
risk_pattern=silent_distortion
```

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_purchase_event_targeting_v2_hotfix.zip
chmod +x deploy/apply_phase4b_purchase_event_targeting_v2_hotfix.py
chmod +x pipelines/collect/collector_wc_log_hit_v04.py
chmod +x pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py

PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4b_purchase_event_targeting_v2_hotfix.py

bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile pipelines/collect/collector_wc_log_hit_v04.py
python -m py_compile pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
```

## Smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Key checks

Look for collector output:

```text
wc_missing_rule_mode=segment_targeted
conversion_only=true
targeted_page_rows=<positive>
targeted_dropped=<positive>
```

Look for scenario validator:

```text
targeted_page_rows > 0
targeted_missing_rows > 0
metric_conversion_gap >= 0.50
all_pv_gap <= 0.12
[OK] validate_v05_ios_collection_missing_scenario passed
```
