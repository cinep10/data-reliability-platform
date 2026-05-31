# CASE-OBS-001 / v0.5 Body Patch Test Manual

## 목적

이번 패치는 CASE-OBS-001 전용 overlay를 줄이고, v0.5 본체에 다음 계층을 추가한다.

```text
Baseline Reference Layer
+ Observability Measurement Layer
+ Native Observability R Analysis
+ Generic Observability Semantic/Action
```

## 핵심 수정 요약

1. `v05_baseline_metric_snapshot_day`, `v05_baseline_reference_resolution_day` 추가.
2. reset shell에서 baseline reference table을 기본 보존.
3. `build_measurement_realism_day.py`의 `source_event_count` fallback을 `stg_webserver_log_hit`로 보강.
4. OBS-001 measurement 실행 위치를 canonical 생성 후로 이동하여 `canonical_behavior_events`가 0으로 남지 않게 수정.
5. `validate_case_obs_001_native.py`에서 `updated_at` 컬럼이 없을 때도 실패하지 않도록 수정.
6. `test_v05_phase2_canonical_mapping.py`에 OBS-001 전용 의미 검증을 추가하되, 기존 구조 PASS와 관측 유실 PASS를 분리.

## 설치

```bash
unzip v05_body_obs001_patch.zip
cd v05_body_obs001_patch
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform ./install_v05_body_obs001_patch.sh
```

## 기본 smoke

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_case_obs_001_native_smoke.sh 2026-05-28 0
```

## 기대 결과

### 1. Collector 파라미터가 로그에 명시되어야 함

```text
--wc-missing-base-rate 0.18
--wc-missing-checkout-rate 0.35
--wc-missing-product-rate 0.22
--wc-missing-ios-safari-rate 0.40
```

### 2. Observability measurement

```sql
SELECT web_hits,
       wc_hits,
       canonical_behavior_events,
       collection_gap_rate,
       web_to_canonical_gap_rate,
       baseline_mode,
       delta_source_type
FROM v05_observability_measurement_day
WHERE scenario_name='source_wc_collection_missing'
ORDER BY run_id DESC
LIMIT 1;
```

기대:

```text
web_hits > wc_hits
canonical_behavior_events ~= wc_hits
collection_gap_rate > 0.10
baseline_mode = same_run_evidence_baseline
```

### 3. measurement_realism_day source_event_count

```sql
SELECT source_event_count,
       baseline_source_event_count,
       canonical_event_count,
       direct_completeness_delta,
       delta_source_type
FROM measurement_realism_day
WHERE scenario_name='source_wc_collection_missing'
ORDER BY run_id DESC
LIMIT 1;
```

기대:

```text
source_event_count > 0
canonical_event_count > 0
```

### 4. Baseline reference 보존 확인

reset 전후에 아래가 삭제되지 않아야 한다.

```sql
SELECT COUNT(*) FROM v05_baseline_metric_snapshot_day;
SELECT COUNT(*) FROM v05_baseline_reference_resolution_day;
```

reset dry-run:

```bash
DRY_RUN=true ./deploy/reset_v05_commerce_pipeline.sh 2026-05-28 2026-05-28
```

로그에 다음이 보여야 한다.

```text
BASELINE_REFERENCE_POLICY=preserve
```

### 5. Native validation

`run_case_obs_001_native_smoke.sh` 마지막에 다음이 나와야 한다.

```text
[OK] CASE-OBS-001 native validation passed
```

## PASS 기준

```text
STRUCTURAL PASS: v0.5 Phase1~4 validation passed
OBSERVABILITY PASS: web_hits > wc_hits, collection_gap_rate > threshold
CANONICAL OBSERVED PASS: canonical_behavior_events ~= wc_hits
SEMANTIC PASS: WC Collection Completeness Risk
ACTION PASS: wc collector validation / web-wc reconciliation check / observability KPI annotation
BASELINE PASS: same_run_evidence_baseline resolution row 생성
```

## REVIEW 기준

```text
baseline metric sample 부족
batch distribution baseline missing
semantic은 맞지만 unified risk가 low인 경우
```

## HARD FAIL 기준

```text
source_event_count = 0
v05_observability_measurement_day 미생성
canonical_behavior_events = 0 after canonical step
updated_at unknown column 오류 재발
baseline reference table reset 삭제
```
