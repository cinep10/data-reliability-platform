# CASE-OBS-001 Phase4-B Step2 Authority Pattern Layer Test

## Purpose

Add an explicit **Pattern Layer** between Evidence and Risk.

This step does **not** make app version, SDK version, URL, browser, campaign, or any case-specific segment an authority risk feature.

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

Key rules:

```text
Evidence is not risk.
Pattern is not risk.
Pattern interprets generic evidence into reusable failure shapes.
OBS remains explanation/reference, not authority pattern input.
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_step2_authority_pattern_layer_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/analytics/build_v05_reliability_analysis.R
chmod +x pipelines/commerce/validation/validate_v05_authority_pattern_layer.py
```

## One-day smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

Expected log:

```text
[AUTHORITY_EVIDENCE_LAYER] ... evidence_is_not_risk=1 next=pattern_layer
[AUTHORITY_PATTERN_LAYER] version=v05_phase4b_step2_pattern_layer_v1 pattern_ready=1 risk_pattern=... pattern_is_not_risk=1 evidence_to_pattern=1 next=risk_layer
[STEP 6.02] Authority Analytics Layer: evidence-to-pattern layer validation
[OK] validate_v05_authority_pattern_layer passed
```

## Direct validation

```bash
python -m pipelines.commerce.validation.validate_v05_authority_pattern_layer \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --require-pattern
```

## SQL check

```sql
SELECT risk_pattern,
       pattern_confidence,
       pattern_reason,
       evidence_layer_version,
       pattern_layer_version
FROM reliability_analysis_result_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='source_wc_collection_missing'
ORDER BY created_at DESC
LIMIT 1;
```

## Completion criteria

- `pattern_layer_version = v05_phase4b_step2_pattern_layer_v1`
- `pattern_ready = 1`
- `risk_pattern` is one of:
  - `stable`
  - `localized_failure`
  - `systemic_failure`
  - `silent_distortion`
  - `reconciliation_failure`
  - `emerging_reliability_degradation`
- `pattern_confidence` is between 0 and 1
- `pattern_payload_json.layer = AUTHORITY_PATTERN_LAYER`
- Pattern does not contain case-specific tokens such as `ios-app`, `wc-ios`, `app_version`, `sdk_version`, URL, browser, or campaign.
