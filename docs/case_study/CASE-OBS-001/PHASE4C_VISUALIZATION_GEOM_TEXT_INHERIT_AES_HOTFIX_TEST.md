# CASE-OBS-001 Phase4-C Visualization geom_text inherit.aes Hotfix Test

## Purpose

Fix ggplot2 runtime failure in STEP 6.10:

```text
Error in ggplot2::geom_text(): object 'metric' not found
```

The failure occurs when a text layer inherits parent plot aesthetics such as
`y=metric` while the layer data does not contain that column. This patch makes
text layers use explicit `data`, `x`, `y`, and `inherit.aes=FALSE` where needed.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_visualization_geom_text_hotfix.zip
chmod +x pipelines/commerce/visualization/build_case_obs_001_figures.R
```

## Test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_purchase_event_collection_missing 0
```

Expected:

```text
[CASE_OBS_001_DIAGNOSTIC_REPORT]
[OK] build_case_obs_001_figures output_dir=...
[OK] validate_case_obs_001_figures passed
```
