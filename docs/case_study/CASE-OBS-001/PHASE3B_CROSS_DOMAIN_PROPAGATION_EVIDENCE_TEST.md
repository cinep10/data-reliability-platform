# CASE-OBS-001 Phase3-B Cross-domain Propagation Evidence Test

## Purpose

Add v0.5-native propagation evidence on top of completed Statistical Evidence and OBS Interpretation.

This phase explains **why** a WC collection issue is risky across the v0.5 chain:

```text
Source/Observability anomaly
  -> Behavior impact
  -> Transaction attribution gap
  -> Conversion/KPI distortion
  -> State/reconciliation drift
  -> Semantic/Risk/Action
```

Core outputs:

```text
affected_domains
propagation_strength
reconciliation_confidence
dominant_propagation_path
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase3b_cross_domain_propagation_patch.zip
chmod +x deploy/*.sh
chmod +x pipelines/commerce/analytics/build_v05_cross_domain_propagation_evidence.R
chmod +x pipelines/commerce/analytics/build_v05_reliability_analysis.R
chmod +x pipelines/commerce/validation/validate_v05_cross_domain_propagation_evidence.py
```

## Baseline smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

Expected logs:

```text
[STEP 5.2] CASE-OBS-001 Phase3-B cross-domain propagation evidence
[OK] build_v05_cross_domain_propagation_evidence ... affected_domains=none propagation=0.000000 ...
[OK] validate_v05_cross_domain_propagation_evidence passed
[build_v05_reliability_analysis.R] ... propagation=0.000000 affected_domains=[] ...
```

## WC missing smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

Expected logs:

```text
[STEP 5.2] CASE-OBS-001 Phase3-B cross-domain propagation evidence
[OK] build_v05_cross_domain_propagation_evidence ... affected_domains=behavior,transaction,conversion,attribution ... propagation=... level=...
[OK] validate_v05_cross_domain_propagation_evidence passed
[build_v05_reliability_analysis.R] ... propagation=... affected_domains=... reconciliation_confidence=...
```

## Direct validation

Baseline:

```bash
python -m pipelines.commerce.validation.validate_v05_cross_domain_propagation_evidence \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --allow-baseline-no-propagation
```

Anomaly:

```bash
python -m pipelines.commerce.validation.validate_v05_cross_domain_propagation_evidence \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_wc_collection_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --require-propagation \
  --min-propagation 0.10 \
  --min-confidence 0.30 \
  --min-affected-domains 1
```

## SQL checks

```sql
SELECT scenario_name,
       affected_domains,
       affected_domain_count,
       behavior_impact_score,
       transaction_impact_score,
       state_impact_score,
       conversion_impact_score,
       attribution_impact_score,
       propagation_strength,
       propagation_level,
       reconciliation_confidence,
       dominant_propagation_path
FROM v05_cross_domain_propagation_evidence_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
ORDER BY created_at DESC
LIMIT 10;
```

```sql
SELECT scenario_name,
       baseline_delta,
       affected_domains,
       affected_domain_count,
       cross_domain_propagation_strength,
       cross_domain_propagation_level,
       reconciliation_confidence,
       dominant_propagation_path
FROM reliability_analysis_result_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
ORDER BY created_at DESC
LIMIT 10;
```

## Completion criteria

- Baseline scenario creates a propagation evidence row with no/near-zero propagation.
- `source_wc_collection_missing` creates affected domains and non-zero propagation strength.
- `reconciliation_confidence` is non-zero and reflects sample/evidence sufficiency.
- `build_v05_reliability_analysis.R` reflects propagation columns in `reliability_analysis_result_day_v05`.
- Semantic/risk/action flow remains unchanged except that reliability payload now explains cross-domain propagation evidence.
