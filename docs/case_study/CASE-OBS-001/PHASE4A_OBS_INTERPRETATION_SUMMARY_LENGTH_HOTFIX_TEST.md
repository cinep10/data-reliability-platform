# CASE-OBS-001 Phase4-A OBS Interpretation Summary Length Hotfix

## Purpose

Fix `Data too long for column 'analysis_summary'` in `build_v05_observability_interpretation.R` for targeted iOS app/SDK scenarios.

The previous dedupe patch correctly merged duplicate root-cause candidates, but merged summaries could exceed the deployed MariaDB column length.

## Apply

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o case_obs_phase4a_obs_interpretation_summary_length_hotfix.zip
chmod +x pipelines/commerce/analytics/build_v05_observability_interpretation.R
```

## Direct retest

```bash
Rscript pipelines/commerce/analytics/build_v05_observability_interpretation.R \
  --db-host 127.0.0.1 --db-port 3306 --db-user nethru --db-pass nethru1234 --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --run-id 693 \
  --source-gen-run-id 686 \
  --scenario-name source_ios_app_version_collection_missing \
  --baseline-window 30d \
  --top-n 20
```

Expected:

```text
[OK] build_v05_observability_interpretation ...
```

## Pipeline retest

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_ios_app_version_collection_missing 0
```

Expected:

```text
[STEP 6.06] Reference Evidence Layer: OBS interpretation / root-cause confidence support
[OK] build_v05_observability_interpretation ...
```

## Notes

- This patch does not change scoring logic.
- It only truncates long text fields before insert:
  - `analysis_summary`
  - `detail_json`
