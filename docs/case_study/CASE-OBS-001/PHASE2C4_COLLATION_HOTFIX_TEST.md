# Phase2-C4 collation hotfix test

## Problem

`build_v05_baseline_science_statistical_evidence.R` can fail in the enrichment update step with:

```text
Illegal mix of collations (utf8mb4_uca1400_ai_ci,IMPLICIT) and (utf8mb4_general_ci,IMPLICIT) for operation '='
```

The root cause is a column-to-column join between C4 evidence and batch metric delta tables whose string columns may have different MariaDB collations.

## Fix

The batch metric enrichment join now applies explicit `COLLATE utf8mb4_general_ci` to string join keys:

- profile_id
- scenario_name
- baseline_window
- evidence_domain
- dimension_type / metric_scope
- metric_name

## Test

```bash
Rscript pipelines/commerce/analytics/build_v05_baseline_science_statistical_evidence.R \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id 636 \
  --source-gen-run-id 629 \
  --baseline-window 30d \
  --baseline-scenario baseline \
  --domains batch,observability \
  --min-sample-days 3
```

Expected:

```text
[OK] build_v05_baseline_science_statistical_evidence rows=...
```
