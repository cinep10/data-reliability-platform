# Phase4-C R syntax + baseline evidence validator v2 hotfix

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_rsyntax_validator_v2_hotfix.zip
chmod +x deploy/apply_phase4c_rsyntax_validator_v2_hotfix.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4c_rsyntax_validator_v2_hotfix.py
Rscript -e "parse(file='pipelines/commerce/analytics/build_v05_reliability_analysis.R'); cat('R parse OK\n')"
python -m py_compile pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
```

## Smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 baseline 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_purchase_event_collection_missing 0
```
