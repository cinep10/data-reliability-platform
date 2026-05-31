# CASE-OBS-001 Baseline/Observability Native Fix Test Guide

## 목적

이번 패치는 CASE-OBS-001을 전용 overlay가 아니라 v0.5 본체의 baseline-aware analytics + native observability input으로 흡수하기 위한 보완이다.

핵심 보완은 다음이다.

1. baseline 실행과 WC 이상치 실행 로그를 명확히 분리한다.
2. batch behavior distribution의 current/baseline 비교 테이블을 만든다.
3. `r_baseline_common_v05.R`를 R 5종 스크립트의 공통 baseline interface로 사용한다.
4. time/correlation R 스크립트가 결과 테이블에 실제 row를 저장한다.
5. `build_v05_observability_reliability_analysis.R`의 실제 DB 컬럼명 불일치를 수정한다.
6. smoke script는 `source_generation_result_summary.scenario_name`을 조회하지 않고 `stg_webserver_log_hit`와 semantic 결과에서 run/source_gen id를 찾는다.

## 적용

```bash
unzip v05_observability_baseline_fix_patch.zip
cd v05_observability_baseline_fix_patch
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform bash install_v05_observability_baseline_fix_patch.sh
```

## 테스트 1: Baseline Reference 생성

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_case_obs_001_baseline_reference.sh 2026-05-28 0
```

확인 SQL:

```sql
SELECT COUNT(*) FROM v05_baseline_metric_snapshot_day
WHERE profile_id='commerce_deliver' AND target_date='2026-05-28';

SELECT COUNT(*) FROM v05_baseline_distribution_snapshot_day
WHERE profile_id='commerce_deliver' AND target_date='2026-05-28';

SELECT dimension_name, COUNT(*)
FROM v05_baseline_distribution_snapshot_day
WHERE profile_id='commerce_deliver' AND target_date='2026-05-28'
GROUP BY dimension_name;
```

기대:

- baseline scenario는 `runtime_mode=none`으로 collector 실행
- WC missing rate 옵션은 baseline collector command에 표시되지 않음
- baseline semantic은 `None`, action은 `no action`
- baseline metric/distribution snapshot row 생성

## 테스트 2: WC Collection Missing 이상치

```bash
./deploy/run_case_obs_001_wc_anomaly_with_baseline.sh 2026-05-28 0
```

기대 로그:

```text
[INFO] WC collection anomaly enabled: base=0.18 checkout=0.35 product=0.22 ios_safari=0.40
runtime_mode=wc_collection_missing
source_rows=33527
wc_rows=26357
collection_gap_rate 약 0.213857
```

확인 SQL:

```sql
SELECT web_hits, wc_hits, collection_gap_rate,
       observability_signal_score, observability_risk_level,
       recommended_semantic_risk
FROM v05_wc_collection_reconciliation_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-05-28'
ORDER BY run_id DESC
LIMIT 3;

SELECT dimension_name, MAX(distribution_shift_score), MAX(baseline_status)
FROM v05_batch_behavior_distribution_compare_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
GROUP BY dimension_name;

SELECT dominant_batch_anomaly, batch_anomaly_score, anomaly_status
FROM r_batch_behavior_anomaly_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
ORDER BY run_id DESC
LIMIT 3;

SELECT time_pattern_score, analysis_status
FROM r_metric_time_pattern_anomaly_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
ORDER BY run_id DESC
LIMIT 3;

SELECT correlation_delta_score, analysis_status
FROM r_metric_correlation_anomaly_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-05-28'
ORDER BY run_id DESC
LIMIT 3;
```

## 통합 테스트

```bash
./deploy/run_case_obs_001_baseline_then_anomaly_test.sh 2026-05-28 0
```

## PASS 기준

- baseline collector command에는 WC missing rate가 표시되지 않는다.
- WC anomaly collector command에는 WC missing rate가 표시된다.
- `v05_baseline_distribution_snapshot_day` row가 생성된다.
- `v05_batch_behavior_distribution_compare_day` row가 생성된다.
- `build_v05_batch_behavior_anomaly.R`가 `observability_collection_anomaly`를 생성한다.
- `r_metric_time_pattern_anomaly_day`, `r_metric_correlation_anomaly_day`에 row가 저장된다.
- `r_v05_observability_analysis_day` insert 시 `canonical_observability_gap_score` 오류가 발생하지 않는다.
- `source_generation_result_summary.scenario_name` 오류가 발생하지 않는다.

## 리셋 정책

`PRESERVE_BASELINE_REFERENCE=true`가 기본이다. 다음 테이블은 일반 scenario reset에서 삭제하지 않는 것이 원칙이다.

- `v05_baseline_metric_snapshot_day`
- `v05_baseline_distribution_snapshot_day`
- `v05_baseline_reference_run_day`

