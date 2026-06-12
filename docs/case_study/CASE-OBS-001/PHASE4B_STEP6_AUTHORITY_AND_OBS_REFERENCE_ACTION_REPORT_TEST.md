# CASE-OBS-001 Phase4-B Step6 Authority Action + OBS Reference Action Report Test

## Purpose

Make report / visualization output show two action layers without breaking the Authority Chain:

```text
Authority Action
= selected by Authority Pattern Layer
= primary recommendation

OBS Reference Action
= selected from Reference Evidence Layer
= supporting audit / explanation only
= not a risk engine
```

This step does **not** change Risk calculation.

```text
Measurement -> Evidence -> Pattern -> Risk -> Classification -> Authority Action
                                      \-> OBS Reference Explanation / Audit Action
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4b_step6_authority_obs_reference_action_report_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/action/build_v05_action_recommendation.py
chmod +x pipelines/commerce/visualization/build_case_obs_001_figures.R
chmod +x pipelines/commerce/validation/validate_v05_action_layer_report_expression.py
chmod +x pipelines/commerce/validation/validate_case_obs_001_figures.py
bash -n deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
python -m py_compile pipelines/commerce/action/build_v05_action_recommendation.py pipelines/commerce/validation/validate_v05_action_layer_report_expression.py pipelines/commerce/validation/validate_case_obs_001_figures.py
```

## Smoke test

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

## Expected logs

```text
[PATTERN_ACTION_CATALOG]
... authority_actions=3 reference_obs_actions>=1 action_is_risk_engine=0

[STEP 6.095]
Knowledge Base Layer: authority action + OBS reference action report validation

[ACTION_LAYER_REPORT]
authority_actions>=1 reference_obs_actions>=1
[OK] validate_v05_action_layer_report_expression passed

[CASE_OBS_001_FIGURES]
... fig05_recommended_action_matrix.png role=authority_reference_action_support
[OK] validate_case_obs_001_figures passed
```

## SQL checks

```sql
SELECT action_layer,
       action_catalog_source,
       COUNT(*) AS rows,
       MIN(action_rank) AS min_rank,
       MAX(action_rank) AS max_rank
FROM action_recommendation_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='source_wc_collection_missing'
GROUP BY action_layer, action_catalog_source;

SELECT action_rank,
       action_layer,
       action_catalog_source,
       action_type,
       recommended_action
FROM action_recommendation_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='source_wc_collection_missing'
ORDER BY action_rank;
```

## Completion criteria

- Authority action rows exist with `action_layer='authority_action'` and `action_catalog_source='authority_pattern_layer'`.
- OBS reference action rows exist with `action_layer='reference_obs_action'` and `action_catalog_source='obs_reference_layer'` for non-baseline OBS gap scenarios.
- All action rows have `action_is_risk_engine=0`.
- Figure 5 shows Authority Actions and OBS Reference Actions separately.
- `figure_manifest.json` contains `action_layer_summary.authority_actions` and `action_layer_summary.reference_obs_actions`.
- Pattern-driven Risk output remains unchanged.
