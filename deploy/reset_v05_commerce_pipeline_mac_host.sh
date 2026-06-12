#!/usr/bin/env bash
set -euo pipefail

# Mac mini Host operation profile.
# Defaults:
# - PROJECT_ROOT=/Users/dwkim/dev/repo/data-reliability-platform
# - SOURCE_LOG_ROOT=/Users/dwkim/dev/log/logdata/source
# - DB_HOST=127.0.0.1
DT_FROM="${1:?dt_from required, e.g. 2026-05-21}"
DT_TO="${2:-$DT_FROM}"
SCENARIO_FILTER="${3:-all}"
RUN_ID_FILTER="${4:-all}"
SOURCE_GEN_RUN_ID_FILTER="${5:-all}"

PROJECT_ROOT="${PROJECT_ROOT:-/Users/dwkim/dev/repo/data-reliability-platform}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-nethru}"
DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"
DB_NAME="${DB_NAME:-weblog}"
PROFILE_ID="${PROFILE_ID:-commerce_deliver}"

RESET_SOURCE_FILES="${RESET_SOURCE_FILES:-false}"
RESET_CASE_OBS_FIGURES="${RESET_CASE_OBS_FIGURES:-false}"
CASE_OBS_ARTIFACT_ROOT="${CASE_OBS_ARTIFACT_ROOT:-$PROJECT_ROOT/artifacts/case_study}"
RESET_ML_FEATURES="${RESET_ML_FEATURES:-false}"
RESET_META="${RESET_META:-false}"
RESET_BASELINE_REFERENCE="${RESET_BASELINE_REFERENCE:-false}"
RESET_OBS_BASELINE_REFERENCE="${RESET_OBS_BASELINE_REFERENCE:-false}"
DRY_RUN="${DRY_RUN:-false}"

SOURCE_LOG_ROOT="${SOURCE_LOG_ROOT:-/Users/dwkim/dev/log/logdata/source}"

