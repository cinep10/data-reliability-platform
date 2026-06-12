# Phase4-C Visualization Concentration Field Hotfix Test

## Purpose

Fix `build_case_obs_001_figures.R` failing on baseline/older rows with:

```text
Error: object 'concentration_evidence_score' not found
```

The diagnostic report business-decision block referenced `concentration_evidence_score` but did not assign it. This patch adds a safe evidence accessor and initializes `concentration_evidence_score` with default 0 when the column is absent.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_visualization_concentration_field_hotfix.zip
chmod +x pipelines/commerce/visualization/build_case_obs_001_figures.R
```

## Test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 baseline 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Expected

```text
[OK] build_case_obs_001_figures output_dir=...
[OK] validate_case_obs_001_figures passed
```
