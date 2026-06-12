#!/usr/bin/env bash
set -euo pipefail

# Backfill compaction for CASE-OBS-001 Phase2-C4 statistical tests.
#
# Purpose:
#   Keep statistical/baseline/reliability decision outputs needed for 7d/30d tests,
#   and delete heavy pipeline runtime rows after each daily scenario run.
#
# Preserved by design:
#   - v05_baseline_science_statistical_evidence_day
#   - v05_batch_metric_delta_history_day
#   - v05_obs_baseline_* / v05_obs_expected_metric_day / v05_obs_threshold_calibration_day
#   - v05_reconciliation_measurement_day
#   - v05_cross_domain_propagation_evidence_day
#   - reliability_analysis_result_day_v05 / semantic_interpretation_day_v05 /
#     unified_reliability_score_day_v05 / action_recommendation_day_v05
#
# Deleted by design:
#   - source files and source lineage/runtime catalog rows
#   - raw/stage/canonical behavior/transaction/state rows
#   - replay/stream/runtime/operational detail rows
#   - v0.4 measurement detail rows and batch delta/anomaly day rows after they have
#     been materialized into C4 statistical evidence/history.

PROJECT_ROOT="${PROJECT_ROOT:-/Users/dwkim/dev/repo/data-reliability-platform}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-nethru}"
DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"
DB_NAME="${DB_NAME:-weblog}"
PROFILE_ID="${PROFILE_ID:-commerce_deliver}"
TARGET_DATE=""
SCENARIO="all"
RUN_ID_FILTER="all"
SOURCE_GEN_RUN_ID_FILTER="all"
REMOVE_SOURCE_FILES="${REMOVE_SOURCE_FILES:-true}"
REMOVE_CASE_OBS_FIGURES="${REMOVE_CASE_OBS_FIGURES:-false}"
CASE_OBS_ARTIFACT_ROOT="${CASE_OBS_ARTIFACT_ROOT:-$PROJECT_ROOT/artifacts/case_study}"
DRY_RUN="${DRY_RUN:-false}"
VERIFY_AFTER_COMPACT="${VERIFY_AFTER_COMPACT:-true}"
SOURCE_LOG_ROOT="${SOURCE_LOG_ROOT:-/Users/dwkim/dev/log/logdata/source}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-id) PROFILE_ID="$2"; shift 2 ;;
    --target-date) TARGET_DATE="$2"; shift 2 ;;
    --scenario) SCENARIO="$2"; shift 2 ;;
    --run-id) RUN_ID_FILTER="$2"; shift 2 ;;
    --source-gen-run-id) SOURCE_GEN_RUN_ID_FILTER="$2"; shift 2 ;;
    --remove-source-files) REMOVE_SOURCE_FILES="$2"; shift 2 ;;
    --remove-case-obs-figures) REMOVE_CASE_OBS_FIGURES="$2"; shift 2 ;;
    --verify-after-compact) VERIFY_AFTER_COMPACT="$2"; shift 2 ;;
    --dry-run) DRY_RUN="true"; shift ;;
    *) echo "[ERROR] unknown arg: $1"; exit 1 ;;
  esac
done
[[ -n "$TARGET_DATE" ]] || { echo "[ERROR] --target-date required"; exit 1; }

