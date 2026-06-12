# CASE-OBS-001 Phase2-C4 Operating Script Fix Test

## Purpose

Ensure `run_v05_reliability_pipeline_commerce_mac_host.sh` actually executes `build_v05_baseline_science_statistical_evidence.R` so that:

- `v05_baseline_science_statistical_evidence_day` is populated.
- `v05_batch_metric_delta_history_day` is populated.
- `STEP 4.147` runs for batch/observability evidence.
- `STEP 5.1` runs for reconciliation evidence.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase2c4_operating_script_fix.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

## Check script integration

```bash
grep -n "078_v05\|079_v05\|4.147\|5.1\|build_v05_baseline_science_statistical_evidence" \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
```

Expected:

```text
078_v05_baseline_science_statistical_evidence_mariadb.sql
079_v05_batch_metric_delta_history_mariadb.sql
STEP 4.147
STEP 5.1
build_v05_baseline_science_statistical_evidence.R
```

## One-day smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

Expected log excerpts:

```text
[STEP 4.147] CASE-OBS-001 Phase2-C4 baseline science statistical evidence: batch/observability
[OK] build_v05_baseline_science_statistical_evidence ... domains=batch_metric_delta,observability_expected
[STEP 5.1] CASE-OBS-001 Phase2-C4 baseline science statistical evidence: reconciliation
[OK] build_v05_baseline_science_statistical_evidence ... domains=reconciliation_measurement
```

## DB checks

```sql
SELECT evidence_domain, COUNT(*) rows
FROM v05_baseline_science_statistical_evidence_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
GROUP BY evidence_domain;

SELECT COUNT(*) rows
FROM v05_batch_metric_delta_history_day
WHERE profile_id='commerce_deliver'
  AND metric_date='2026-06-01';
```

## Notes

This patch fixes operating-script orchestration only. It assumes the C4 SQL/R/validator files from the final C4 patch are already present.
