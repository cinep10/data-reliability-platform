# v0.5 R Style Refactor Guide

## 목적

이번 패키지는 기존 `v05_obs_r_reengineer_patch`의 기능을 유지하면서, RStudio에서 장기 유지보수하기 쉬운 코드 스타일로 R 파일 전체를 재정리합니다.

핵심 원칙은 다음과 같습니다.

```text
1 변수 = 1 줄
Arguments / Database Connection / Load Data / Analysis / Save Result / Console Output 섹션 분리
공통 함수는 r_baseline_common_v05.R에 집중
운영쉘에서 호출되는 R 파일은 모두 같은 구조를 따름
```

## 적용 대상 R 파일

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

## 코드 구조 표준

각 실행 R 스크립트는 아래 섹션 순서를 따릅니다.

```r
# ------------------------------------------------------------------
# Arguments
# ------------------------------------------------------------------

profile_id <- arg_value(args, "--profile-id")
dt         <- arg_value(args, "--dt")

run_id <- as.integer(
  arg_value(args, "--run-id", "0")
)

scenario_name <- arg_value(
  args,
  "--scenario-name",
  "baseline"
)

baseline_window <- arg_value(
  args,
  "--baseline-window",
  "30d"
)

# ------------------------------------------------------------------
# Database Connection
# ------------------------------------------------------------------

con <- connect_db(args)
on.exit(DBI::dbDisconnect(con), add = TRUE)
```

## 기능상 변경점

이번 패키지는 스타일만 바꾸지 않습니다. 직전 패키지의 관측성 보정도 유지합니다.

```text
Baseline: stable / no action 유지
WC collection missing: Observability HIGH가 Unified Risk에서 지나치게 낮아지지 않도록 floor 반영
WC Collection Completeness Risk semantic/action 유지
```

## 테스트

```bash
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 baseline 0
./deploy/run_v05_reliability_pipeline_commerce.sh 2026-05-28 source_wc_collection_missing 0
```

기대 결과:

```text
baseline -> stable / no action
source_wc_collection_missing -> WC Collection Completeness Risk / warning 이상 / WC action 3개
```
