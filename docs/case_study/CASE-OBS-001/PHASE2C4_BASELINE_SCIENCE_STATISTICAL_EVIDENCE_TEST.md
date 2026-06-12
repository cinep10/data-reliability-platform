# CASE-OBS-001 Phase2-C4 Baseline Science Statistical Evidence Test

## 목적

Phase2-C4는 Baseline Science 결과를 독립 산출물로 끝내지 않고, 기존 분석 체계가 참조할 수 있는 공통 통계 evidence로 변환한다.

핵심 원칙:

```text
Baseline Science = 공통 기준 계층
v0.4 batch analytics = batch measurement를 baseline-aware하게 해석
OBS analytics = observability measurement를 baseline-aware하게 해석
v0.5 reliability analysis = Behavior/Transaction/State reconciliation measurement를 baseline-aware하게 해석
```

중요: v0.5 reliability analysis는 OBS 분석 결과를 참조하지 않는다. v0.5는 `v05_reconciliation_measurement_day` 기반의 `reconciliation_measurement` evidence만 참조한다.

## 적용

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c4_baseline_science_stat_evidence_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x deploy/backfill_v05_obs_baseline_mac_host.sh
chmod +x deploy/reset_v05_commerce_pipeline_mac_host.sh
chmod +x deploy/truncate_v05_runtime_tables_mac_host.sh
chmod +x pipelines/commerce/analytics/build_v05_baseline_science_statistical_evidence.R
```

## 1일 Smoke

```bash
/opt/homebrew/bin/bash \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

기대 로그:

```text
[STEP 4.147] CASE-OBS-001 Phase2-C4 baseline science statistical evidence: batch/observability
[OK] build_v05_baseline_science_statistical_evidence rows=...
[OK] validate_v05_baseline_science_statistical_evidence passed

[STEP 5.1] CASE-OBS-001 Phase2-C4 baseline science statistical evidence: reconciliation
[OK] build_v05_baseline_science_statistical_evidence rows=...
[OK] validate_v05_baseline_science_statistical_evidence passed

[build_v05_reliability_analysis.R] ... stat=... sig=...
```

## 직접 실행: batch + OBS evidence

```bash
Rscript pipelines/commerce/analytics/build_v05_baseline_science_statistical_evidence.R \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --baseline-window 30d \
  --baseline-scenario baseline \
  --domains batch,observability \
  --min-sample-days 3
```

## 직접 실행: v0.5 reconciliation evidence

`v05_reconciliation_measurement_day` 생성 이후 실행한다.

```bash
Rscript pipelines/commerce/analytics/build_v05_baseline_science_statistical_evidence.R \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --baseline-window 30d \
  --baseline-scenario baseline \
  --domains reconciliation \
  --min-sample-days 3
```

## 검증

```bash
python -m pipelines.commerce.validation.validate_v05_baseline_science_statistical_evidence \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --baseline-window 30d \
  --domains batch_metric_delta,observability_expected,reconciliation_measurement \
  --allow-missing-domain \
  --allow-low-sample
```

## DB 확인 SQL

```sql
SELECT evidence_domain,
       COUNT(*) AS row_count,
       COUNT(DISTINCT metric_name) AS metric_count,
       MAX(statistical_score) AS max_score,
       MAX(z_score) AS max_z,
       MAX(historical_percentile) AS max_percentile,
       SUM(control_limit_breach) AS breach_count,
       MAX(co_movement_score) AS max_co_movement
FROM v05_baseline_science_statistical_evidence_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
GROUP BY evidence_domain
ORDER BY evidence_domain;
```

```sql
SELECT metric_scope,
       metric_name,
       risk_score,
       z_score,
       historical_percentile,
       control_limit_breach,
       statistical_score,
       statistical_significance
FROM v05_batch_metric_delta_day
WHERE profile_id='commerce_deliver'
  AND dt='2026-06-01'
ORDER BY statistical_score DESC
LIMIT 20;
```

```sql
SELECT reconciliation_gap_score,
       baseline_delta,
       statistical_evidence_score,
       max_z_score,
       max_historical_percentile,
       control_limit_breach_count,
       co_movement_score,
       statistical_significance
FROM reliability_analysis_result_day_v05
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
ORDER BY created_at DESC
LIMIT 1;
```

## PASS 기준

```text
1. v05_baseline_science_statistical_evidence_day row > 0
2. batch_metric_delta domain 생성
3. OBS baseline/expected가 있으면 observability_expected domain 생성
4. STEP 5 이후 reconciliation_measurement domain 생성
5. v05_batch_metric_delta_day enriched columns 조회 가능
6. r_batch_* / v05_batch_behavior_anomaly_day / reliability_analysis_result_day_v05에 statistical evidence fields 저장
7. baseline scenario에서는 최종 risk/action false positive 없음
```
