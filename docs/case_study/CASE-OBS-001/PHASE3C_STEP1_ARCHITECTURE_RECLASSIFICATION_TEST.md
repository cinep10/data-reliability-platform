# CASE-OBS-001 Phase3-C Step 1 Architecture Reclassification Test

## Goal

Before changing the risk formula, confirm that the current codebase clearly separates:

```text
OBS = Reference Evidence
Baseline Science = Authority Reference Layer
Reliability Analysis = Authority Analytics Layer
Unified Risk = Authority Risk Layer
Semantic / Action = Knowledge Base
```

## Apply Patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase3c_step1_architecture_reclassification_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/validation/validate_v05_architecture_reclassification.py
```

## Static Validation

```bash
python -m pipelines.commerce.validation.validate_v05_architecture_reclassification \
  --project-root /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  --contract /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform/pipelines/commerce/configs/v05_authority_layer_contract.yaml
```

Expected:

```text
[PASS] contract: architecture markers present
[PASS] observability_reference_analysis: architecture markers present
[PASS] baseline_science: architecture markers present
[PASS] reliability_analysis: architecture markers present
[PASS] unified_risk: architecture markers present
[PASS] semantic_kb: architecture markers present
[PASS] action_catalog: architecture markers present
[PASS] operation_shell: architecture markers present
[OK] validate_v05_architecture_reclassification passed
```

## Smoke Test

Baseline:

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

Anomaly:

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

Expected new log marker near STEP 0:

```text
architecture: OBS=reference evidence; Baseline Science=authority reference; Reliability Analysis=authority analytics; Unified Risk=authority risk; Semantic/Action=knowledge base
```

Expected new step:

```text
[STEP 0.26] architecture layer reclassification contract validation
[OK] validate_v05_architecture_reclassification passed
```

## Completion Criteria

- Pipeline results remain unchanged.
- No risk formula is changed in this step.
- OBS files are labeled as reference evidence.
- Baseline Science is labeled as authority reference, not OBS.
- Reliability Analysis is labeled as authority analytics.
- Unified Risk is labeled as authority risk.
- Semantic/Action are labeled as Knowledge Base.
