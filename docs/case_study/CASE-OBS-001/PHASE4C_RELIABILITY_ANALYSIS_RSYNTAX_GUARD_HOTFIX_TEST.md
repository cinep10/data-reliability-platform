# Phase4-C Reliability Analysis R Syntax Guard Hotfix Test

## Purpose

Fix a syntax error introduced by the baseline evidence v2 guard patch:

```text
Error: unexpected symbol in:
"}
.phase4c_conversion_gap_for_guard"
```

The executable inline R guard is removed from `build_v05_reliability_analysis.R`. Baseline-zero semantics remain enforced in `validate_v05_authority_evidence_layer.py` by excluding normality evidence (`traffic_preservation_score`) from anomaly-signal checks.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase4c_reliability_analysis_rsyntax_guard_hotfix.zip
chmod +x deploy/apply_phase4c_reliability_analysis_rsyntax_guard_hotfix.py

PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform \
  python deploy/apply_phase4c_reliability_analysis_rsyntax_guard_hotfix.py

Rscript -e "parse(file='pipelines/commerce/analytics/build_v05_reliability_analysis.R'); cat('R parse OK\n')"
python -m py_compile pipelines/commerce/validation/validate_v05_authority_evidence_layer.py
```

## Baseline smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-06-01 baseline 0
```

Expected:

```text
[AUTHORITY_EVIDENCE_LAYER] ... baseline=0.000000 ... criticality=0.000000
traffic_preservation_score=1.000000
[OK] validate_v05_authority_evidence_layer passed
```

`traffic_preservation_score=1.0` is normality evidence and must not fail baseline-zero validation.
