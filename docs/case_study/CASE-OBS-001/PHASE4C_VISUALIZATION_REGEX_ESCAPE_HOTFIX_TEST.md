# CASE-OBS-001 Phase4-C Visualization Regex Escape Hotfix Test

## Purpose

Fix R parse/runtime failure in `build_case_obs_001_figures.R` caused by an invalid regex escape:

```text
Error: '\.' is an unrecognized escape in character string
```

The patch changes the Figure 4 title-cleanup regex from an invalid single-backslash escape to a valid R regex escape.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_visualization_regex_escape_hotfix.zip
chmod +x pipelines/commerce/visualization/build_case_obs_001_figures.R
```

## Test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_purchase_event_collection_missing 0
```

## Expected

```text
[CASE_OBS_001_DIAGNOSTIC_REPORT] report_type=operational_reliability_diagnostic_report ...
[OK] build_case_obs_001_figures output_dir=...
[OK] validate_case_obs_001_figures passed
```
