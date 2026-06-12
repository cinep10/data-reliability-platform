# v0.5 Behavior Scope Mapping Fix Guide

## 목적

이 패치는 `source_partial_missing` 테스트에서 v0.5 Behavior Measurement와 v0.4/R Evidence를 분리해서 검증하기 위한 보정이다.

핵심 수정은 다음과 같다.

```text
1. validate_v05_behavior_measurement_scope.py schema-aware 보정
2. v05_batch_behavior_anomaly_day.behavior_analysis_score 매핑 보정
3. dominant_contribution_family / metric tie-break 보정
4. Mac Host runner에 v0.5 behavior scope validation 자동 연결
```

---

## 배경

`source_partial_missing`은 원천 behavior source 자체가 감소한 시나리오다. 운영 파이프라인 내부에는 이미 유실된 원천이 들어오기 때문에, “원래 몇 건이어야 했는가”를 직접 측정할 수 없다.

따라서 1차 검증은 다음처럼 baseline/reference 대비 관측량 감소로 수행한다.

```text
baseline/reference event_count
  ↓ compare
current event_count / pv / uv / visit
  ↓
v05_batch_metric_delta_day risk_score
  ↓
v05_batch_behavior_anomaly_day anomaly_score
```

이 검증은 WebServer ↔ WC 직접 비교로 수집 유실을 설명하는 `source_wc_collection_missing`과 다르다.

---

## 테이블 역할 분리

### v0.5 Behavior Measurement Tables

이 테이블들이 `source_partial_missing`의 1차 PASS/FAIL 기준이다.

```text
measurement_batch_day
v05_batch_metric_delta_day
v05_batch_score_contribution_day
v05_batch_behavior_anomaly_day
```

### v0.4 / R Evidence Tables

이 테이블들은 2차 설명용 evidence다. 1차 PASS/FAIL 기준으로 사용하지 않는다.

```text
r_batch_behavior_analysis_day
r_batch_distribution_analysis_day
r_metric_time_pattern_anomaly_day
r_metric_correlation_anomaly_day
```

### Legacy / Deprecated

아래 테이블은 authoritative 기준에서 제외한다.

```text
batch_behavior_anomaly_day
r_batch_behavior_anomaly_day
```

---

## 주요 수정

### 1. Validator schema-aware 처리

기존 validator는 `measurement_batch_day`에서 아래 컬럼을 직접 조회했다.

```sql
SELECT event_count, pv, uv, visit
FROM measurement_batch_day
```

하지만 Mac Host 현재 스키마는 다음 컬럼명을 사용한다.

```text
event_count
pv_count
uv_count
visit_count
pageview_count
```

수정 후 validator는 아래 우선순위로 컬럼을 자동 선택한다.

```text
pv    -> pv, pv_count, pageview_count
uv    -> uv, uv_count
visit -> visit, visit_count, session_count
```

### 2. v05_batch_behavior_anomaly_day score 매핑

기존 증상:

```text
v05_batch_behavior_anomaly_day.anomaly_score = 0.608418
v05_batch_behavior_anomaly_day.batch_distribution_risk_score = 0.608418
v05_batch_behavior_anomaly_day.behavior_analysis_score = 0.0
```

수정 후:

```text
behavior_analysis_score
  <- max(
       r_batch_behavior_analysis_day.batch_overall_analysis_score,
       r_batch_behavior_analysis_day.overall_batch_behavior_score,
       behavior/session/conversion sub-score
     )

batch_distribution_risk_score
  <- r_batch_distribution_analysis_day.distribution_risk_score
```

### 3. dominant contribution tie-break

동일 score가 여러 family에 존재할 때 아래 순서로 대표 contribution을 선택한다.

```text
behavior_distortion
collection_effect
conversion_distortion
session_fragmentation
other
```

따라서 `pv`가 top metric이면 기본적으로 `behavior_distortion` family가 우선된다.

---

## 적용 방법

```bash
unzip v05_behavior_scope_mapping_fix.zip
cd v05_behavior_scope_mapping_fix_pkg

export PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
export DB_HOST=127.0.0.1
export DB_PORT=3306
export DB_USER=nethru
export DB_PASSWORD='nethru1234'
export DB_NAME=weblog

/opt/homebrew/bin/bash deploy/install_v05_behavior_scope_mapping_fix.sh
```

---

## 테스트 방법

### 1. Baseline

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform

/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

기대 결과:

```text
v05_batch_metric_delta_max_score = 0.000000
v05_batch_behavior_anomaly_max_score = 0.000000
[OK] v0.5 behavior measurement scope passed
```

### 2. source_partial_missing

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_partial_missing 0
```

기대 결과:

```text
canonical_behavior_events > 0
measurement_batch_day row exists
v05_batch_metric_delta_max_score > 0.05
v05_batch_behavior_anomaly_rows > 0
v05_batch_behavior_anomaly_max_score > 0.05
v05_batch_behavior_anomaly_behavior_score > 0.05
[OK] v0.5 behavior measurement scope passed
```

---

## 수동 검증 SQL

```sql
SELECT
  profile_id,
  dt,
  run_id,
  scenario_name,
  event_count,
  pv_count,
  uv_count,
  visit_count
FROM measurement_batch_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-06-01'
ORDER BY run_id DESC
LIMIT 5;
```

```sql
SELECT
  metric_scope,
  metric_name,
  current_value,
  baseline_value_avg,
  delta_rate,
  risk_score,
  risk_status
FROM v05_batch_metric_delta_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-06-01'
  AND scenario_name='source_partial_missing'
ORDER BY risk_score DESC
LIMIT 10;
```

```sql
SELECT
  anomaly_signal,
  anomaly_score,
  batch_distribution_risk_score,
  behavior_analysis_score,
  observability_collection_score,
  time_pattern_score,
  correlation_score,
  contribution_max_score,
  dominant_contribution_family,
  dominant_contribution_metric,
  anomaly_status
FROM v05_batch_behavior_anomaly_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-06-01'
  AND scenario_name='source_partial_missing'
ORDER BY run_id DESC
LIMIT 5;
```

---

## 판정 기준

`source_partial_missing` 1차 판정은 v0.5 Behavior Measurement 기준으로 한다.

```text
source/canonical behavior 감소
measurement_batch_day event_count 감소
v05_batch_metric_delta_day risk_score 반응
v05_batch_behavior_anomaly_day anomaly_score 반응
```

R evidence는 2차 설명 지표로만 사용한다.
