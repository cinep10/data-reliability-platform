# CASE-OBS-001 Phase4-B Purchase Event Targeting V3 Shell Hotfix Test

## Purpose

Fix the operation shell patch failure caused by stale anchors and ensure iOS purchase-event collection-missing runs as `segment_targeted` immediately before the WC collector.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_purchase_event_targeting_v3_shell_hotfix.zip
chmod +x deploy/apply_phase4b_purchase_event_targeting_v3_shell_hotfix.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4b_purchase_event_targeting_v3_shell_hotfix.py
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## Verify shell contract

```bash
grep -n "targeted scenario override" deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
grep -n "source_ios_purchase_event_collection_missing" deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
grep -n "wc-missing-target-event-names" deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## Re-run purchase event test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_purchase_event_collection_missing 0
```

Expected collector/info log:

```text
rule_mode=segment_targeted
target_rule=ios_purchase_event_collection_missing
target_event_names=purchase,purchase_success,payment_success,order_complete,conversion
conversion_only=true
targeted_page_rows > 0
targeted_dropped > 0
```

Expected validation:

```text
targeted_missing_rows > 0
metric_conversion_gap >= 0.50
all_pv_gap <= 0.12
risk_pattern=silent_distortion
```
