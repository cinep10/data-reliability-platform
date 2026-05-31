# v0.5 Batch Time/Correlation Interface Fix Guide

## 목적

테스트방 리뷰 기준으로 WC Collection Missing은 최종 semantic/action은 정상 수렴했지만, 배치 기준 R 분석 중 일부가 아직 `v05_batch_metric_delta_day`를 충분히 사용하지 못했다.

특히 아래 두 스크립트는 기존 구조상 비율 분포 또는 neutral correlation에 가깝게 동작했다.

```text
pipelines/analytics/r/r_time_pattern_anomaly_v04.R
pipelines/analytics/r/r_correlation_anomaly_v04.R
```

이번 수정은 두 스크립트가 배치 scalar delta와 observability delta를 함께 읽도록 인터페이스를 보강한다.

---

## 수정 대상

### 1. `build_v05_batch_metric_delta_day.py`

보강 내용:

- `canonical_behavior_events`가 observability row 생성 시점에는 0일 수 있으므로, 실행 시점에 다시 table count fallback을 수행한다.
- `collection_gap_rate`, `canonical_gap_rate`는 fallback count 이후 항상 재계산한다.
- `wc_hits`, `canonical_behavior_events`는 historical baseline이 없더라도 같은 run의 `web_hits`를 expected source baseline으로 사용한다.
- 따라서 WC 유실 시 아래 지표도 risk score를 갖는다.

```text
event_count
pv
uv
visit
wc_hits
canonical_behavior_events
collection_gap_rate
canonical_gap_rate
checkout_missing_rate
product_missing_rate
uv_gap_rate
```

---

### 2. `r_time_pattern_anomaly_v04.R`

기존 문제:

- hour 분포의 ratio shift만 보면 WC 유실처럼 전체 수량이 균일하게 감소하는 문제는 작게 보인다.

보강 내용:

- `v05_batch_behavior_distribution_compare_day`의 hour row를 읽는다.
- `current_count` vs `baseline_count_avg`의 count delta를 계산한다.
- `v05_batch_metric_delta_day`의 batch volume score를 함께 반영한다.

최종 score:

```text
max(
  hour ratio shift,
  hour count delta,
  batch volume score * 0.70
)
```

기대:

```text
baseline -> score=0, PASS
WC missing -> hour ratio 변화가 작아도 volume 기반 score가 WARN/FAIL 쪽으로 반응
```

---

### 3. `r_correlation_anomaly_v04.R`

기존 문제:

- 단일 일자 smoke에서는 true correlation을 계산할 수 없어 neutral row만 저장했다.
- 그래서 WC 유실로 여러 metric이 동시에 흔들리는 현상이 correlation layer에 표현되지 않았다.

보강 내용:

- `v05_batch_metric_delta_day`와 `r_batch_behavior_analysis_day`를 읽는다.
- 각 metric risk score 간 pairwise coupled score를 계산한다.
- 단일 일자에서는 통계적 correlation이 아니라 `co-movement diagnostic score`로 저장한다.

최종 score 예시:

```text
sqrt(event_count_delta_score * collection_gap_score)
sqrt(pv_delta_score * canonical_gap_score)
sqrt(behavior_distortion_score * conversion_distortion_score)
```

기대:

```text
baseline -> max_score=0, PASS
WC missing -> collection/event/pv 관련 pair score가 함께 상승
```

---

## 테스트 방법

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 baseline 0
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 source_wc_collection_missing 0
```

## 확인 SQL

```sql
SELECT metric_scope, metric_name, current_value, baseline_value_avg,
       delta_rate, risk_score, risk_status, baseline_status
FROM v05_batch_metric_delta_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
  AND scenario_name='source_wc_collection_missing'
ORDER BY risk_score DESC;
```

```sql
SELECT metric_name, observed_value, delta_ratio, anomaly_score,
       anomaly_status, analysis_reason
FROM r_metric_time_pattern_anomaly_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
  AND scenario_name='source_wc_collection_missing'
ORDER BY anomaly_score DESC;
```

```sql
SELECT metric_pair, corr_value, corr_delta, anomaly_score,
       anomaly_status, analysis_reason
FROM r_metric_correlation_anomaly_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
  AND scenario_name='source_wc_collection_missing'
ORDER BY anomaly_score DESC
LIMIT 20;
```

## 리셋 테이블 확인

현재 로그 기준으로 신규 테이블은 이미 reset 대상에 포함되어 있다.

```text
v05_batch_behavior_anomaly_day
v05_batch_metric_delta_day
r_metric_time_pattern_anomaly_day
r_metric_correlation_anomaly_day
```

추가로 새 테이블을 만들지 않았으므로 이번 패키지는 reset DDL을 변경하지 않는다.
