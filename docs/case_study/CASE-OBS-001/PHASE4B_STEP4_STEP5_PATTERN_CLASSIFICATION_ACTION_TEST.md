# CASE-OBS-001 Phase4-B Step4/5 Pattern Classification + Pattern Action Catalog Test

## Purpose

Finalize the post-risk Knowledge Base separation after Step3 Pattern-driven Risk.

The runtime authority chain is now:

```text
Measurement
↓
Evidence
↓
Pattern
↓
Risk
↓
Classification / Narrative
↓
Pattern Action Catalog
```

Step4/5 does **not** change numeric risk. It makes Semantic and Action explicit Knowledge Base consumers:

```text
Pattern + Risk -> Classification / Narrative
Pattern + Classification + Risk Level + Confidence -> Action Catalog
```

Key rules:

```text
Classification is not risk.
Action is not risk.
OBS remains reference explanation only.
Action catalog is pattern-driven, not scenario-driven.
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_step45_pattern_classification_action_catalog_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/semantic/build_v05_semantic_interpretation.R
chmod +x pipelines/commerce/action/build_v05_action_recommendation.py
chmod +x pipelines/commerce/validation/validate_v05_pattern_classification_action_catalog.py
```

## Syntax checks

```bash
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile \
  pipelines/commerce/action/build_v05_action_recommendation.py \
  pipelines/commerce/validation/validate_v05_pattern_classification_action_catalog.py
```

## One-day smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

Expected log snippets:

```text
[KNOWLEDGE_BASE_CLASSIFICATION]
version=v05_phase4b_step4_pattern_classification_v1
pattern=<stable|localized_failure|systemic_failure|silent_distortion|reconciliation_failure|...>
classification=<...>
semantic_is_risk_driver=0
classification_is_risk_engine=0
source=authority_pattern_layer
obs_reference_only=1

[PATTERN_ACTION_CATALOG]
version=v05_phase4b_step5_pattern_action_catalog_v1
mode=pattern_driven
source=authority_pattern_layer
action_is_risk_engine=0

[STEP 6.09] Knowledge Base Layer: pattern classification/action catalog validation
[OK] validate_v05_pattern_classification_action_catalog passed
```

## Direct validation

```bash
python -m pipelines.commerce.validation.validate_v05_pattern_classification_action_catalog \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --require-pattern-classification \
  --require-pattern-action \
  --min-pattern-confidence 0.05
```

## SQL checks

```sql
SELECT risk_pattern,
       pattern_confidence,
       risk_classification,
       action_catalog_key,
       classification_source,
       semantic_is_risk_driver,
       classification_is_risk_engine,
       pattern_to_classification_rule_id
FROM semantic_interpretation_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='source_wc_collection_missing'
ORDER BY created_at DESC
LIMIT 1;

SELECT action_rank,
       action_type,
       recommended_action,
       action_catalog_mode,
       action_catalog_source,
       risk_pattern,
       pattern_action_rule_id,
       action_is_risk_engine
FROM action_recommendation_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='source_wc_collection_missing'
ORDER BY action_rank;
```

## Completion criteria

- `semantic_is_risk_driver = 0`
- `classification_is_risk_engine = 0`
- `classification_source = authority_pattern_layer`
- `risk_pattern` is present in semantic/action rows
- `action_catalog_mode = pattern_driven`
- `action_catalog_source = authority_pattern_layer`
- `action_is_risk_engine = 0`
- `OBS` appears only as reference/root-cause explanation, not as classification/risk driver
