#!/usr/bin/env bash
set -euo pipefail
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB_USER="${DB_USER:-nethru}"; DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"; DB_NAME="${DB_NAME:-weblog}"; PROFILE_ID="${PROFILE_ID:-commerce_deliver}"
mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" <<SQL
SELECT 'v05_reconciliation_measurement_day' table_name, COUNT(*) rows FROM v05_reconciliation_measurement_day WHERE profile_id='${PROFILE_ID}';
SELECT 'reliability_analysis_result_day_v05' table_name, COUNT(*) rows FROM reliability_analysis_result_day_v05 WHERE profile_id='${PROFILE_ID}';
SELECT 'semantic_interpretation_day_v05' table_name, COUNT(*) rows FROM semantic_interpretation_day_v05 WHERE profile_id='${PROFILE_ID}';
SELECT 'unified_reliability_score_day_v05' table_name, COUNT(*) rows FROM unified_reliability_score_day_v05 WHERE profile_id='${PROFILE_ID}';
SELECT 'action_recommendation_day_v05' table_name, COUNT(*) rows FROM action_recommendation_day_v05 WHERE profile_id='${PROFILE_ID}';
SELECT 'v05_runtime_evidence_day' table_name, COUNT(*) rows FROM v05_runtime_evidence_day WHERE profile_id='${PROFILE_ID}';
SELECT 'v05_ml_prediction_day' table_name, COUNT(*) rows FROM v05_ml_prediction_day WHERE profile_id='${PROFILE_ID}';
SELECT 'v05_ai_validation_detail_day' table_name, COUNT(*) rows FROM v05_ai_validation_detail_day WHERE profile_id='${PROFILE_ID}';
SQL
echo "[OK] core v0.5 Grafana query tables are reachable"
