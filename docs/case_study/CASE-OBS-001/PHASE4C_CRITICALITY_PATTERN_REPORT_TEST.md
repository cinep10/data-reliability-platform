# CASE-OBS-001 Phase4-C Criticality Evidence v2 / Pattern v2 / SDK Rename / Diagnostic Report Test

## Apply
```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_criticality_pattern_report_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/collect/collector_wc_log_hit_v04.py
chmod +x pipelines/commerce/analytics/build_v05_reliability_analysis.R
chmod +x pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
chmod +x pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
chmod +x pipelines/commerce/validation/validate_v05_authority_pattern_layer.py
chmod +x pipelines/commerce/visualization/build_case_obs_001_figures.R
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile pipelines/commerce/validation/validate_v05_ios_collection_missing_scenario.py
python -m py_compile pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
python -m py_compile pipelines/commerce/validation/validate_v05_authority_pattern_layer.py
```

## Scenario tests
```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_app_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_sdk_version_collection_missing 0
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 source_ios_purchase_event_collection_missing 0
```

Expected:
- app version: `risk_pattern=localized_failure`, concentration > 0.15
- sdk version: canonical scenario `source_sdk_version_collection_missing`, old `source_ios_sdk_version_collection_missing` remains alias, concentration > 0.15
- purchase event: `traffic_preservation_score > 0.30`, `business_kpi_distortion_score > 0.60`, `risk_pattern=silent_distortion`
- Diagnostic report fig01 changes decision/business text for silent distortion.
