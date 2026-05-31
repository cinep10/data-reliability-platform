# CASE-OBS-001 Time Distribution / Baseline Distribution / Correlation Fix

## 반영 내용

1. `build_v05_batch_behavior_distribution_day.py`
   - `hour` dimension을 명시적으로 생성합니다.
   - `canonical_events`에 시간 컬럼이 없으면 `stg_event_batch`, `stg_wc_log_hit`, `stg_webserver_log_hit` 순서로 fallback합니다.
   - 실행 로그에 `dims=...hour...` 및 dimension별 source가 표시됩니다.

2. `run_v05_reliability_pipeline_commerce.sh`
   - 기본 운영쉘의 STEP 4.1에서 distribution 생성 시 baseline 옵션을 전달합니다.
   - baseline scenario 실행 시 `build_v05_baseline_distribution_snapshot_day`를 자동 실행합니다.

3. `r_correlation_anomaly_v04.R`
   - 실제 테이블이 `metric_pair/corr_value/baseline_corr_value/corr_delta/anomaly_score/anomaly_status` 구조일 때도 동작합니다.
   - 이전 패치의 `pair_key` 컬럼 의존을 제거했습니다.

## 테스트 순서

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_case_obs_001_baseline_then_anomaly_test.sh 2026-05-28 0
```

## 확인 SQL

```sql
SELECT dimension_name, COUNT(*) rows
FROM batch_behavior_distribution_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
GROUP BY dimension_name;
```

`hour`가 반드시 포함되어야 합니다.

```sql
SELECT *
FROM r_metric_correlation_anomaly_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
ORDER BY created_at DESC
LIMIT 5;
```

`pair_key` 오류 없이 `metric_pair` 기준 row가 생성되어야 합니다.
