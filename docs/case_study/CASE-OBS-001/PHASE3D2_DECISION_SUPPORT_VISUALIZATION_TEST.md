# CASE-OBS-001 Phase3-D2 Decision Support Visualization Layer Test

## Purpose

Phase3-D2 upgrades the ggplot2 output from an engineer evidence pack into a decision-support visualization pack for Case Report / Toolkit / Consulting use.

The visualization layer is not a monitoring authority and does not change risk calculations.

```text
Unified Risk = Authority Risk Layer
Semantic / Action = Knowledge Base Layer
Visualization = Decision Support Report Layer
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase3d2_decision_support_visualization_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/visualization/build_case_obs_001_figures.R
chmod +x pipelines/commerce/validation/validate_case_obs_001_figures.py
```

## Required R packages

RStudio is not required. Install packages with Rscript:

```bash
Rscript -e 'install.packages(c("ggplot2","DBI","RMariaDB","jsonlite"), repos="https://cloud.r-project.org")'
```

## Smoke test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

Expected log:

```text
[STEP 6.10] CASE-OBS-001 Phase3-D2 decision support visualization layer
[OK] build_case_obs_001_figures mode=decision_support ... figures=9
[OK] validate_case_obs_001_figures passed
```

## Expected artifact layout

```text
artifacts/case_study/CASE-OBS-001/2026-06-01/source_wc_collection_missing/figures/
  executive/
    fig01_executive_reliability_summary.png
    fig02_reality_vs_observability_waterfall.png

  analyst/
    fig03_kpi_impact_heatmap.png
    fig04_journey_impact_view.png
    fig05_recommended_action_matrix.png

  engineer_appendix/
    appendix01_web_vs_wc_gap.png
    appendix02_baseline_current_gap.png
    appendix03_url_gap_topn.png
    appendix04_risk_score_breakdown.png

  figure_manifest.json
```

## Direct validation

```bash
python -m pipelines.commerce.validation.validate_case_obs_001_figures \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --figure-dir /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform/artifacts/case_study/CASE-OBS-001/2026-06-01/source_wc_collection_missing/figures \
  --require-decision-support \
  --require-engineer-appendix \
  --require-gap-signal
```

## Completion criteria

- Executive figures exist: summary card + reality/observability waterfall.
- Analyst figures exist: KPI heatmap + journey impact + action matrix.
- Engineer appendix exists: legacy evidence pack moved to appendix.
- `figure_manifest.json` has `visualization_mode=decision_support`.
- `decision_support_summary` answers detection, severity, localization, and recommendation.
- `source_wc_collection_missing` manifest preserves the evidence chain:

```text
evidence_signal=wc_collection_gap
evidence_metric=collection_gap_rate
mapping_rule_id=OBS_WC_COLLECTION_GAP_TO_COLLECTION_RELIABILITY_V1
```

## Interpretation

The old figures were not wrong. They were engineer evidence. Phase3-D2 changes the output into a diagnostic report structure:

```text
Executive: problem / severity / action
Analyst: impact / localization
Engineer: detailed evidence appendix
```
