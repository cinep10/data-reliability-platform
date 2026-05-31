#!/usr/bin/env bash
set -euo pipefail
DT="${1:?target date required}"; JOURNEYS="${2:-0}"
PROJECT_ROOT="${PROJECT_ROOT:-/home/dwkim_nethru/data/etl/data-reliability-platform}"
cd "$PROJECT_ROOT"
export RESET_BEFORE_RUN="${RESET_BEFORE_RUN:-true}"
export PRESERVE_BASELINE_REFERENCE="${PRESERVE_BASELINE_REFERENCE:-true}"
export RUN_V05_OBSERVABILITY_NATIVE="true"
export BASELINE_MODE="temporal_baseline"
export BASELINE_WINDOW="${BASELINE_WINDOW:-30d}"
export WC_MISSING_BASE_RATE="${WC_MISSING_BASE_RATE:-0.18}"
export WC_MISSING_CHECKOUT_RATE="${WC_MISSING_CHECKOUT_RATE:-0.35}"
export WC_MISSING_PRODUCT_RATE="${WC_MISSING_PRODUCT_RATE:-0.22}"
export WC_MISSING_IOS_SAFARI_RATE="${WC_MISSING_IOS_SAFARI_RATE:-0.40}"
echo "[CASE-OBS-001][ANOMALY] WC collection missing enabled: base=$WC_MISSING_BASE_RATE checkout=$WC_MISSING_CHECKOUT_RATE product=$WC_MISSING_PRODUCT_RATE ios_safari=$WC_MISSING_IOS_SAFARI_RATE"
./deploy/run_v05_reliability_pipeline_commerce.sh "$DT" source_wc_collection_missing "$JOURNEYS"
PROFILE_ID="${PROFILE_ID:-commerce_deliver}"; DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB_USER="${DB_USER:-nethru}"; DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"; DB_NAME="${DB_NAME:-weblog}"
echo "[CASE-OBS-001][ANOMALY] locating latest IDs from stg_webserver_log_hit, not source_generation_result_summary.scenario_name"
RUN_ID=$(mysql -N -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" -e "SELECT MAX(run_id) FROM semantic_interpretation_day_v05 WHERE profile_id='$PROFILE_ID' AND target_date='$DT' AND scenario_name='source_wc_collection_missing';")
SOURCE_GEN_RUN_ID=$(mysql -N -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" -e "SELECT MAX(source_gen_run_id) FROM stg_webserver_log_hit WHERE profile_id='$PROFILE_ID' AND dt='$DT' AND scenario_name='source_wc_collection_missing';")
echo "[CASE-OBS-001][ANOMALY] run_id=$RUN_ID source_gen_run_id=$SOURCE_GEN_RUN_ID"
"${VENV_PYTHON:-$PROJECT_ROOT/.venv/bin/python3}" -m pipelines.commerce.validation.validate_case_obs_001_native \
  --db-host "$DB_HOST" --db-port "$DB_PORT" --db-user "$DB_USER" --db-pass "$DB_PASSWORD" --db-name "$DB_NAME" \
  --profile-id "$PROFILE_ID" --target-date "$DT" --scenario-name source_wc_collection_missing --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID"
