# CASE-OBS-001 Phase4-D Visual Layer v7

Purpose: fix App Version / SDK Version customer report figures where `appendix03_mechanism_specific_evidence` and `fig06_mechanism_root_cause_concentration` appeared as misleading 0%/100% row-level charts.

## What changed

- `failure_mechanism` is still the visual router.
- `fig06` now uses a mechanism evidence profile, not raw row-level maxima.
- `appendix03` reuses the same mechanism evidence profile as supporting evidence.
- App Version view shows: app version concentration, UID missing signal, login user gap, identified UV impact.
- SDK Version view shows: SDK version concentration, URL attribution shift, order URL undercount, collapse/overcount signal.
- Purchase Event view is unchanged in principle but uses the same profile contract.
- Manifest now records appendix03 score values and distinct-label checks.
- Validator adds `--require-visual-v7`.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4d_visual_layer_v7_patch.zip
```

## Regenerate and validate

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_app_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_sdk_version_collection_missing 0

python3 -m pipelines.commerce.validation.validate_case_obs_001_figures \
  --figure-dir artifacts/case_study/CASE-OBS-001/2026-06-01/source_ios_app_version_collection_missing/figures \
  --require-operational-report \
  --require-customer-visual-redesign \
  --require-engineer-appendix \
  --require-visual-v7

python3 -m pipelines.commerce.validation.validate_case_obs_001_figures \
  --figure-dir artifacts/case_study/CASE-OBS-001/2026-06-01/source_sdk_version_collection_missing/figures \
  --require-operational-report \
  --require-customer-visual-redesign \
  --require-engineer-appendix \
  --require-visual-v7
```
