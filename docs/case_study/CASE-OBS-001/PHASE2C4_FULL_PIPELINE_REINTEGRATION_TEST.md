# CASE-OBS-001 Phase2-C4 Full Pipeline Reintegration Test

## 적용

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c4_full_pipeline_reintegration_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## 적용 확인

```bash
grep -n "4.12\|4.13\|4.14\|4.145\|4.146\|4.147\|5.1\|078_v05\|RUN_V05_BASELINE_SCIENCE_STAT" \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## 1일 Smoke

```bash
/opt/homebrew/bin/bash \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

## 기대 로그

```text
[STEP 4.12] CASE-OBS-001 Phase2-B gap measurement layer
[STEP 4.13] CASE-OBS-001 Phase2-C1 baseline foundation
[STEP 4.14] CASE-OBS-001 Phase2-C2 expected metric model v1
[STEP 4.145] CASE-OBS-001 Phase2-C3 threshold calibration
[STEP 4.146] CASE-OBS-001 Phase2-C3 forecast interface validation
[STEP 4.147] CASE-OBS-001 Phase2-C4 baseline science statistical evidence: batch/observability
[STEP 5.1] CASE-OBS-001 Phase2-C4 baseline science statistical evidence: reconciliation
```

## DB 확인

```sql
SELECT evidence_domain,
       COUNT(*) AS row_count,
       MAX(statistical_score) AS max_score,
       MAX(ABS(z_score)) AS max_abs_z,
       MAX(historical_percentile) AS max_percentile
FROM v05_baseline_science_statistical_evidence_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='baseline'
GROUP BY evidence_domain;
```

기대 domain:

```text
batch_metric_delta
observability_expected
reconciliation_measurement
```

## 보정 포함 사항

- 현재 첨부 운영 스크립트 기준 누락된 073~078 DDL 적용을 복구한다.
- Phase2-B/C1/C2/C3/C4 운영 경로를 복구한다.
- `build_v05_batch_distribution_analysis.R` 호출에 `--source-gen-run-id`를 명시한다.
- STEP 5 이후 reconciliation statistical evidence를 생성해서 v0.5 reliability analysis 전에 참조 가능하게 한다.
