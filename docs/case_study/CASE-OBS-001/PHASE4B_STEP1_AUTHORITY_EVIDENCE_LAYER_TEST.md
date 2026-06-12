# CASE-OBS-001 Phase4-B Step1 Authority Evidence Layer Test

## Purpose

Make the `Reliability Analysis` output explicitly expose an **Authority Evidence Layer** before any Pattern or Risk interpretation.

This step does **not** change the risk formula. It only makes the boundary explicit:

```text
Measurement
↓
Evidence
↓
Pattern
↓
Risk
↓
Classification / Action
```

Key rule:

```text
Evidence is not risk.
OBS remains reference evidence, not authority input.
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_step1_authority_evidence_layer_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/analytics/build_v05_reliability_analysis.R
chmod +x pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
```

## One-day smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

Expected log:

```text
[AUTHORITY_EVIDENCE_LAYER] version=v05_phase4b_step1_evidence_layer_v1 ... evidence_is_not_risk=1 next=pattern_layer
[STEP 6.015] Authority Analytics Layer: explicit evidence layer validation
[OK] validate_v05_authority_evidence_layer passed
```

## Direct validation

```bash
python -m pipelines.commerce.validation.validate_v05_authority_evidence_layer \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --require-evidence-signal
```

## Expected columns

`reliability_analysis_result_day_v05` must include:

```text
evidence_layer_version
evidence_ready
baseline_evidence_score
statistical_evidence_group_score
propagation_evidence_score
impact_evidence_score
concentration_evidence_score
criticality_evidence_score
evidence_payload_json
evidence_summary
```

## SQL check

```sql
SELECT evidence_layer_version,
       evidence_ready,
       baseline_evidence_score,
       statistical_evidence_group_score,
       propagation_evidence_score,
       impact_evidence_score,
       concentration_evidence_score,
       criticality_evidence_score,
       evidence_summary
FROM reliability_analysis_result_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='source_wc_collection_missing'
ORDER BY created_at DESC
LIMIT 1;
```

## Completion criteria

- Evidence layer columns exist.
- `evidence_layer_version = v05_phase4b_step1_evidence_layer_v1`.
- `evidence_ready = 1`.
- `evidence_payload_json.layer = AUTHORITY_EVIDENCE_LAYER`.
- Payload includes six generic groups: baseline, statistical, propagation, impact, concentration, criticality.
- Payload says Pattern Layer is required before Risk interpretation.
- OBS is explicitly marked as reference, not authority.
- Risk formula/result does not need to change in this step.
