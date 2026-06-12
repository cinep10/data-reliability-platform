# CASE-OBS-001 Phase2-B Gap Measurement Layer

## Goal

Phase2-A proved that `app_platform`, `app_version`, and `sdk_version` propagate to:

- `stg_webserver_log_hit`
- `stg_wc_log_hit`
- `event_log_raw`
- `canonical_events`
- `canonical_behavior_events`

Phase2-B materializes direct gap measurements for Native/Web observability reliability.

## New tables

- `v05_obs_app_version_measurement_day`
- `v05_obs_sdk_version_measurement_day`
- `v05_obs_url_gap_day`
- `v05_obs_client_gap_day`
- `v05_obs_metric_gap_day`

## Apply schema

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
mysql -h 127.0.0.1 -P 3306 -u nethru -pnethru1234 weblog < sql/073_v05_obs_gap_measurement_layer_mariadb.sql
```

You can also let the Python materializer create the tables with `--apply-schema`.

## Run baseline pipeline first

```bash
/opt/homebrew/bin/bash \
  deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 baseline 0
```

From the pipeline log, capture:

- `RUN_ID`
- `SOURCE_GEN_RUN_ID`

Example from the latest review log:

```text
RUN_ID=518
SOURCE_GEN_RUN_ID=513
```

## Build gap measurements

```bash
python -m pipelines.commerce.observability.build_v05_obs_gap_measurement_layer \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id 518 \
  --source-gen-run-id 513 \
  --truncate-target \
  --apply-schema
```

Expected baseline result:

```text
[OK] build_v05_obs_gap_measurement_layer ... app_rows>0 sdk_rows>0 url_rows>0 client_rows>0 metric_rows>0
```

## Validate

```bash
python -m pipelines.commerce.validation.validate_v05_obs_gap_measurement_layer \
  --db-host 127.0.0.1 \
  --db-port 3306 \
  --db-user nethru \
  --db-pass nethru1234 \
  --db-name weblog \
  --profile-id commerce_deliver \
  --target-date 2026-06-01 \
  --scenario-name baseline \
  --run-id 518 \
  --source-gen-run-id 513 \
  --require-native
```

Expected baseline result:

```text
[PASS] v05_obs_app_version_measurement_day: rows > 0
[PASS] v05_obs_sdk_version_measurement_day: rows > 0
[PASS] v05_obs_url_gap_day: rows > 0
[PASS] v05_obs_client_gap_day: rows > 0
[PASS] v05_obs_metric_gap_day: rows > 0
[PASS] native app platforms present in app version measurement: ios_app/android_app
[PASS] baseline app version gap within tolerance: 0.000000
```

## Review SQL

```sql
SELECT app_platform, app_version, sdk_version,
       webserver_events, wc_events, missing_count, missing_rate,
       webserver_uv, wc_uv, uv_missing_rate,
       webserver_pv, wc_pv, pv_missing_rate
FROM v05_obs_app_version_measurement_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='baseline'
ORDER BY missing_rate DESC, webserver_events DESC;
```

```sql
SELECT app_platform, sdk_version,
       webserver_events, wc_events, missing_count, missing_rate,
       affected_app_versions
FROM v05_obs_sdk_version_measurement_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='baseline'
ORDER BY missing_rate DESC, webserver_events DESC;
```

```sql
SELECT dimension_type, dimension_value, metric_name,
       web_value, wc_value, missing_value, gap_rate, severity
FROM v05_obs_metric_gap_day
WHERE profile_id='commerce_deliver'
  AND target_date='2026-06-01'
  AND scenario_name='baseline'
ORDER BY gap_rate DESC, web_value DESC
LIMIT 50;
```

## Scope boundary

This patch does not add risk scoring, semantic interpretation, action recommendation, R analytics, visualization, or a version-specific missing scenario. It only builds the Measurement layer required before those steps.
