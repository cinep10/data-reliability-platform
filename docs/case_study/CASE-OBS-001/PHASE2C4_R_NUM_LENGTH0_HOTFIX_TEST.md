# CASE-OBS-001 Phase2-C4 R length-0 optional-column hotfix test

## Purpose

Fix `build_v05_baseline_science_statistical_evidence.R` failure:

```text
Error in `$<-.data.frame`(`*tmp*`, "baseline_mean", value = logical(0)) :
  replacement has 0 rows, data has 1
```

## Cause

Some source tables do not always expose optional columns such as `baseline_mean` for every domain/schema version. In R, accessing a missing column can produce a length-0 vector. The previous `num()` helper returned length-0 for that case, which cannot be assigned to a one-row evidence frame.

## Fix

`num()` now returns the provided default when input is `NULL` or length-0.

## Smoke rerun

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

Then rerun the normal pipeline from the failed point or full smoke.
