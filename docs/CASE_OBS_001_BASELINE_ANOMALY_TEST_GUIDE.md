# CASE-OBS-001 Baseline + WC Anomaly Test Guide

## 목적

이 테스트는 CASE-OBS-001을 단일 이상치 실행으로만 보지 않고, 아래 두 단계를 분리해서 검증한다.

```text
1. Baseline Reference 생성
2. WC collection missing 이상치 실행
```

핵심은 다음이다.

```text
Baseline Reference Table은 reset으로 삭제하지 않는다.
WC 이상치 실행은 baseline snapshot을 기준으로 얼마나 달라졌는지 해석한다.
OBS-001은 same-run evidence baseline(WebServer vs WC)도 동시에 사용한다.
```

---

## 1. 사전 적용

```bash
unzip v05_body_baseline_r_scripts_patch.zip
cd v05_body_baseline_r_scripts_patch
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform ./install_v05_body_baseline_r_scripts_patch.sh
```

---

## 2. Baseline Reference 생성 테스트

### 실행

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_case_obs_001_baseline_reference.sh 2026-05-28 0
```

### 기대 결과

```text
baseline scenario 정상 완주
v05_baseline_metric_snapshot_day 생성
Behavior Volume / Funnel / Observability metric snapshot 저장
```

### 확인 SQL

```sql
SELECT baseline_window,
       metric_scope,
       metric_name,
       metric_value_avg,
       sample_days
FROM v05_baseline_metric_snapshot_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
ORDER BY metric_scope, metric_name;
```

### PASS 기준

```text
baseline pipeline abort 없음
v05_baseline_metric_snapshot_day row > 0
sample_days > 0 또는 include-target-date baseline row 존재
```

---

## 3. WC Collection Missing 이상치 테스트

### 실행

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_case_obs_001_wc_anomaly_with_baseline.sh 2026-05-28 0
```

### 기대 결과

```text
WebServer source 정상
WC collector만 유실
collection_gap_rate > 0
R observability analysis high
semantic = WC Collection Completeness Risk 계열
action = wc collector / web-wc / dashboard annotation 계열
```

### 확인 SQL

```sql
SELECT web_hits,
       wc_hits,
       canonical_behavior_events,
       collection_gap_rate,
       web_to_canonical_gap_rate,
       observability_signal_score,
       observability_risk_level,
       recommended_semantic_risk
FROM v05_wc_collection_reconciliation_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
  AND scenario_name='source_wc_collection_missing';
```

```sql
SELECT dominant_semantic_risk
FROM semantic_interpretation_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
ORDER BY run_id DESC
LIMIT 1;
```

```sql
SELECT action_rank, action_type, recommended_action
FROM action_recommendation_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
ORDER BY run_id DESC, action_rank, action_type;
```

### PASS 기준

```text
web_hits > 0
wc_hits < web_hits
collection_gap_rate >= 0.05
canonical_behavior_events ~= wc_hits 또는 canonical 생성 후 web_to_canonical_gap_rate > 0
semantic이 WC Collection Completeness Risk / Operational Observability Distortion 계열
action에 wc collector validation / web-wc reconciliation / observability KPI annotation 포함
```

---

## 4. 통합 실행

Baseline 생성과 WC 이상치 실행을 한 번에 수행하려면 아래를 실행한다.

```bash
./deploy/run_case_obs_001_baseline_then_anomaly_test.sh 2026-05-28 0
```

---

## 5. 리셋 정책

`reset_v05_commerce_pipeline.sh`는 runtime/output 계층은 삭제하지만 아래 baseline reference table은 삭제하지 않는다.

```text
v05_baseline_metric_snapshot_day
v05_baseline_reference_run_day
```

즉 baseline은 이상치 비교 기준선이므로 runtime reset 대상이 아니다.

---

## 6. R 스크립트 변경 요약

### 7.1 r_batch_behavior_analysis.R

`baseline_metric_snapshot_day`를 읽고 volume/conversion delta를 계산한다. baseline이 없으면 current fallback을 조용히 쓰지 않고 `BASELINE_MISSING_REVIEW`로 남긴다.

### 7.2 build_v05_batch_distribution_analysis.R

baseline distribution이 없으면 current distribution fallback으로 0점 처리하지 않고 `BASELINE_MISSING_REVIEW` 상태를 기록한다.

### 7.3 build_v05_batch_behavior_anomaly.R

기존 `v05_source_anomaly_trace_day`뿐 아니라 `v05_observability_anomaly_trace_day`도 읽는다. WC 수집 유실은 source file mutation이 아니라 collection-layer anomaly로 해석한다.

### 7.4 r_time_pattern_anomaly_v04.R

`baseline_dt` 단일 비교 대신 최근 30일 hourly baseline을 우선 사용한다. baseline이 없으면 review status를 남긴다.

### 7.5 r_correlation_anomaly_v04.R

현재 hourly correlation과 최근 30일 baseline correlation delta를 비교한다. baseline이 없으면 review status를 남긴다.

---

## 2026-05-29 v4 Fix: schema-aware baseline builder

`measurement_batch_day` column names differ by v0.5 asset version. Some environments use `pv_count / uv_count / visit_count`, while older design notes used `pv / uv / visit`. The baseline builder is now schema-aware:

- `event_count` resolves from `event_count`, `semantic_event_count`, `batch_event_count`, `total_event_count`
- `pv` resolves from `pv`, `pv_count`, `pageview_count`, `page_view_count`, `pageviews`
- `uv` resolves from `uv`, `uv_count`, `unique_visitor_count`, `visitor_count`, `unique_visitors`
- `visit` resolves from `visit`, `visit_count`, `session_count`, `visits`, `sessions`
- observability `web_to_canonical_gap_rate` resolves from `web_to_canonical_gap_rate` or `canonical_gap_rate`

This prevents errors like:

```text
Unknown column 'pv' in 'SELECT'
```

### Expected baseline step

```bash
./deploy/run_case_obs_001_baseline_reference.sh 2026-05-28 0
```

PASS evidence:

```sql
SELECT metric_scope, metric_name, sample_days, metric_value_avg
FROM v05_baseline_metric_snapshot_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
ORDER BY metric_scope, metric_name;
```

If there are no prior historical baseline days and the baseline test builds the snapshot immediately after the same-day baseline run, use `--include-target-date` through the provided baseline reference shell. The resolver still marks missing historical baselines as review rather than silently using current anomaly data.
