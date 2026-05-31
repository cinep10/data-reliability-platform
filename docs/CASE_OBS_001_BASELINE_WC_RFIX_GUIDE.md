# CASE-OBS-001 Baseline/WC R Fix Guide

## 목적

이번 보완은 다음 문제를 해결한다.

1. baseline 테스트인데 collector 로그에 WC missing rate가 계속 보여 baseline과 anomaly 차이가 흐려지는 문제
2. baseline reference 생성 중 distribution baseline이 아직 없어서 `BASELINE_MISSING_REVIEW`가 발생하는 문제
3. `r_time_pattern_anomaly_v04.R`가 실제 `r_metric_time_pattern_anomaly_day` 스키마와 다른 `time_bucket` 컬럼을 insert하는 문제

## 적용

```bash
unzip v05_baseline_wc_rfix.zip
cd v05_baseline_wc_rfix_pkg
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform bash install_v05_baseline_wc_rfix.sh
```

## 기대 로그 변화

### Baseline 실행

collector 명령에는 WC missing rate 인자가 붙지 않는다.

```text
--runtime-mode none --truncate-target
```

collector 결과도 다음처럼 나온다.

```text
runtime_mode=none ... dropped=0 ... wc_missing_rates=not_applied
```

### WC anomaly 실행

collector 명령에는 WC missing rate 인자가 붙는다.

```text
--runtime-mode wc_collection_missing
--wc-missing-base-rate 0.18
--wc-missing-checkout-rate 0.35
--wc-missing-product-rate 0.22
--wc-missing-ios-safari-rate 0.40
```

## 테스트 순서

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform

./deploy/run_case_obs_001_baseline_reference.sh 2026-05-28 0

./deploy/run_case_obs_001_wc_anomaly_with_baseline.sh 2026-05-28 0
```

## 확인 SQL

```sql
SELECT scenario_name, runtime_mode, dropped_count, affected_ratio
FROM v05_observability_anomaly_trace_day
WHERE target_date='2026-05-28'
ORDER BY created_at DESC
LIMIT 10;
```

```sql
SELECT scenario_name, dimension_name, baseline_status, MAX(distribution_shift_score) AS max_score
FROM v05_batch_behavior_distribution_compare_day
WHERE dt='2026-05-28'
GROUP BY scenario_name, dimension_name, baseline_status;
```

```sql
SELECT *
FROM r_metric_time_pattern_anomaly_day
WHERE dt='2026-05-28'
ORDER BY created_at DESC
LIMIT 10;
```

## 판정 기준

Baseline:

```text
collector dropped=0
wc_missing_rates=not_applied
dominant_semantic_risk=None
action=no action
distribution analysis status=PASS 또는 BASELINE_SELF_REFERENCE
```

WC anomaly:

```text
runtime_mode=wc_collection_missing
dropped > 0
collection_gap_rate > 0.1
batch_behavior_anomaly signal=observability_collection_anomaly
semantic=WC Collection Completeness Risk
```
