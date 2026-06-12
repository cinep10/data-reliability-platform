# v0.5 Mac Host Baseline / Source Partial / Reset Fix Guide

## 목적

이 패치는 Mac Mini Host 전환 후 발견된 세 가지 문제를 수정한다.

1. Baseline 실행에서 R Batch Evidence Layer가 `0.200001 / WARN / batch_behavior_distortion`을 생성하는 문제
2. `source_partial_missing` 실행 시 WC collector에 `--runtime-mode source_partial_missing`이 전달되어 실패하는 문제
3. Reset/Truncate 수행 후 `v05_baseline_*` 또는 `v05_batch_score_contribution_day`가 기대대로 정리되지 않는 문제

## 수정 요약

### 1. Baseline R Batch Evidence Suppression

Baseline은 기준 데이터를 만드는 실행이다. 따라서 baseline 자체에서 발생하는 미세한 baseline snapshot/self-reference noise는 evidence WARN으로 남기지 않는다.

수정 대상:

- `pipelines/analytics/r/r_batch_behavior_analysis.R`
- `pipelines/analytics/r/build_v05_batch_distribution_analysis.R`
- `pipelines/analytics/r/build_v05_batch_behavior_anomaly.R`

기대 결과:

```text
scenario=baseline
R Batch Behavior overall=0
Distribution max_score=0
Batch Behavior Anomaly signal=none score=0
```

### 2. source_partial_missing Collector Runtime Fix

`source_partial_missing`은 source file mutation 단계에서 이미 적용된다. WC collector는 이 경우 정상 collector mode로 실행되어야 한다.

수정 전:

```text
--runtime-mode source_partial_missing
```

수정 후:

```text
source_runtime_mode=source_partial_missing
collector_runtime_mode=none
```

`wc_collection_missing`일 때만 collector에 다음이 전달된다.

```text
--runtime-mode wc_collection_missing
--wc-missing-base-rate ...
```

### 3. Reset / Truncate 정리 정책

기본 정책은 기존과 동일하다.

```text
Baseline Reference = preserve
ML/AI outputs = preserve
```

다만 날짜별 완전 초기화를 위해 optional flag를 추가했다.

#### Reset에서 baseline reference 삭제

```bash
RESET_BASELINE_REFERENCE=true \
/opt/homebrew/bin/bash deploy/reset_v05_commerce_pipeline_mac_host.sh 2026-06-01
```

#### Truncate에서 baseline reference 삭제

```bash
/opt/homebrew/bin/bash deploy/truncate_v05_runtime_tables_mac_host.sh \
  --target-date 2026-06-01 \
  --preserve-baseline-reference false
```

## 적용 방법

```bash
unzip v05_mac_host_runtime_reset_rfix.zip
cd v05_mac_host_runtime_reset_rfix_pkg

export PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
export DB_HOST=127.0.0.1
export DB_PORT=3306
export DB_USER=nethru
export DB_PASSWORD='nethru1234'
export DB_NAME=weblog

/opt/homebrew/bin/bash deploy/install_v05_mac_host_runtime_reset_rfix.sh
```

## 테스트 순서

### 1. Baseline 재테스트

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform

/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

확인 SQL:

```sql
SELECT
  behavior_distortion_score,
  conversion_distortion_score,
  session_fragmentation_score,
  batch_overall_analysis_score,
  dominant_batch_signal,
  analysis_status
FROM r_batch_behavior_analysis_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-06-01'
  AND scenario_name='baseline'
ORDER BY run_id DESC
LIMIT 1;
```

기대:

```text
batch_overall_analysis_score = 0
dominant_batch_signal = none
analysis_status = PASS
```

### 2. source_partial_missing 재테스트

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_partial_missing 0
```

기대 로그:

```text
source_runtime_mode=source_partial_missing collector_runtime_mode=none
[collector_wc_log_hit_v04] runtime_mode=none ... dropped=0
```

주의: `source_partial_missing`의 row loss는 collector가 아니라 source mutation 단계에서 확인한다.

```text
rows_before=36460 rows_after=32085
```

### 3. Reset 검증

기본 reset은 baseline reference를 보존한다.

```bash
/opt/homebrew/bin/bash deploy/reset_v05_commerce_pipeline_mac_host.sh 2026-06-01
```

완전 날짜 초기화가 필요하면 baseline reference까지 삭제한다.

```bash
RESET_BASELINE_REFERENCE=true \
/opt/homebrew/bin/bash deploy/reset_v05_commerce_pipeline_mac_host.sh 2026-06-01
```

검증 SQL:

```sql
SELECT 'v05_baseline_metric_snapshot_day' AS table_name, COUNT(*) cnt
FROM v05_baseline_metric_snapshot_day
WHERE profile_id='commerce_deliver' AND target_date='2026-06-01'
UNION ALL
SELECT 'v05_baseline_distribution_snapshot_day', COUNT(*)
FROM v05_baseline_distribution_snapshot_day
WHERE profile_id='commerce_deliver' AND target_date='2026-06-01'
UNION ALL
SELECT 'v05_batch_score_contribution_day', COUNT(*)
FROM v05_batch_score_contribution_day
WHERE profile_id='commerce_deliver' AND dt='2026-06-01';
```

## 운영 기준

Mac Host 기준 기본 실행 환경:

```text
PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
SOURCE_LOG_ROOT=/Volumes/EXTERNAL_USB/dev/log/logdata/source
LOG_DIR=/Volumes/EXTERNAL_USB/dev/log/runtime
DB_HOST=127.0.0.1
```