mysql_db(){ mysql -N -s -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" "$@"; }
mysql_info(){ mysql -N -s -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" information_schema "$@"; }
exists_table(){ [[ "$(mysql_info -e "SELECT COUNT(*) FROM tables WHERE table_schema='${DB_NAME}' AND table_name='$1';")" == "1" ]]; }
has_column(){ [[ "$(mysql_info -e "SELECT COUNT(*) FROM columns WHERE table_schema='${DB_NAME}' AND table_name='$1' AND column_name='$2';")" == "1" ]]; }
q(){ printf "%s" "$1" | sed "s/'/''/g"; }

date_where_for(){
  local t="$1"
  if has_column "$t" target_date; then echo "target_date='$(q "$TARGET_DATE")'"
  elif has_column "$t" dt; then echo "dt='$(q "$TARGET_DATE")'"
  elif has_column "$t" event_date; then echo "event_date='$(q "$TARGET_DATE")'"
  elif has_column "$t" dt_from; then echo "dt_from='$(q "$TARGET_DATE")'"
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
  elif [[ "$SCENARIO" != "all" ]] && has_column "$t" scenario_name; then
    w="$w AND scenario_name='$(q "$SCENARIO")'"
  fi
  echo "[COMPACT_DELETE] $t WHERE $w"
  if [[ "$DRY_RUN" != "true" ]]; then mysql_db -e "DELETE FROM ${t} WHERE ${w};"; fi
}

count_scoped(){
  local t="$1"
  if ! exists_table "$t"; then echo "0"; return; fi
  local w="1=1"
  has_column "$t" profile_id && w="$w AND profile_id='$(q "$PROFILE_ID")'"
  local dw; dw="$(date_where_for "$t")"; [[ "$dw" != "1=1" ]] && w="$w AND $dw"
  if [[ "$SOURCE_GEN_RUN_ID_FILTER" != "all" ]] && has_column "$t" source_gen_run_id; then
    w="$w AND source_gen_run_id='$(q "$SOURCE_GEN_RUN_ID_FILTER")'"
  elif [[ "$RUN_ID_FILTER" != "all" ]] && has_column "$t" run_id; then
    w="$w AND run_id='$(q "$RUN_ID_FILTER")'"
  elif [[ "$SCENARIO" != "all" ]] && has_column "$t" scenario_name; then
    w="$w AND scenario_name='$(q "$SCENARIO")'"
  fi
  mysql_db -e "SELECT COUNT(*) FROM ${t} WHERE ${w};" 2>/dev/null || echo "0"
}

echo "[COMPACT] profile_id=$PROFILE_ID target_date=$TARGET_DATE scenario=$SCENARIO run_id=$RUN_ID_FILTER source_gen_run_id=$SOURCE_GEN_RUN_ID_FILTER remove_source_files=$REMOVE_SOURCE_FILES dry_run=$DRY_RUN"
echo "[COMPACT] delete heavy pipeline/source/canonical/runtime rows; preserve C4 statistical history/evidence and decision outputs"

# Heavy source/raw/stage/canonical/detail runtime tables.
for t in \
  stg_webserver_log_hit stg_wc_log_hit event_log_raw canonical_events stg_event_batch stg_event_stream stream_replay_event \
  canonical_behavior_events canonical_transaction_events canonical_state_events \
  behavior_transaction_mapping transaction_state_mapping \
  v05_transaction_log_raw v05_state_log_raw raw_snapshot_manifest source_file_manifest source_generation_result_history source_generation_result_summary \
  source_generation_run pipeline_run_control pipeline_run_registry \
  pipeline_performance_summary_minute pipeline_performance_summary_day pipeline_availability_run pipeline_availability_day \
  stream_reliability_summary_minute stream_reliability_summary_day stream_validation_result_day stream_validation_summary_day \
  stream_completeness_result stream_duplicate_result stream_latency_result stream_ordering_result \
  metric_value_hh metric_value_day stg_ds_metric_hh stg_ds_metric_hh_wide batch_input_day batch_behavior_measurement_day batch_behavior_distribution_day batch_behavior_anomaly_day \
  measurement_batch_day measurement_stream_day measurement_operational_day measurement_realism_day mapping_coverage_day \
  v05_batch_metric_delta_day v05_batch_behavior_anomaly_day v05_batch_score_contribution_day \
  r_batch_behavior_analysis_day r_batch_distribution_analysis_day r_batch_behavior_anomaly_day r_metric_time_pattern_anomaly_day r_metric_correlation_anomaly_day r_risk_metric_distribution_day r_risk_threshold_profile_v2 \
  v05_runtime_evidence_day v05_semantic_action_calibration_review_day \
  v05_observability_measurement_day r_v05_observability_analysis_day v05_observability_anomaly_trace_day \
  source_exogenous_snapshot_v05 verification_snapshot_v1 exogenous_state_timeline exogenous_timeline_v1 v05_exogenous_registration_snapshot
 do
  delete_scoped "$t"
done

if [[ "$REMOVE_SOURCE_FILES" == "true" || "$REMOVE_SOURCE_FILES" == "1" ]]; then
  if [[ "$SCENARIO" == "all" ]]; then
    target_dir="$SOURCE_LOG_ROOT/$PROFILE_ID/$TARGET_DATE"
  else
    target_dir="$SOURCE_LOG_ROOT/$PROFILE_ID/$TARGET_DATE/$SCENARIO"
  fi
  echo "[COMPACT_DELETE_DIR] $target_dir"
  if [[ "$DRY_RUN" != "true" && -d "$target_dir" ]]; then rm -rf "$target_dir"; fi
fi

if [[ "$VERIFY_AFTER_COMPACT" == "true" || "$VERIFY_AFTER_COMPACT" == "1" ]]; then
  echo "[COMPACT_VERIFY] heavy table counts after compaction"
  for t in canonical_behavior_events canonical_events stg_webserver_log_hit stg_wc_log_hit pipeline_run_registry v05_batch_metric_delta_day measurement_batch_day; do
    echo "  $t=$(count_scoped "$t")"
  done
  echo "[COMPACT_VERIFY] preserved statistical/decision table counts"
  for t in v05_baseline_science_statistical_evidence_day v05_batch_metric_delta_history_day v05_reconciliation_measurement_day v05_cross_domain_propagation_evidence_day reliability_analysis_result_day_v05 r_v05_observability_interpretation_day semantic_interpretation_day_v05 unified_reliability_score_day_v05 action_recommendation_day_v05; do
    echo "  $t=$(count_scoped "$t")"
  done
fi

if [[ "$REMOVE_CASE_OBS_FIGURES" == "true" ]]; then
  if [[ "$SCENARIO" == "all" ]]; then
    FIGURE_DIR="$CASE_OBS_ARTIFACT_ROOT/CASE-OBS-001/$TARGET_DATE"
  else
    FIGURE_DIR="$CASE_OBS_ARTIFACT_ROOT/CASE-OBS-001/$TARGET_DATE/$SCENARIO/figures"
  fi
  echo "[COMPACT_DELETE_FIGURES] $FIGURE_DIR"
  if [[ "$DRY_RUN" != "true" && -d "$FIGURE_DIR" ]]; then rm -rf "$FIGURE_DIR"; fi
fi

echo "[DONE] compact_v05_backfill_runtime completed"
