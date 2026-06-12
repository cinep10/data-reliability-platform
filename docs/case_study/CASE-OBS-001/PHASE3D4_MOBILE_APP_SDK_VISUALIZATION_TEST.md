# CASE-OBS-001 Phase3-D4 Mobile/App/SDK Evidence Visualization Test

## Purpose

This patch completes the missing visualization evidence for mobile/app/SDK concentration.
D3 already generated decision-support figures, but the report could not answer:

```text
Which app platform, app version, or SDK version shows concentrated collection loss?
```

Phase3-D4 adds evidence profiling, not root-cause diagnosis.

## Added figures

```text
analyst/fig06_app_sdk_impact_view.png
engineer_appendix/appendix05_app_version_sdk_gap.png
```

## Important interpretation

These figures do not assert an SDK or app-version root cause. They show where the evidence is concentrated and which segment should be inspected first.

## Run

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

## Expected log

```text
[STEP 6.10] CASE-OBS-001 Phase3-D4 decision support visualization + mobile/app/SDK evidence layer
[OK] build_case_obs_001_figures ... figures=11
[OK] validate_case_obs_001_figures passed
```

## Expected manifest roles

```text
fig06_app_sdk_impact_view.png: mobile_app_sdk_evidence_profile
appendix05_app_version_sdk_gap.png: app_version_sdk_gap_evidence
```

## Direct validation

```bash
python -m pipelines.commerce.validation.validate_case_obs_001_figures \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --figure-dir artifacts/case_study/CASE-OBS-001/2026-06-01/source_wc_collection_missing/figures \
  --require-decision-support \
  --require-engineer-appendix \
  --require-gap-signal \
  --require-mobile-app-evidence
```

## Completion criteria

- Executive figures remain present.
- Analyst layer has at least 4 figures.
- Engineer appendix has at least 5 figures.
- Mobile/App/SDK figures are included in the manifest.
- The figure roles are explicitly set to evidence profiling, not diagnosis.
- Deprecated `geom_label(label.size=...)` warning is removed by using `linewidth`.
