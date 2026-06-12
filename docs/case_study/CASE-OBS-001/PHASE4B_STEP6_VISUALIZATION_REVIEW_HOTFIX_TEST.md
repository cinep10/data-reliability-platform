# CASE-OBS-001 Phase4-B Step6 Visualization/Review Hotfix Test

## Purpose

This hotfix connects the existing ggplot2 visualization script to the Mac host operation shell and fixes the final STEP 8 action review query after the Authority Action / OBS Reference Action split.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_step6_visualization_review_hotfix.zip
chmod +x deploy/apply_phase4b_step6_visualization_review_hotfix.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4b_step6_visualization_review_hotfix.py
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## Static checks

```bash
grep -n "STEP 6.10" deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
grep -n "build_case_obs_001_figures.R" deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
grep -n "validate_case_obs_001_figures" deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
grep -n "FROM action_recommendation_day_v05" deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## Smoke test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

Expected logs:

```text
[STEP 6.10] Visualization Layer: CASE-OBS-001 decision-support figures
[OK] build_case_obs_001_figures ... figures=...
[OK] validate_case_obs_001_figures passed
[STEP 8] authoritative review
... action_recommendation_day_v05 rows displayed without Unknown column action_rank
[DONE] v0.5 commerce reliability pipeline completed
```

## What changed

- Adds Step 6.10 to call `pipelines/commerce/visualization/build_case_obs_001_figures.R`.
- Runs `pipelines.commerce.validation.validate_case_obs_001_figures` after figure generation.
- Fixes the malformed STEP 8 action query that was missing `FROM`.
- Adds fallbacks for both `action_recommendation_day_v05` and legacy `action_recommendation_day` layouts.
- Leaves Authority Risk / Pattern / Classification / Action formulas unchanged.
