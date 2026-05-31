#!/usr/bin/env bash
set -euo pipefail
DT="${1:?target date required}"; JOURNEYS="${2:-0}"
PROJECT_ROOT="${PROJECT_ROOT:-/home/dwkim_nethru/data/etl/data-reliability-platform}"
cd "$PROJECT_ROOT"
export RESET_BEFORE_RUN="${RESET_BEFORE_RUN:-true}"
export PRESERVE_BASELINE_REFERENCE="${PRESERVE_BASELINE_REFERENCE:-true}"
export RUN_V05_OBSERVABILITY_NATIVE="${RUN_V05_OBSERVABILITY_NATIVE:-true}"
export BASELINE_MODE="temporal_baseline"
export BASELINE_WINDOW="${BASELINE_WINDOW:-30d}"
echo "[CASE-OBS-001][BASELINE] Step 1/3 run baseline scenario dt=$DT journeys=$JOURNEYS"
./deploy/run_v05_reliability_pipeline_commerce.sh "$DT" baseline "$JOURNEYS"
echo "[CASE-OBS-001][BASELINE] Step 2/3 build baseline metric snapshot"
"${VENV_PYTHON:-$PROJECT_ROOT/.venv/bin/python3}" -m pipelines.commerce.baseline.build_v05_baseline_metric_snapshot_day \
  --db-host "${DB_HOST:-127.0.0.1}" --db-port "${DB_PORT:-3306}" --db-user "${DB_USER:-nethru}" --db-pass "${DB_PASSWORD:-${DB_PASS:-nethru1234}}" --db-name "${DB_NAME:-weblog}" \
  --profile-id "${PROFILE_ID:-commerce_deliver}" --target-date "$DT" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline --include-target-date --truncate-target
echo "[CASE-OBS-001][BASELINE] Step 3/3 build baseline distribution snapshot"
"${VENV_PYTHON:-$PROJECT_ROOT/.venv/bin/python3}" -m pipelines.commerce.baseline.build_v05_baseline_distribution_snapshot_day \
  --db-host "${DB_HOST:-127.0.0.1}" --db-port "${DB_PORT:-3306}" --db-user "${DB_USER:-nethru}" --db-pass "${DB_PASSWORD:-${DB_PASS:-nethru1234}}" --db-name "${DB_NAME:-weblog}" \
  --profile-id "${PROFILE_ID:-commerce_deliver}" --target-date "$DT" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline --include-target-date --truncate-target
mysql -h "${DB_HOST:-127.0.0.1}" -P "${DB_PORT:-3306}" -u "${DB_USER:-nethru}" -p"${DB_PASSWORD:-${DB_PASS:-nethru1234}}" "${DB_NAME:-weblog}" -e "SELECT 'metric' kind, COUNT(*) cnt FROM v05_baseline_metric_snapshot_day WHERE profile_id='${PROFILE_ID:-commerce_deliver}' AND target_date='$DT' UNION ALL SELECT 'distribution', COUNT(*) FROM v05_baseline_distribution_snapshot_day WHERE profile_id='${PROFILE_ID:-commerce_deliver}' AND target_date='$DT';"
echo "[DONE] CASE-OBS-001 baseline reference built dt=$DT window=$BASELINE_WINDOW"
