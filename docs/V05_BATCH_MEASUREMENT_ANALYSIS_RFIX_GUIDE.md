# v0.5 Batch Measurement → R Analysis Fix Guide

## 목적

WC Collection Missing 케이스에서 최종 semantic/action은 맞았지만, 배치 기준 측정/분석에서는 `behavior_distortion_score` 외의 지표가 충분히 반응하지 않는 문제가 있었다.

핵심 원인은 두 가지다.

1. `batch_behavior_distribution_day`는 비율 분포 중심이라 전체 수량 유실이 희석된다.
2. R batch 분석은 scalar metric delta(`event_count`, `pv`, `uv`, `visit`, `wc_hits`, `canonical_behavior_events`, `collection_gap_rate`)를 직접 읽지 않았다.

## 추가된 구조

### 1. `v05_batch_metric_delta_day`

새 scalar delta 테이블이다.

저장 지표:

- `event_count`
- `pv`
- `uv`
- `visit`
- `conversion_rate`
- `collector_capture_rate`
- `estimated_missing_rate`
- `web_hits`
- `wc_hits`
- `canonical_behavior_events`
- `collection_gap_rate`
- `canonical_gap_rate`
- `checkout_missing_rate`
- `product_missing_rate`
- `uv_gap_rate`

각 지표는 baseline 대비 다음 값을 가진다.

- `current_value`
- `baseline_value_avg`
- `baseline_value_std`
- `absolute_delta`
- `delta_rate`
- `z_score`
- `risk_score`
- `risk_status`
- `baseline_status`

### 2. `build_v05_batch_metric_delta_day.py`

`measurement_batch_day`, `v05_observability_measurement_day`, stage/canonical count를 읽어 scalar delta를 생성한다.

운영쉘 STEP 4.1에서 다음 순서로 실행된다.

```text
build_measurement_batch_day
build_v05_batch_behavior_distribution_day
baseline metric/distribution snapshot 생성(baseline scenario only)
build_v05_batch_metric_delta_day
```

### 3. R 분석 변경

#### `r_batch_behavior_analysis.R`

이제 아래 점수를 분리한다.

```text
behavior_distortion_score
conversion_distortion_score
session_fragmentation_score
mapping_risk_score
batch_quality_risk_score
```

WC 유실 시 기대 반응:

```text
behavior_distortion_score > 0
conversion_distortion_score > 0
session_fragmentation_score > 0
```

#### `build_v05_batch_distribution_analysis.R`

기존 비율 분포 변화뿐 아니라 scalar volume 변화도 같이 반영한다.

```text
ratio_shift_score
volume_shift_score
batch_distribution_score = max(ratio_shift_score, volume_shift_score)
```

#### `build_v05_batch_behavior_anomaly.R`

이제 batch score와 observability collection score를 함께 본다.

```text
batch_score
collection_score
anomaly_score = max(batch_score, collection_score)
```

## 테스트 방법

### 1. Baseline

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 baseline 0
```

기대:

```text
v05_batch_metric_delta_day max_score=0
r_batch_behavior_analysis overall=0
v05_batch_behavior_anomaly signal=none
unified risk stable
no action
```

### 2. WC Collection Missing

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 source_wc_collection_missing 0
```

기대:

```text
v05_batch_metric_delta_day max_score > 0
behavior_distortion_score > 0
conversion_distortion_score > 0
session_fragmentation_score > 0
batch_distribution_score > 0
anomaly_signal = observability_collection_anomaly
```

확인 SQL:

```sql
SELECT metric_scope, metric_name, current_value, baseline_value_avg, delta_rate, risk_score, risk_status
FROM v05_batch_metric_delta_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
  AND scenario_name='source_wc_collection_missing'
ORDER BY risk_score DESC, metric_scope, metric_name;

SELECT behavior_distortion_score,
       conversion_distortion_score,
       session_fragmentation_score,
       dominant_batch_signal,
       overall_batch_behavior_score,
       analysis_reason
FROM r_batch_behavior_analysis_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
  AND scenario_name='source_wc_collection_missing';
```

## 리셋 정책

`reset_v05_commerce_pipeline.sh`에 다음 신규 런타임 테이블 삭제가 추가되었다.

```text
v05_batch_metric_delta_day
v05_batch_behavior_anomaly_day
```

Baseline Reference 계열은 계속 보존한다.

```text
v05_baseline_metric_snapshot_day
v05_baseline_reference_run_day
v05_baseline_distribution_snapshot_day
```
