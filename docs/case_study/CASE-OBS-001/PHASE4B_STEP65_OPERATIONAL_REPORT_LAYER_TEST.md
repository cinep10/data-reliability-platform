# CASE-OBS-001 Phase4-B Step6.5 Operational Reliability Diagnostic Report Layer Test

## Purpose

Convert the visualization output from an engineering-oriented figure pack to an Operational Reliability Diagnostic Report.

The report layers are:

```text
Business
Operational
Technical
```

Key contract:

```text
Gap is not business risk.
Evidence does not directly drive risk.
Pattern is the risk driver.
Authority actions drive remediation.
OBS reference actions support investigation only and do not drive risk.
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_step65_operational_report_layer_patch.zip
chmod +x pipelines/commerce/visualization/build_case_obs_001_figures.R
chmod +x pipelines/commerce/validation/validate_case_obs_001_figures.py
chmod +x deploy/apply_phase4b_step65_operational_report_layer_patch.py

PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4b_step65_operational_report_layer_patch.py

bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile pipelines/commerce/validation/validate_case_obs_001_figures.py
Rscript -e 'parse(file="pipelines/commerce/visualization/build_case_obs_001_figures.R"); cat("R parse OK\n")'
```

## One-day smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

Expected log:

```text
[STEP 6.10] CASE-OBS-001 Operational Reliability Diagnostic Report
[CASE_OBS_001_DIAGNOSTIC_REPORT] report_type=operational_reliability_diagnostic_report ...
[OK] validate_case_obs_001_figures passed
```

## Direct validation

```bash
python -m pipelines.commerce.validation.validate_case_obs_001_figures \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --figure-dir /Volumes/EXTERNAL_USB/dev/log/artifacts/CASE-OBS-001/2026-06-01/source_wc_collection_missing/figures \
  --require-decision-support \
  --require-operational-report \
  --require-engineer-appendix \
  --require-mobile-app-evidence
```

## Expected file layout

```text
business/fig01_can_we_trust_this_kpi.png
business/fig02_how_much_data_is_missing.png
business/fig03_which_kpis_are_affected.png
operational/fig04_why_this_is_not_critical.png
operational/fig05_recommended_action_plan.png
technical/fig06_potential_investigation_candidates.png
technical/appendix01_web_vs_wc_evidence.png
technical/appendix02_baseline_control_evidence.png
technical/appendix03_url_evidence.png
technical/appendix04_pattern_driven_risk_decomposition.png
technical/appendix05_app_sdk_detailed_evidence.png
figure_manifest.json
```

## Completion criteria

- Manifest `report_type = operational_reliability_diagnostic_report`.
- Business, Operational, Technical layers exist.
- Figure 1 contains `decision_reliability` and `business_impact` semantics.
- Figure 5 separates authority actions from OBS reference actions.
- Figure 6 states that OBS candidates support investigation only.
- Manifest includes `obs_does_not_drive_risk=true`.
