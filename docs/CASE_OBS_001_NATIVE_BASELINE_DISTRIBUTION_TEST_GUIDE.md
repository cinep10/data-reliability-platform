# CASE-OBS-001 Native Baseline/Distribution Test Guide

## 목적

이번 패키지는 CASE-OBS-001을 전용 overlay가 아니라 v0.5 본체의 baseline-aware analytics 경로에 흡수하는 것을 목표로 한다.

핵심 검증 흐름:

```text
baseline run
→ baseline metric/distribution snapshot 생성
→ WC collection missing anomaly run
→ current distribution vs baseline distribution 비교
→ R 공통 baseline 함수 기반 분석
→ observability analysis가 semantic/action 본체 입력으로 흡수
```

## 1. 설치

```bash
unzip v05_baseline_distribution_native_patch.zip
cd pkg_baseline_distribution_native
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform bash install_v05_baseline_distribution_native_patch.sh
```

## 2. Baseline Reference 테스트

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_case_obs_001_baseline_reference.sh 2026-05-28 0
```

확인 SQL:

```sql
SELECT metric_scope, metric_name, metric_value_avg, sample_days
FROM v05_baseline_metric_snapshot_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
ORDER BY metric_scope, metric_name;

SELECT dimension_name, dimension_value, baseline_ratio_avg, sample_days
FROM v05_baseline_distribution_snapshot_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
ORDER BY dimension_name, baseline_ratio_avg DESC
LIMIT 20;
```

## 3. WC 이상치 테스트

```bash
./deploy/run_case_obs_001_wc_anomaly_with_baseline.sh 2026-05-28 0
```

확인 SQL:

```sql
SELECT web_hits, wc_hits, collection_gap_rate, observability_signal_score, observability_risk_level
FROM v05_wc_collection_reconciliation_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
  AND scenario_name='source_wc_collection_missing'
ORDER BY run_id DESC
LIMIT 1;

SELECT dimension_name, dimension_value, current_ratio, baseline_ratio_avg, ratio_delta, distribution_shift_score, baseline_status
FROM v05_batch_behavior_distribution_compare_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
  AND scenario_name='source_wc_collection_missing'
ORDER BY distribution_shift_score DESC
LIMIT 20;

SELECT dominant_batch_anomaly, batch_behavior_risk_score, anomaly_status, anomaly_reason
FROM r_batch_behavior_anomaly_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
  AND scenario_name='source_wc_collection_missing'
ORDER BY run_id DESC
LIMIT 1;
```

## 4. 통합 테스트

```bash
./deploy/run_case_obs_001_baseline_then_anomaly_test.sh 2026-05-28 0
```

PASS 기준:

```text
Baseline metric snapshot row > 0
Baseline distribution snapshot row > 0
WC anomaly run에서 collection_gap_rate > 0.05
batch distribution compare row > 0
build_v05_batch_behavior_anomaly.R signal != none 또는 observability_collection_anomaly
semantic = WC Collection Completeness Risk / Operational Observability Distortion 계열
action = wc collector validation / web-wc reconciliation / observability KPI annotation 포함
```

## 5. 주요 변경 사항

- `v05_baseline_distribution_snapshot_day` 추가
- `v05_batch_behavior_distribution_compare_day` 추가
- `build_v05_batch_behavior_distribution_day.py`가 baseline comparison 인터페이스 지원
- `r_baseline_common_v05.R` 공통 함수 완성
- R 5종 분석 스크립트가 공통 baseline 함수를 사용
- `build_v05_batch_behavior_anomaly.R`가 observability / distribution / behavior analysis input을 함께 사용
- STEP 6.1 별도 adapter 제거: observability analysis가 본체 semantic/action 이전 입력으로 흡수
- smoke script의 `source_generation_result_summary.scenario_name` 조회 제거
