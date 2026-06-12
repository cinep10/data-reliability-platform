# CASE-OBS-001 Phase4-B Step6.5 Visualization Factor Hotfix Test

## Purpose

Fix `build_case_obs_001_figures.R` runtime failure:

```text
Error in `levels<-`(`*tmp*`, value = as.character(levels)) :
  factor level [4] is duplicated
```

The failure is caused by shortened labels collapsing multiple original segments/actions into duplicate factor levels in diagnostic report figures.
This patch adds `safe_factor()` and applies it to report figures that use shortened labels.

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_step65_visualization_factor_hotfix.zip
chmod +x pipelines/commerce/visualization/build_case_obs_001_figures.R
```

## Direct visualization test

Use the last failed run values:

```bash
Rscript pipelines/commerce/visualization/build_case_obs_001_figures.R \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id 711 \
  --source-gen-run-id 704 \
  --output-dir /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform/artifacts/case_study/CASE-OBS-001/2026-06-01/source_wc_collection_missing/figures \
  --view-mode diagnostic_report \
  --include-engineer-appendix true \
  --top-n 15
```

## Expected result

```text
[CASE_OBS_001_DIAGNOSTIC_REPORT] report_type=operational_reliability_diagnostic_report ...
[OK] build_case_obs_001_figures output_dir=...
```

No `factor level is duplicated` error should appear.

## Full smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```
