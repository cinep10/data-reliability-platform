# CASE-OBS-001 Phase3-C Step2 Reliability Analysis Risk Input Interface Test

## Purpose

Step2 fixes the output contract of `build_v05_reliability_analysis.R` as the authority analytics interface consumed by `build_v05_unified_risk_score.R`.

This step does **not** change the risk formula. It only guarantees that the following risk-input fields are materialized and validated:

```text
statistical_evidence_effective_score
statistical_significance
cross_domain_propagation_strength
affected_domains
affected_domain_count
reconciliation_confidence
baseline_delta
reconciliation_gap_score
customer_impact_score
transaction_loss_score
```

Architecture boundary:

```text
OBS = Reference Evidence
Baseline Science = Authority Reference Layer
Reliability Analysis = Authority Analytics Layer
Unified Risk = Authority Risk Layer
Semantic / Action = Knowledge Base
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase3c_step2_reliability_analysis_interface_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/analytics/build_v05_reliability_analysis.R
chmod +x pipelines/commerce/validation/validate_v05_reliability_analysis_risk_input_interface.py
```

## Static/schema validation

The new schema file is applied by the operation shell:

```text
sql/082_v05_reliability_analysis_risk_input_interface_mariadb.sql
```

## Baseline smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh   2026-06-01 baseline 0
```

Expected:

```text
[STEP 6.01] Authority Analytics Layer: reliability analysis risk input interface validation
[RELIABILITY_ANALYSIS_RISK_INPUT]
risk_input_ready=1
statistical_evidence_effective_score=0.000000
cross_domain_propagation_strength=0.000000
baseline_delta=0.000000
[OK] validate_v05_reliability_analysis_risk_input_interface passed
```

## Anomaly smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh   2026-06-01 source_wc_collection_missing 0
```

Expected:

```text
[AUTHORITY_ANALYTICS_INTERFACE] version=v05_phase3c_step2_risk_input_v1 risk_input_ready=1 ...
[STEP 6.01] Authority Analytics Layer: reliability analysis risk input interface validation
[OK] validate_v05_reliability_analysis_risk_input_interface passed
```

For `source_wc_collection_missing`, at least one risk-input signal should be non-zero:

```text
statistical_evidence_effective_score > 0
cross_domain_propagation_strength > 0
baseline_delta > 0
reconciliation_gap_score > 0
customer_impact_score > 0
```

## Direct validation

```bash
python -m pipelines.commerce.validation.validate_v05_reliability_analysis_risk_input_interface   --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog   --profile-id commerce_deliver   --target-date 2026-06-01   --scenario-name source_wc_collection_missing   --run-id <RUN_ID>   --source-gen-run-id <SOURCE_GEN_RUN_ID>   --require-signal
```

## Completion criteria

- Required columns exist in `reliability_analysis_result_day_v05`.
- `authority_interface_version = v05_phase3c_step2_risk_input_v1`.
- `risk_input_ready = 1`.
- `authority_input_payload_json` is valid JSON.
- OBS is marked as reference, not authority risk input.
- Baseline run remains near zero.
- Anomaly run exposes non-zero authority analytics risk-input signals.
