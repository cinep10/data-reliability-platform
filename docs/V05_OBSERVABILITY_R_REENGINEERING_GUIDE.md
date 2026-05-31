# v0.5 Observability Risk + R Reengineering Guide

## 목적

이번 패키지는 두 가지 문제를 동시에 해결한다.

1. `Observability Risk = HIGH`인데 `Unified Risk = LOW`로 과도하게 희석되는 문제를 수정한다.
2. v0.5 포트폴리오 엔진 역할을 하는 R 분석 코드를 유지보수 가능한 구조로 재정리한다.

## 핵심 보정 로직

### 이전 흐름

```text
WebServer 정상
→ WC Collection 21.39% 유실
→ Observability Risk 0.915 HIGH
→ Semantic = WC Collection Completeness Risk
→ Unified Risk 0.269 LOW
```

이 흐름의 문제는 Semantic/Action은 올바른데, 최종 Unified Risk가 LOW로 낮아 운영 판단에서 과소평가될 수 있다는 점이다.

### 수정 흐름

```text
WebServer 정상
→ WC Collection 유실
→ v05_observability_measurement_day
→ r_v05_observability_analysis_day
→ semantic_interpretation_day_v05.observability_semantic_score
→ unified_risk_score_day_v05 observability floor 적용
→ WARNING 이상으로 승격
→ WC collector / web-wc reconciliation / KPI annotation action 유지
```

## Unified Risk 보정 규칙

`build_v05_unified_risk_score.R`에 아래 원칙을 추가했다.

```text
if observability_score >= 0.75:
    unified risk >= max(0.35, observability_score * 0.45)
    cap = 0.55
```

따라서 이번 테스트처럼 `observability_score = 0.915`이면 최소 약 `0.412`가 보장되어 `warning`으로 승격된다.

이 보정은 의도적으로 `critical`까지 올리지 않는다. WC Collection Missing은 실제 거래 실패가 아니라 KPI/관측 의사결정 리스크이기 때문이다.

## R 리엔지니어링 원칙

### 공통 함수

`pipelines/analytics/r/r_baseline_common_v05.R`에 다음 공통 함수를 정리했다.

```text
parse_cli_args / arg_value
connect_db
query_df / execute_sql
table_exists / table_columns / column_exists
read_scoped_table / read_first_scoped_row
insert_schema_aware / delete_scoped_rows
pick_number / pick_character
clamp01 / risk_level / score_status
```

### 코드 스타일

기존의 압축된 R 코드를 다음 방향으로 전면 정리했다.

```text
입력 인자 파싱
DB 연결
입력 테이블 로드
측정값 추출
점수 계산
스키마 호환 insert
로그 출력
```

각 단계가 함수명과 변수명으로 읽히도록 구성했다. 외부 패키지 설치 실패를 피하기 위해 `dplyr` 의존성은 강제하지 않고, base pipe `|>`와 tidy-style dataframe 흐름을 사용했다.

## 포함 R 파일

```text
pipelines/analytics/r/r_baseline_common_v05.R
pipelines/analytics/r/r_batch_behavior_analysis.R
pipelines/analytics/r/build_v05_batch_distribution_analysis.R
pipelines/analytics/r/build_v05_batch_behavior_anomaly.R
pipelines/analytics/r/r_time_pattern_anomaly_v04.R
pipelines/analytics/r/r_correlation_anomaly_v04.R
pipelines/analytics/r/r_risk_metric_distribution_day.R
pipelines/analytics/r/r_risk_threshold_profile_v2.R
pipelines/commerce/analytics/build_v05_reliability_analysis.R
pipelines/commerce/analytics/build_v05_observability_reliability_analysis.R
pipelines/commerce/semantic/build_v05_semantic_interpretation.R
pipelines/commerce/score/build_v05_unified_risk_score.R
```

## 테스트 방법

### 1. 설치

```bash
unzip v05_obs_r_reengineer_patch.zip
cd v05_obs_r_reengineer_pkg
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform bash deploy/install_v05_obs_r_reengineer.sh
```

### 2. Baseline 검증

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 baseline 0
```

기대값:

```text
dominant_semantic_risk = None
overall_risk_score = 0
final_risk_level = stable
action = no action
```

### 3. WC Collection Missing 검증

```bash
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 source_wc_collection_missing 0
```

기대값:

```text
collection_gap_rate ≈ 0.213857
observability_overall_score ≈ 0.915
semantic = WC Collection Completeness Risk
unified risk >= 0.35
final_risk_level = warning 또는 high
actions = wc collector validation / web-wc reconciliation check / observability KPI annotation
```

### 4. 확인 SQL

```sql
SELECT dominant_semantic_risk, observability_semantic_score
FROM semantic_interpretation_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
ORDER BY run_id DESC
LIMIT 5;

SELECT overall_risk_score, final_risk_level, score_payload_json
FROM unified_reliability_score_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
ORDER BY run_id DESC
LIMIT 5;
```

## 개략 설명

```text
원천 변화 없음
  - Customer Journey / WebServer Source = 정상

수집 계층 유실
  - WC collector에서 일부 event drop

관측 차이 측정
  - web_hits vs wc_hits gap 계산

R Observability 분석
  - collection/canonical/UV/stage gap을 score로 변환

Semantic 해석
  - WC Collection Completeness Risk 생성

Unified Score
  - observability floor로 LOW 과소평가 방지

Action
  - collector 검증, Web-WC reconciliation, KPI dashboard annotation
```