mysql_db(){ mysql -N -s -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" "$@"; }
mysql_info(){ mysql -N -s -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" information_schema "$@"; }
exists_table(){ [[ "$(mysql_info -e "SELECT COUNT(*) FROM tables WHERE table_schema='${DB_NAME}' AND table_name='$1';")" == "1" ]]; }
has_column(){ [[ "$(mysql_info -e "SELECT COUNT(*) FROM columns WHERE table_schema='${DB_NAME}' AND table_name='$1' AND column_name='$2';")" == "1" ]]; }
q(){ printf "%s" "$1" | sed "s/'/''/g"; }

date_where_for(){
  local t="$1"
  if has_column "$t" target_date; then echo "target_date BETWEEN '$(q "$DT_FROM")' AND '$(q "$DT_TO")'"
  elif has_column "$t" dt; then echo "dt BETWEEN '$(q "$DT_FROM")' AND '$(q "$DT_TO")'"
  elif has_column "$t" event_date; then echo "event_date BETWEEN '$(q "$DT_FROM")' AND '$(q "$DT_TO")'"
  else echo "1=1"
  fi
}

delete_scoped(){
  local t="$1"
  if ! exists_table "$t"; then echo "[SKIP] missing table $t"; return; fi
  local w="1=1"
  has_column "$t" profile_id && w="$w AND profile_id='$(q "$PROFILE_ID")'"
  local dw; dw="$(date_where_for "$t")"; [[ "$dw" != "1=1" ]] && w="$w AND $dw"

  if [[ "$SOURCE_GEN_RUN_ID_FILTER" != "all" ]] && has_column "$t" source_gen_run_id; then
    w="$w AND source_gen_run_id='$(q "$SOURCE_GEN_RUN_ID_FILTER")'"
  elif [[ "$RUN_ID_FILTER" != "all" ]] && has_column "$t" run_id; then
    w="$w AND run_id='$(q "$RUN_ID_FILTER")'"
  elif [[ "$SCENARIO_FILTER" != "all" ]] && has_column "$t" scenario_name; then
    echo "[WARN] fallback cleanup by scenario_name for $t because run_id/source_gen_run_id filter unavailable"
    w="$w AND scenario_name='$(q "$SCENARIO_FILTER")'"
  fi

  echo "[DELETE] $t WHERE $w"
  if [[ "$DRY_RUN" != "true" ]]; then mysql_db -e "DELETE FROM ${t} WHERE ${w};"; fi
}


echo "[RESET] v0.5 commerce scoped reset"
echo "PROFILE_ID=$PROFILE_ID"
echo "DT=$DT_FROM..$DT_TO"
echo "SCENARIO_FILTER=$SCENARIO_FILTER"
echo "RUN_ID_FILTER=$RUN_ID_FILTER"
echo "SOURCE_GEN_RUN_ID_FILTER=$SOURCE_GEN_RUN_ID_FILTER"
echo "RESET_SOURCE_FILES=$RESET_SOURCE_FILES"
echo "RESET_CASE_OBS_FIGURES=$RESET_CASE_OBS_FIGURES"
echo "RESET_ML_FEATURES=$RESET_ML_FEATURES"
echo "RESET_META=$RESET_META"
echo "DRY_RUN=$DRY_RUN"
echo "POLICY=scoped-delete-then-insert; preserve ML feature/AI outputs and Baseline Reference tables by default"
echo "PRESERVE_BASELINE_REFERENCE=${PRESERVE_BASELINE_REFERENCE:-true}"
echo "RESET_BASELINE_REFERENCE=$RESET_BASELINE_REFERENCE"
echo "RESET_OBS_BASELINE_REFERENCE=$RESET_OBS_BASELINE_REFERENCE"

# Baseline Reference tables are intentionally not reset here:
# - v05_baseline_metric_snapshot_day
# - v05_baseline_reference_run_day
# - v05_baseline_distribution_snapshot_day
# They are reference data for anomaly comparison, not runtime output.


if [[ "$RESET_BASELINE_REFERENCE" == "true" || "$RESET_BASELINE_REFERENCE" == "1" ]]; then
  echo "[RESET] RESET_BASELINE_REFERENCE=true; deleting baseline reference rows for selected date scope"
  for t in v05_baseline_metric_snapshot_day v05_baseline_reference_run_day v05_baseline_distribution_snapshot_day; do
    delete_scoped "$t"
  done
else
  echo "[SKIP] preserve Baseline Reference tables by default"
fi

if [[ "$RESET_OBS_BASELINE_REFERENCE" == "true" || "$RESET_OBS_BASELINE_REFERENCE" == "1" || "$RESET_BASELINE_REFERENCE" == "true" || "$RESET_BASELINE_REFERENCE" == "1" ]]; then
  echo "[RESET] deleting OBS Baseline Reference rows for selected date scope"
  delete_scoped v05_obs_baseline_reference_day
else
  echo "[SKIP] preserve OBS Baseline Reference table by default"
fi

# v0.5 authoritative runtime/decision outputs
for t in \
  action_recommendation_day_v05 unified_reliability_score_day_v05 semantic_interpretation_day_v05 \
  reliability_analysis_result_day_v05 v05_cross_domain_propagation_evidence_day v05_reconciliation_measurement_day transaction_state_mapping behavior_transaction_mapping \
  canonical_state_events canonical_transaction_events canonical_behavior_events v05_runtime_evidence_day v05_semantic_action_calibration_review_day v05_observability_measurement_day r_v05_observability_analysis_day r_v05_observability_interpretation_day v05_observability_anomaly_trace_day \
   v05_obs_app_version_measurement_day v05_obs_sdk_version_measurement_day v05_obs_url_gap_day v05_obs_client_gap_day v05_obs_metric_gap_day \
  v05_obs_baseline_feature_snapshot_day v05_obs_baseline_stat_profile_day v05_obs_baseline_compare_day v05_obs_expected_metric_day \
  v05_obs_threshold_calibration_day v05_obs_forecast_metric_day \
  v05_state_log_raw v05_transaction_log_raw source_exogenous_snapshot_v05
do delete_scoped "$t"; done

# v0.4 evidence layer only
for t in \
  r_reliability_analysis_result_day r_batch_behavior_analysis_day r_batch_distribution_analysis_day r_risk_threshold_profile_v2 r_risk_metric_distribution_day \
  r_metric_correlation_anomaly_day r_metric_time_pattern_anomaly_day r_batch_behavior_anomaly_day \
  measurement_realism_day measurement_operational_day measurement_stream_day measurement_batch_day mapping_coverage_day \
  v05_batch_score_contribution_day v05_batch_behavior_anomaly_day v05_batch_metric_delta_day batch_behavior_anomaly_day \
  batch_behavior_distribution_day batch_behavior_measurement_day batch_input_day batch_quality_diagnostic_v04 stg_ds_metric_hh stg_ds_metric_hh_wide \
  stream_reliability_summary_day stream_reliability_summary_minute stream_validation_result_day stream_validation_summary_day stream_replay_event stg_event_stream \
  pipeline_availability_day pipeline_availability_run pipeline_performance_summary_day pipeline_performance_summary_minute pipeline_run_registry \
  stg_event_batch canonical_events event_log_raw stg_wc_log_hit stg_webserver_log_hit raw_snapshot_manifest
do delete_scoped "$t"; done

# Source lineage and exogenous provenance are reset for scenario rerun unless RESET_META=false prevents catalog-level cleanup.
for t in source_file_manifest source_generation_result_history source_generation_result_summary verification_snapshot_v1 exogenous_state_timeline exogenous_timeline_v1 v05_exogenous_registration_snapshot; do
  delete_scoped "$t"
done

if [[ "$RESET_META" == "true" ]]; then
  for t in source_generation_run pipeline_run_control source_scenario_catalog; do delete_scoped "$t"; done
fi

if [[ "$RESET_ML_FEATURES" == "true" ]]; then
  echo "[RESET] RESET_ML_FEATURES=true; deleting Phase5 ML/AI outputs"
  for t in v05_ai_reliability_score_day v05_ai_validation_result_day v05_ai_incident_summary_day v05_ai_incident_context_day v05_ml_calibration_result_day v05_ml_feature_snapshot_day \
	  v05_ml_prediction_day v05_ml_output_verification_day v05_ml_feature_diagnostics_day v05_llm_execution_log_day v05_ai_validation_detail_day; do
    delete_scoped "$t"
  done
else
  echo "[SKIP] preserve Phase5 ML/AI outputs by default"
fi

if [[ "$RESET_SOURCE_FILES" == "true" ]]; then
  if [[ "$SCENARIO_FILTER" == "all" ]]; then
    TARGET_DIR="$SOURCE_LOG_ROOT/$PROFILE_ID/$DT_FROM"
  else
    TARGET_DIR="$SOURCE_LOG_ROOT/$PROFILE_ID/$DT_FROM/$SCENARIO_FILTER"
  fi
  echo "[DELETE_DIR] $TARGET_DIR"
  if [[ "$DRY_RUN" != "true" && -d "$TARGET_DIR" ]]; then rm -rf "$TARGET_DIR"; fi
fi

if [[ "$RESET_CASE_OBS_FIGURES" == "true" ]]; then
  if [[ "$SCENARIO_FILTER" == "all" ]]; then
    FIGURE_DIR="$CASE_OBS_ARTIFACT_ROOT/CASE-OBS-001/$DT_FROM"
  else
    FIGURE_DIR="$CASE_OBS_ARTIFACT_ROOT/CASE-OBS-001/$DT_FROM/$SCENARIO_FILTER/figures"
  fi
  echo "[DELETE_FIGURES] $FIGURE_DIR"
  if [[ "$DRY_RUN" != "true" && -d "$FIGURE_DIR" ]]; then rm -rf "$FIGURE_DIR"; fi
fi

echo "[DONE] v0.5 commerce reset completed"
