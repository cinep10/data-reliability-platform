# CASE-OBS-001 Phase2-C4 Statistical Reliability Backfill Test

## 목적

7일/30일 backfill로 Baseline Science Statistical Evidence가 실제 통계 의미를 갖는지 확인한다.

검증 대상:

1. baseline / source_partial_missing / source_wc_collection_missing 시나리오가 모두 실행되는지
2. `v05_baseline_science_statistical_evidence_day`에 아래 도메인이 생성되는지
   - `batch_metric_delta`
   - `observability_expected`
   - `reconciliation_measurement`
3. v0.5 `build_v05_reliability_analysis.R`가 `reconciliation_measurement` evidence를 반영하는지
4. 7일/30일 history 누적 후 `sample_days`, z-score, percentile, control limit이 low-sample 상태를 벗어나는지
5. 각 날짜 실행 후 heavy source/canonical/runtime 테이블과 source files가 정리되는지

## 적용

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c4_statistical_backfill_patch.zip
chmod +x deploy/backfill_v05_statistical_reliability_mac_host.sh
chmod +x deploy/compact_v05_backfill_runtime_mac_host.sh
chmod +x pipelines/commerce/validation/validate_v05_statistical_backfill_summary.py
```

## 7일 backfill

```bash
/opt/homebrew/bin/bash \
  deploy/backfill_v05_statistical_reliability_mac_host.sh \
  --target-date 2026-06-01 \
  --days 7 \
  --scenarios baseline,source_partial_missing,source_wc_collection_missing \
  --compact-after-each-run true \
  --remove-source-files true
```

초기 검증은 low-sample 허용:

```bash
python -m pipelines.commerce.validation.validate_v05_statistical_backfill_summary \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenarios baseline,source_partial_missing,source_wc_collection_missing \
  --min-sample-days 3 \
  --allow-low-sample
```

7일 누적 후에는 low-sample 옵션 제거:

```bash
python -m pipelines.commerce.validation.validate_v05_statistical_backfill_summary \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenarios baseline,source_partial_missing,source_wc_collection_missing \
  --min-sample-days 3
```

## 30일 backfill

```bash
/opt/homebrew/bin/bash \
  deploy/backfill_v05_statistical_reliability_mac_host.sh \
  --target-date 2026-06-01 \
  --days 30 \
  --scenarios baseline,source_partial_missing,source_wc_collection_missing \
  --compact-after-each-run true \
  --remove-source-files true
```

30일 검증:

```bash
python -m pipelines.commerce.validation.validate_v05_statistical_backfill_summary \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenarios baseline,source_partial_missing,source_wc_collection_missing \
  --min-sample-days 7
```

## DB 확인 SQL

```sql
SELECT scenario_name, evidence_domain,
       COUNT(*) AS row_count,
       MIN(sample_days) AS min_sample_days,
       MAX(sample_days) AS max_sample_days,
       MAX(ABS(z_score)) AS max_abs_z,
       MAX(historical_percentile) AS max_percentile,
       SUM(CASE WHEN control_limit_breach=1 THEN 1 ELSE 0 END) AS breach_count,
       MAX(statistical_score) AS max_score
FROM v05_baseline_science_statistical_evidence_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name IN ('baseline','source_partial_missing','source_wc_collection_missing')
GROUP BY scenario_name, evidence_domain
ORDER BY scenario_name, evidence_domain;
```

```sql
SELECT scenario_name,
       statistical_evidence_reflected,
       statistical_evidence_row_count,
       statistical_evidence_raw_score,
       statistical_evidence_effective_score,
       statistical_significance_level
FROM reliability_analysis_result_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name IN ('baseline','source_partial_missing','source_wc_collection_missing')
ORDER BY scenario_name;
```

## PASS 기준

### Interface PASS

```text
STEP 4.147 실행
STEP 5.1 실행
batch_metric_delta rows > 0
observability_expected rows > 0
reconciliation_measurement rows > 0
reliability_analysis_result_day_v05.statistical_evidence_reflected = 1
```

### 통계 의미 PASS

```text
7일/30일 후 max_sample_days >= min-sample-days
baseline scenario: effective score suppressed 또는 near-zero
source_partial_missing / source_wc_collection_missing: statistical score, percentile, control-limit 중 하나 이상 반응
```

### 용량 정리 PASS

```text
각 date/scenario 실행 후 source/raw/canonical/stage/runtime heavy table이 compact 로그에서 DELETE됨
source log directory가 remove-source-files=true일 때 삭제됨
statistical/baseline evidence tables는 보존됨
```
