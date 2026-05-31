#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/dwkim_nethru/data/etl/data-reliability-platform}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-nethru}"
DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"
DB_NAME="${DB_NAME:-weblog}"
PROFILE_ID_DEFAULT="${PROFILE_ID:-commerce_deliver}"

PROFILE_ID_ARG="$PROFILE_ID_DEFAULT"
TARGET_DATE=""
SCENARIO="all"
PRESERVE_ML_AI="true"
REMOVE_SOURCE_FILES="0"
DRY_RUN="${DRY_RUN:-false}"

# v0.5 backfill-safe defaults for set -u cleanup
SOURCE_GEN_RUN_ID_FILTER="${SOURCE_GEN_RUN_ID_FILTER:-all}"
RUN_ID_FILTER="${RUN_ID_FILTER:-all}"
SCENARIO_FILTER="${SCENARIO_FILTER:-all}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-id) PROFILE_ID_ARG="$2"; shift 2 ;;
    --target-date) TARGET_DATE="$2"; shift 2 ;;
    --scenario) SCENARIO="$2"; shift 2 ;;
    --source-gen-run-id) SOURCE_GEN_RUN_ID_FILTER="$2"; shift 2 ;;
    --run-id) RUN_ID_FILTER="$2"; shift 2 ;;
    --scenario-filter) SCENARIO_FILTER="$2"; shift 2 ;;
    --preserve-ml-ai) PRESERVE_ML_AI="$2"; shift 2 ;;
    --remove-source-files) REMOVE_SOURCE_FILES="$2"; shift 2 ;;
    --dry-run) DRY_RUN="true"; shift ;;
    *) echo "[ERROR] unknown arg: $1"; exit 1 ;;
  esac
done

[[ -n "$TARGET_DATE" ]] || { echo "[ERROR] --target-date required"; exit 1; }

SOURCE_LOG_ROOT="${SOURCE_LOG_ROOT:-/mnt/d/etl_storage/log/logdata/source}"

mysql_db(){ mysql -N -s -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" "$@"; }
mysql_info(){ mysql -N -s -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" information_schema "$@"; }
exists_table(){ [[ "$(mysql_info -e "SELECT COUNT(*) FROM tables WHERE table_schema='${DB_NAME}' AND table_name='$1';")" == "1" ]]; }
has_column(){ [[ "$(mysql_info -e "SELECT COUNT(*) FROM columns WHERE table_schema='${DB_NAME}' AND table_name='$1' AND column_name='$2';")" == "1" ]]; }
q(){ printf "%s" "$1" | sed "s/'/''/g"; }

date_col_for(){
  local t="$1"
  if has_column "$t" target_date; then echo "target_date"
  elif has_column "$t" dt; then echo "dt"
  elif has_column "$t" event_date; then echo "event_date"
  else echo ""
  fi
}


date_where_for(){
  local t="$1"
  if has_column "$t" target_date; then echo "target_date>='$(q "$TARGET_DATE")' AND target_date<='$(q "${TARGET_DATE_TO:-$TARGET_DATE}")'"
  elif has_column "$t" dt; then echo "dt>='$(q "$TARGET_DATE")' AND dt<='$(q "${TARGET_DATE_TO:-$TARGET_DATE}")'"
  elif has_column "$t" event_date; then echo "event_date>='$(q "$TARGET_DATE")' AND event_date<='$(q "${TARGET_DATE_TO:-$TARGET_DATE}")'"
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


echo "[TRUNCATE] profile_id=$PROFILE_ID_ARG target_date=$TARGET_DATE scenario=$SCENARIO"
echo "[TRUNCATE] preserve_ml_ai=$PRESERVE_ML_AI remove_source_files=$REMOVE_SOURCE_FILES dry_run=$DRY_RUN"

# Runtime/source/canonical/measurement/authoritative v0.5 outputs.
for t in \
  stg_wc_log_hit stg_webserver_log_hit \
  stream_completeness_result stream_duplicate_result stream_latency_result stream_ordering_result \
  metric_value_hh metric_value_day action_recommendation_day_v05 unified_reliability_score_day_v05 semantic_interpretation_day_v05 \
  reliability_analysis_result_day_v05 v05_reconciliation_measurement_day v05_runtime_evidence_day v05_semantic_action_calibration_review_day \
  transaction_state_mapping behavior_transaction_mapping \
  canonical_state_events canonical_transaction_events canonical_behavior_events \
  v05_state_log_raw v05_transaction_log_raw  \
  r_reliability_analysis_result_day r_batch_behavior_analysis_day r_batch_distribution_analysis_day r_risk_threshold_profile_v2 r_risk_metric_distribution_day \
  r_metric_correlation_anomaly_day r_metric_time_pattern_anomaly_day \
  measurement_realism_day measurement_operational_day measurement_stream_day measurement_batch_day mapping_coverage_day \
  batch_behavior_measurement_day batch_input_day batch_quality_diagnostic_v04 stg_ds_metric_hh stg_ds_metric_hh_wide \
  stream_reliability_summary_day stream_reliability_summary_minute stream_validation_result_day stream_validation_summary_day \
  stream_replay_event stg_event_stream pipeline_availability_run \
  pipeline_availability_day pipeline_performance_summary_day pipeline_performance_summary_minute pipeline_run_registry \
  stg_event_batch canonical_events event_log_raw raw_snapshot_manifest \
  source_file_manifest source_generation_result_history source_generation_result_summary source_exogenous_snapshot_v05 \
  verification_snapshot_v1 v05_exogenous_registration_snapshot exogenous_state_timeline exogenous_timeline_v1
do
  delete_scoped "$t"
done

if [[ "$PRESERVE_ML_AI" == "true" || "$PRESERVE_ML_AI" == "1" ]]; then
  echo "[TRUNCATE] preserve ML/AI outputs"
else
  echo "[TRUNCATE] remove ML/AI outputs"
  for t in \
    v05_ai_reliability_score_day v05_ai_validation_result_day v05_ai_incident_summary_day \
    v05_ml_prediction_day v05_ml_output_verification_day v05_ml_feature_diagnostics_day v05_llm_execution_log_day v05_ai_validation_detail_day \
    v05_ai_incident_context_day v05_ml_calibration_result_day v05_ml_feature_snapshot_day
  do
    delete_scoped "$t"
  done
fi

if [[ "$REMOVE_SOURCE_FILES" == "true" || "$REMOVE_SOURCE_FILES" == "1" ]]; then
  if [[ "$SCENARIO" == "all" ]]; then
    target_dir="$SOURCE_LOG_ROOT/$PROFILE_ID_ARG/$TARGET_DATE"
  else
    target_dir="$SOURCE_LOG_ROOT/$PROFILE_ID_ARG/$TARGET_DATE/$SCENARIO"
  fi
  echo "[TRUNCATE] remove source files: $target_dir"
  if [[ "$DRY_RUN" != "true" && -d "$target_dir" ]]; then
    rm -rf "$target_dir"
  fi
fi

echo "[DONE] truncate_v05_runtime_tables completed"
