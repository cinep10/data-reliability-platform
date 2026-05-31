#!/usr/bin/env bash
set -euo pipefail
DT="${1:-2026-05-28}"
JOURNEYS="${2:-0}"
PROJECT_ROOT="${PROJECT_ROOT:-/home/dwkim_nethru/data/etl/data-reliability-platform}"
cd "$PROJECT_ROOT"
export RUN_V05_OBSERVABILITY_NATIVE="${RUN_V05_OBSERVABILITY_NATIVE:-true}"
export WC_MISSING_BASE_RATE="${WC_MISSING_BASE_RATE:-0.18}"
export WC_MISSING_CHECKOUT_RATE="${WC_MISSING_CHECKOUT_RATE:-0.35}"
export WC_MISSING_PRODUCT_RATE="${WC_MISSING_PRODUCT_RATE:-0.22}"
export WC_MISSING_IOS_SAFARI_RATE="${WC_MISSING_IOS_SAFARI_RATE:-0.40}"

echo "[CASE-OBS-001] native smoke start dt=$DT journeys=$JOURNEYS"
echo "[CASE-OBS-001] wc rates base=$WC_MISSING_BASE_RATE checkout=$WC_MISSING_CHECKOUT_RATE product=$WC_MISSING_PRODUCT_RATE ios_safari=$WC_MISSING_IOS_SAFARI_RATE"
./deploy/run_v05_reliability_pipeline_commerce.sh "$DT" source_wc_collection_missing "$JOURNEYS"

echo "[CASE-OBS-001] locating latest run/source_gen ids"
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB_USER="${DB_USER:-nethru}"; DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"; DB_NAME="${DB_NAME:-weblog}"; PROFILE_ID="${PROFILE_ID:-commerce_deliver}"
read -r RUN_ID SOURCE_GEN_RUN_ID < <(mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" -N -B -e "SELECT run_id, source_gen_run_id FROM v05_observability_measurement_day WHERE profile_id='$PROFILE_ID' AND target_date='$DT' AND scenario_name='source_wc_collection_missing' ORDER BY updated_at DESC LIMIT 1;")
echo "[CASE-OBS-001] run_id=$RUN_ID source_gen_run_id=$SOURCE_GEN_RUN_ID"
"${VENV_PYTHON:-$PROJECT_ROOT/.venv/bin/python3}" -m pipelines.commerce.validation.validate_case_obs_001_native \
  --db-host "$DB_HOST" --db-port "$DB_PORT" --db-user "$DB_USER" --db-pass "$DB_PASSWORD" --db-name "$DB_NAME" \
  --profile-id "$PROFILE_ID" --target-date "$DT" --scenario-name source_wc_collection_missing --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID"

echo "[CASE-OBS-001] reconciliation review"
mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" -e "SELECT web_hits,wc_hits,canonical_behavior_events,collection_gap_rate,observability_signal_score,observability_risk_level,recommended_semantic_risk FROM v05_wc_collection_reconciliation_day WHERE profile_id='$PROFILE_ID' AND target_date='$DT' AND scenario_name='source_wc_collection_missing' AND run_id=$RUN_ID AND source_gen_run_id=$SOURCE_GEN_RUN_ID;"
