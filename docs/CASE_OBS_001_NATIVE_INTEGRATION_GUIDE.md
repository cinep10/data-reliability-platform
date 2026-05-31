# CASE-OBS-001 Native Observability Integration Guide

## 목적

이 패키지는 기존 `CASE-OBS-001`의 전용 overlay 구조를 줄이고, WC collection missing을 v0.5 본체의 `Operational Observability Reliability` 확장으로 흡수하기 위한 산출물입니다.

핵심 변경:

```text
기존: collector drop → observability signal → CASE-OBS-001 semantic/action overlay
개선: collector drop → observability measurement → R observability analysis → generic semantic/action
```

## 역할 분리

| Layer | 역할 |
|---|---|
| SQL | `v05_observability_measurement_day`, `r_v05_observability_analysis_day`, view 저장/조회 |
| Python | WC collector 실행, measurement materialization, trace materialization, action persistence |
| R | observability gap을 risk/semantic signal로 해석 |
| Shell | 순서와 파라미터 전달 |

## 주요 파일

```text
sql/036_v05_observability_measurement_schema_mariadb.sql
sql/035_v05_wc_collection_reconciliation_view_mariadb.sql
pipelines/commerce/observability/build_v05_observability_measurement_day.py
pipelines/commerce/analytics/build_v05_observability_reliability_analysis.R
pipelines/commerce/semantic/apply_v05_observability_semantic_interpretation.R
pipelines/commerce/action/build_v05_observability_action_recommendation.py
pipelines/commerce/trace/materialize_v05_observability_anomaly_trace.py
pipelines/commerce/validation/validate_case_obs_001_native.py
deploy/run_case_obs_001_native_smoke.sh
```

## 설치

```bash
unzip case_obs_001_native_integration.zip
cd case_obs_001_native_integration
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform ./install_obs001_native_integration.sh
```

설치 스크립트는 기존 파일을 `.bak_obs001_native_<timestamp>`로 백업합니다.

## 실행

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_case_obs_001_native_smoke.sh 2026-05-28 0
```

강도 조정:

```bash
WC_MISSING_BASE_RATE=0.10 \
WC_MISSING_CHECKOUT_RATE=0.25 \
WC_MISSING_PRODUCT_RATE=0.18 \
WC_MISSING_IOS_SAFARI_RATE=0.30 \
./deploy/run_case_obs_001_native_smoke.sh 2026-05-28 0
```

## 검증 SQL

```sql
SELECT web_hits,
       wc_hits,
       canonical_behavior_events,
       collection_gap_rate,
       observability_signal_score,
       observability_risk_level,
       recommended_semantic_risk
FROM v05_wc_collection_reconciliation_day
WHERE scenario_name='source_wc_collection_missing'
ORDER BY updated_at DESC
LIMIT 5;
```

```sql
SELECT dominant_semantic_risk
FROM semantic_interpretation_day_v05
WHERE scenario_name='source_wc_collection_missing'
ORDER BY updated_at DESC
LIMIT 5;
```

```sql
SELECT action_rank, action_type, recommended_action
FROM action_recommendation_day_v05
WHERE scenario_name='source_wc_collection_missing'
ORDER BY action_rank;
```

## PASS 기준

```text
web_hits > 0
wc_hits < web_hits
collection_gap_rate >= 0.10
canonical_behavior_events ~= wc_hits
recommended_semantic_risk = WC Collection Completeness Risk
semantic_interpretation_day_v05.dominant_semantic_risk = WC Collection Completeness Risk
action contains wc collector validation / web-wc reconciliation check / observability KPI annotation
```

## 중요한 설계 판단

### 1. `--drop-rate 0.00` 문제 해결

runner가 다음 파라미터를 명시적으로 collector에 전달합니다.

```bash
--wc-missing-base-rate
--wc-missing-checkout-rate
--wc-missing-product-rate
--wc-missing-ios-safari-rate
```

### 2. baseline 의미 분리

CASE-OBS-001은 `temporal_baseline`이 아니라 `same_run_evidence_baseline`입니다.

```text
WebServer Source = reality baseline
WC / canonical behavior = observed telemetry
```

### 3. Phase2 PASS 의미 분리

`canonical_behavior_events_exists: PASS`는 구조 PASS입니다. OBS-001에서는 별도 `observability_collection_gap` 검증이 필요합니다.

### 4. overlay 제거 방향

`apply_case_obs_001_semantic_action` 대신 다음 generic chain을 사용합니다.

```text
v05_observability_measurement_day
→ r_v05_observability_analysis_day
→ semantic_interpretation_day_v05
→ action_recommendation_day_v05
```
