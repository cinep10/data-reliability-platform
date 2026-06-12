# CASE-OBS-001 Phase4-B Step3 Pattern-driven Risk Layer Test

## Purpose

Change Authority Risk input from:

```text
Evidence -> Risk
```

to:

```text
Evidence -> Pattern -> Risk
```

This step does **not** make OBS an authority input. OBS remains reference explanation.

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_step3_pattern_driven_risk_layer_patch.zip
chmod +x pipelines/commerce/score/build_v05_unified_risk_score.R
chmod +x pipelines/commerce/validation/validate_v05_pattern_driven_risk_layer.py
chmod +x deploy/apply_phase4b_step3_pattern_driven_risk_shell_patch.py
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4b_step3_pattern_driven_risk_shell_patch.py
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## One-day smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

## Expected log

```text
[AUTHORITY_EVIDENCE_LAYER] ... evidence_is_not_risk=1 next=pattern_layer
[AUTHORITY_PATTERN_LAYER] ... pattern_is_not_risk=1 evidence_to_pattern=1 next=risk_layer
[AUTHORITY_RISK_LAYER] version=v05_phase4b_step3_pattern_driven_risk_v1 pattern=... evidence_direct_to_risk=0 confidence_separate=1
[STEP 6.071] Authority Risk Layer: pattern-driven risk validation
[OK] validate_v05_pattern_driven_risk_layer passed
```

## Direct validation

```bash
python -m pipelines.commerce.validation.validate_v05_pattern_driven_risk_layer \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --require-risk-signal
```

## Completion criteria

- `risk_model_version = v05_phase4b_step3_pattern_driven_risk_v1`
- `risk_pattern` is populated from Authority Analytics Pattern Layer.
- `pattern_is_risk_driver = 1`
- `evidence_direct_to_risk = 0`
- `overall_risk_score = likelihood_score * impact_score`
- `confidence_separate_from_risk = 1`
- No `legacy_rate` collector mode is passed by the operating shell.
