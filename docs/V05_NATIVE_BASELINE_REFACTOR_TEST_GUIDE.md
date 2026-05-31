# v0.5 Native Baseline Refactor Test Guide

## 목적

이번 패키지는 `baseline_dt` 혼재를 줄이고 `baseline_mode + baseline_window` 기준으로 measurement/R 분석을 통일합니다.

핵심 수정:

- `build_measurement_realism_day.py`가 `--baseline-mode`, `--baseline-window`, `--source-gen-run-id`를 수용합니다.
- `build_v05_batch_behavior_distribution_day.py`가 `hour` dimension을 항상 시도합니다.
- baseline run에서 `build_v05_baseline_distribution_snapshot_day.py`가 운영쉘에 포함됩니다.
- `r_time_pattern_anomaly_v04.R`, `r_correlation_anomaly_v04.R`는 실제 테이블 컬럼 기준으로 insert합니다.
- collector는 `--runtime-mode none|wc_collection_missing`을 지원합니다.

## 설치

```bash
unzip v05_native_baseline_refactor.zip
cd v05_native_baseline_refactor_pkg
PROJECT_ROOT=/home/dwkim_nethru/data/etl/data-reliability-platform bash deploy/install_v05_native_baseline_refactor.sh
```

## 테스트 1: baseline reference 생성

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 baseline 0
```

기대 로그:

```text
[collector_wc_log_hit_v04] runtime_mode=none ... dropped=0 ... wc_missing_rates=not_applied
[OK] build_v05_batch_behavior_distribution_day ... dims=...hour...
[OK] build_v05_baseline_distribution_snapshot_day ... rows>0
[R_TIME_PATTERN_SCORE_FIX_V9] ... status=PASS
[R_CORRELATION_SAFE_COR_FIX_V11] ... status=PASS
```

확인 SQL:

```sql
SELECT dimension_name, COUNT(*)
FROM batch_behavior_distribution_day
WHERE profile_id='commerce_deliver' AND dt='2026-05-28'
GROUP BY dimension_name;

SELECT dimension_name, COUNT(*)
FROM v05_baseline_distribution_snapshot_day
WHERE profile_id='commerce_deliver' AND target_date='2026-05-28'
GROUP BY dimension_name;
```

`hour`가 포함되어야 합니다.

## 테스트 2: WC collection missing

```bash
cd /home/dwkim_nethru/data/etl/data-reliability-platform
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 source_wc_collection_missing 0
```

기대 로그:

```text
[INFO] WC collection anomaly enabled: base=0.18 checkout=0.35 product=0.22 ios_safari=0.40
[collector_wc_log_hit_v04] runtime_mode=wc_collection_missing ... dropped>0 ... wc_missing_base_rate=0.18 ...
[MEASUREMENT_REALISM_COMPLETION] ... baseline_mode=temporal_baseline baseline_window=30d
```

확인 SQL:

```sql
SELECT web_hits,wc_hits,collection_gap_rate,observability_signal_score,observability_risk_level
FROM v05_wc_collection_reconciliation_day
WHERE profile_id='commerce_deliver' AND target_date='2026-05-28'
ORDER BY run_id DESC LIMIT 5;
```

## PASS 기준

- baseline: no action / low risk / collector dropped=0
- baseline distribution: `hour` 포함
- WC anomaly: `dropped > 0`, `collection_gap_rate > 0`
- R scripts: `time_bucket`, `pair_key`, `baseline-mode` 관련 argparse/insert 오류 없음
