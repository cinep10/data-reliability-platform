# v0.5 Behavior Measurement Scope / v0.4 Batch Evidence 분리 가이드

## 1. 핵심 결론

`source_partial_missing`의 1차 검증은 v0.4 R Evidence가 아니라 v0.5 Behavior Measurement 기준으로 수행한다.

v0.5 Behavior Measurement는 다음을 확인한다.

- `canonical_behavior_events`
- `measurement_batch_day`
- `batch_behavior_distribution_day`
- `v05_batch_metric_delta_day`
- `v05_batch_score_contribution_day`
- `v05_batch_behavior_anomaly_day`

v0.4/R Evidence는 2차 설명 계층이다.

- `r_batch_behavior_analysis_day`
- `r_batch_distribution_analysis_day`
- `r_metric_time_pattern_anomaly_day`
- `r_metric_correlation_anomaly_day`

Legacy table은 authoritative 기준에서 제외한다.

- `batch_behavior_anomaly_day`
- `r_batch_behavior_anomaly_day`

## 2. source_partial_missing 해석 주의

`source_partial_missing`은 시뮬레이터 테스트에서는 원본 생성 건수와 mutation 후 건수를 모두 알고 있다. 예를 들어 로그에 다음처럼 남는다.

```text
rows_before=36460
rows_after=32085
```

하지만 실제 운영에서 원천 소스가 이미 유실되어 들어온 경우, 파이프라인 내부만으로는 "원래 몇 건이어야 했는지"를 직접 알 수 없다. 따라서 운영형 판단은 다음 방식이어야 한다.

```text
현재 관측 batch count
vs
baseline/reference snapshot
```

즉 `canonical_behavior_events 감소`, `measurement_batch_day 감소`라는 표현은 "절대 원천 진실 대비 감소"가 아니라 "baseline/reference 대비 관측량 감소"를 의미한다.

정리하면 다음과 같다.

| 구분 | 판단 방식 |
| --- | --- |
| 시뮬레이터 테스트 | mutation trace의 before/after로 감소 확인 가능 |
| 실제 운영 | baseline snapshot 대비 delta로만 감소 추정 가능 |
| WC collection missing | WebServer vs WC observability reconciliation로 직접 확인 가능 |
| source partial missing | baseline/reference 대비 behavior volume delta로 확인 |

## 3. source_partial_missing 1차 PASS 기준

아래 기준만 1차 PASS/FAIL 기준으로 사용한다.

```sql
SELECT COUNT(*) AS canonical_behavior_events
FROM canonical_behavior_events
WHERE profile_id = 'commerce_deliver'
  AND target_date = '2026-06-01'
  AND run_id = <RUN_ID>
  AND scenario_name = 'source_partial_missing';
```

```sql
SELECT event_count, pv, uv, visit
FROM measurement_batch_day
WHERE profile_id = 'commerce_deliver'
  AND dt = '2026-06-01'
  AND run_id = <RUN_ID>
  AND scenario_name = 'source_partial_missing';
```

```sql
SELECT MAX(risk_score) AS max_metric_delta_score
FROM v05_batch_metric_delta_day
WHERE profile_id = 'commerce_deliver'
  AND dt = '2026-06-01'
  AND run_id = <RUN_ID>
  AND scenario_name = 'source_partial_missing';
```

```sql
SELECT anomaly_signal, anomaly_score, anomaly_status, analysis_reason
FROM v05_batch_behavior_anomaly_day
WHERE profile_id = 'commerce_deliver'
  AND dt = '2026-06-01'
  AND run_id = <RUN_ID>
  AND scenario_name = 'source_partial_missing';
```

## 4. v0.4/R Evidence 2차 참고 기준

아래 테이블은 1차 PASS/FAIL 기준이 아니다. 원인 설명과 보조 진단에만 사용한다.

```sql
SELECT *
FROM r_batch_behavior_analysis_day
WHERE profile_id = 'commerce_deliver'
  AND dt = '2026-06-01'
  AND run_id = <RUN_ID>;
```

```sql
SELECT *
FROM r_batch_distribution_analysis_day
WHERE profile_id = 'commerce_deliver'
  AND dt = '2026-06-01'
  AND run_id = <RUN_ID>;
```

```sql
SELECT *
FROM r_metric_time_pattern_anomaly_day
WHERE profile_id = 'commerce_deliver'
  AND dt = '2026-06-01'
  AND run_id = <RUN_ID>;
```

```sql
SELECT *
FROM r_metric_correlation_anomaly_day
WHERE profile_id = 'commerce_deliver'
  AND dt = '2026-06-01'
  AND run_id = <RUN_ID>;
```

## 5. Distribution R Evidence 수정 기준

`r_batch_distribution_analysis_day`는 상태가 `FAIL`인데 risk score가 0으로 저장되면 안 된다.

수정 기준:

```text
distribution_risk_score = max(ratio_shift_score, volume_shift_score)
analysis_status = score_status(distribution_risk_score)
```

R insert는 다음 컬럼 alias를 모두 호환한다.

- `distribution_risk_score`
- `batch_distribution_score`
- `batch_distribution_risk_score`
- `max_distribution_shift_score`
- `max_distribution_score`

## 6. 검증 명령

```bash
python -m pipelines.commerce.validation.validate_v05_behavior_measurement_scope \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name source_partial_missing \
  --run-id <RUN_ID> \
  --source-gen-run-id <SOURCE_GEN_RUN_ID> \
  --require-anomaly-row
```

기대:

```text
[OK] v0.5 behavior measurement scope passed
```
