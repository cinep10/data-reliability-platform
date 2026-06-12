#!/usr/bin/env bash
set -euo pipefail

# Mac mini Host operation profile.
# Use Homebrew bash if possible:
#   /opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh 2026-05-21 baseline 0
# Defaults:
# - PROJECT_ROOT=/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
# - SOURCE_LOG_ROOT=/Volumes/EXTERNAL_USB/dev/log/logdata/source
# - LOG_DIR=/Volumes/EXTERNAL_USB/dev/log/runtime
# - DB_HOST=127.0.0.1
DT_FROM="${1:?target date required, e.g. 2026-05-21}"
SCENARIO="${2:-baseline}"
JOURNEYS="${3:-0}"
RUN_ID_INPUT="${4:-}"
SOURCE_GEN_RUN_ID_INPUT="${5:-}"

PROJECT_ROOT="${PROJECT_ROOT:-/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform}"

# v0.5 commerce calibration profile for R analytics
export V05_COMMERCE_CALIBRATION_CONFIG="${V05_COMMERCE_CALIBRATION_CONFIG:-$PROJECT_ROOT/pipelines/commerce/configs/v05_commerce_calibration_profile.json}"
VENV_PYTHON="${VENV_PYTHON:-$PROJECT_ROOT/.venv/bin/python3}"
[[ -x "$VENV_PYTHON" ]] || VENV_PYTHON="${PYTHON_BIN:-python3}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB_USER="${DB_USER:-nethru}"; DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"; DB_NAME="${DB_NAME:-weblog}"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-127.0.0.1:9092}"
PROFILE_ID="${PROFILE_ID:-commerce_deliver}"
SOURCE_LOG_ROOT="${SOURCE_LOG_ROOT:-/Volumes/EXTERNAL_USB/dev/log/logdata/source}"
OUTPUT_DIR="${OUTPUT_DIR:-$SOURCE_LOG_ROOT/$PROFILE_ID/$DT_FROM/$SCENARIO}"
DT_TO="${DT_TO:-$DT_FROM}"
SEED="${SEED:-42}"
DROP_RATE="${DROP_RATE:-0.00}"; DUP_RATE="${DUP_RATE:-0.00}"
WC_MISSING_BASE_RATE="${WC_MISSING_BASE_RATE:-0.18}"
WC_MISSING_CHECKOUT_RATE="${WC_MISSING_CHECKOUT_RATE:-0.35}"
WC_MISSING_PRODUCT_RATE="${WC_MISSING_PRODUCT_RATE:-0.22}"
WC_MISSING_IOS_SAFARI_RATE="${WC_MISSING_IOS_SAFARI_RATE:-0.40}"

# CASE-OBS-001 Phase4-B targeted WC collection defaults
WC_MISSING_RULE_MODE="${WC_MISSING_RULE_MODE:-broad}"
WC_MISSING_TARGET_RULE_ID="${WC_MISSING_TARGET_RULE_ID:-none}"
WC_MISSING_TARGET_REASON="${WC_MISSING_TARGET_REASON:-none}"
WC_MISSING_TARGET_APP_PLATFORM="${WC_MISSING_TARGET_APP_PLATFORM:-*}"
WC_MISSING_TARGET_APP_VERSION="${WC_MISSING_TARGET_APP_VERSION:-*}"
WC_MISSING_TARGET_SDK_VERSION="${WC_MISSING_TARGET_SDK_VERSION:-*}"
WC_MISSING_TARGET_RATE="${WC_MISSING_TARGET_RATE:-0.00}"
WC_MISSING_TARGET_FUNNEL_STAGES="${WC_MISSING_TARGET_FUNNEL_STAGES:-*}"
WC_MISSING_TARGET_EVENT_NAMES="${WC_MISSING_TARGET_EVENT_NAMES:-*}"
WC_MISSING_TARGET_CONVERSION_ONLY="${WC_MISSING_TARGET_CONVERSION_ONLY:-false}"
WC_MISSING_RULE_MODE="${WC_MISSING_RULE_MODE:-broad}"
WC_MISSING_TARGET_RULE_ID="${WC_MISSING_TARGET_RULE_ID:-none}"
WC_MISSING_TARGET_REASON="${WC_MISSING_TARGET_REASON:-none}"
WC_MISSING_TARGET_APP_PLATFORM="${WC_MISSING_TARGET_APP_PLATFORM:-*}"
WC_MISSING_TARGET_APP_VERSION="${WC_MISSING_TARGET_APP_VERSION:-*}"
WC_MISSING_TARGET_SDK_VERSION="${WC_MISSING_TARGET_SDK_VERSION:-*}"
WC_MISSING_TARGET_RATE="${WC_MISSING_TARGET_RATE:-0.00}"
WC_MISSING_TARGET_FUNNEL_STAGES="${WC_MISSING_TARGET_FUNNEL_STAGES:-*}"
WC_MISSING_TARGET_EVENT_NAMES="${WC_MISSING_TARGET_EVENT_NAMES:-*}"
WC_MISSING_TARGET_CONVERSION_ONLY="${WC_MISSING_TARGET_CONVERSION_ONLY:-false}"
RUN_V05_OBSERVABILITY_NATIVE="${RUN_V05_OBSERVABILITY_NATIVE:-true}"
RUN_V05_OBS_GAP_MEASUREMENT="${RUN_V05_OBS_GAP_MEASUREMENT:-true}"
RUN_V05_OBS_GAP_VALIDATION="${RUN_V05_OBS_GAP_VALIDATION:-true}"
RUN_V05_OBS_BASELINE_FOUNDATION="${RUN_V05_OBS_BASELINE_FOUNDATION:-true}"
RUN_V05_OBS_BASELINE_VALIDATION="${RUN_V05_OBS_BASELINE_VALIDATION:-true}"
OBS_BASELINE_INCLUDE_TARGET_DATE="${OBS_BASELINE_INCLUDE_TARGET_DATE:-true}"
OBS_BASELINE_ALLOW_LOW_SAMPLE="${OBS_BASELINE_ALLOW_LOW_SAMPLE:-true}"
OBS_BASELINE_MIN_SAMPLE_DAYS="${OBS_BASELINE_MIN_SAMPLE_DAYS:-3}"
RUN_V05_OBS_EXPECTED_MODEL="${RUN_V05_OBS_EXPECTED_MODEL:-true}"
RUN_V05_OBS_EXPECTED_VALIDATION="${RUN_V05_OBS_EXPECTED_VALIDATION:-true}"
OBS_EXPECTED_RECENT_DAYS="${OBS_EXPECTED_RECENT_DAYS:-7}"
OBS_EXPECTED_MIN_SAMPLE_DAYS="${OBS_EXPECTED_MIN_SAMPLE_DAYS:-3}"
RUN_V05_OBS_THRESHOLD_CALIBRATION="${RUN_V05_OBS_THRESHOLD_CALIBRATION:-true}"
RUN_V05_OBS_THRESHOLD_VALIDATION="${RUN_V05_OBS_THRESHOLD_VALIDATION:-true}"
OBS_THRESHOLD_MIN_SAMPLE_DAYS="${OBS_THRESHOLD_MIN_SAMPLE_DAYS:-3}"
RUN_V05_OBS_FORECAST_INTERFACE_VALIDATION="${RUN_V05_OBS_FORECAST_INTERFACE_VALIDATION:-true}"
RUN_V05_BASELINE_SCIENCE_STAT_EVIDENCE="${RUN_V05_BASELINE_SCIENCE_STAT_EVIDENCE:-true}"
RUN_V05_BASELINE_SCIENCE_STAT_VALIDATION="${RUN_V05_BASELINE_SCIENCE_STAT_VALIDATION:-true}"
BASELINE_SCIENCE_STAT_MIN_SAMPLE_DAYS="${BASELINE_SCIENCE_STAT_MIN_SAMPLE_DAYS:-3}"
RUN_V05_CROSS_DOMAIN_PROPAGATION_EVIDENCE="${RUN_V05_CROSS_DOMAIN_PROPAGATION_EVIDENCE:-true}"
RUN_V05_CROSS_DOMAIN_PROPAGATION_VALIDATION="${RUN_V05_CROSS_DOMAIN_PROPAGATION_VALIDATION:-true}"
RUN_V05_OBS_INTERPRETATION="${RUN_V05_OBS_INTERPRETATION:-true}"
RUN_V05_OBS_INTERPRETATION_VALIDATION="${RUN_V05_OBS_INTERPRETATION_VALIDATION:-true}"
OBS_INTERPRETATION_TOP_N="${OBS_INTERPRETATION_TOP_N:-20}"
HOST_DEFAULT="${HOST_DEFAULT:-www.commerce-deliver.example.com}"
SOURCE_SCENARIO_MODE="${SOURCE_SCENARIO_MODE:-source_injection}"; SOURCE_MODE="${SOURCE_MODE:-simulator_file_generate}"
PROFILE_CONFIG="${PROFILE_CONFIG:-$PROJECT_ROOT/simulator/customer_journey_sim/configs/${PROFILE_ID}.yaml}"
SCENARIO_REGISTRY="${SCENARIO_REGISTRY:-$PROJECT_ROOT/configs/v05_scenario_registry.yaml}"
if [[ ! -f "$SCENARIO_REGISTRY" && -f "$PROJECT_ROOT/simulator/customer_journey_sim/configs/v05_scenario_registry.yaml" ]]; then SCENARIO_REGISTRY="$PROJECT_ROOT/simulator/customer_journey_sim/configs/v05_scenario_registry.yaml"; fi
EXPERIMENT_ID="${EXPERIMENT_ID:-v05_${PROFILE_ID}_${DT_FROM}_${SCENARIO}}"
EXOGENOUS_CONFIG="${EXOGENOUS_CONFIG:-$PROJECT_ROOT/simulator/weblog_sim/configs/exogenous_timeline_db.yaml}"
SCENARIO_CONFIG="${SCENARIO_CONFIG:-$PROJECT_ROOT/simulator/weblog_sim/configs/scenario_baseline.yaml}"
BASELINE_DT="${BASELINE_DT:-$DT_FROM}"
BASELINE_WINDOW="${BASELINE_WINDOW:-30d}"
BASELINE_MODE="${BASELINE_MODE:-temporal_baseline}"
BUILD_BASELINE_DISTRIBUTION_IN_RUN="${BUILD_BASELINE_DISTRIBUTION_IN_RUN:-true}"
BASELINE_TPM_INPUT="${BASELINE_TPM_INPUT:-auto}"
RUN_STREAM_KAFKA="${RUN_STREAM_KAFKA:-false}"
RESET_BEFORE_RUN="${RESET_BEFORE_RUN:-true}"
RUN_V04_EVIDENCE_MEASUREMENT="${RUN_V04_EVIDENCE_MEASUREMENT:-true}"
RUN_V04_LEGACY_DECISION="${RUN_V04_LEGACY_DECISION:-false}"
RUN_V05_BATCH_DISTRIBUTION="${RUN_V05_BATCH_DISTRIBUTION:-true}"
RUN_V05_PHASE3_PHASE4="${RUN_V05_PHASE3_PHASE4:-true}"
RUN_INTEGRATED_VALIDATION="${RUN_INTEGRATED_VALIDATION:-true}"
RUN_V05_PATTERN_DRIVEN_RISK_VALIDATION="${RUN_V05_PATTERN_DRIVEN_RISK_VALIDATION:-true}"
RUN_V05_BEHAVIOR_SCOPE_ALLOW_BASELINE_STAT_SUPPRESSION="${RUN_V05_BEHAVIOR_SCOPE_ALLOW_BASELINE_STAT_SUPPRESSION:-true}"
RUN_COMMERCE_FALLBACK_RUNTIME="${RUN_COMMERCE_FALLBACK_RUNTIME:-true}"
ALLOW_LOW_RISK_ANOMALY="${ALLOW_LOW_RISK_ANOMALY:-true}"
LOG_DIR="${LOG_DIR:-/Volumes/EXTERNAL_USB/dev/log/runtime}"
mkdir -p "$LOG_DIR" "$OUTPUT_DIR"
LOG_FILE="${LOG_FILE:-$LOG_DIR/run_v05_commerce_${PROFILE_ID}_${DT_FROM}_${SCENARIO}_$(date +%Y%m%d%H%M%S).log}"
exec > >(tee -a "$LOG_FILE") 2>&1

COMMON_DB_ARGS=(--db-host "$DB_HOST" --db-port "$DB_PORT" --db-user "$DB_USER" --db-pass "$DB_PASSWORD" --db-name "$DB_NAME")
mysql_exec(){ mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" -e "$1"; }
mysql_file(){ mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < "$1"; }
run_cmd(){ printf '[RUN]'; printf ' %q' "$@"; printf '\n'; "$@"; }
run_py_module(){ run_cmd "$VENV_PYTHON" -m "$@"; }
run_r_script(){ run_cmd "$RSCRIPT_BIN" "$@"; }
announce(){ echo; echo "[STEP $1] $2"; }
require_file(){ [[ -f "$1" ]] || { echo "[ERROR] missing required file: $1"; exit 1; }; }
py_module_exists(){ "$VENV_PYTHON" - <<PY "$1" >/dev/null 2>&1
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)
PY
}
run_py_module_if_exists(){ local m="$1"; shift; if py_module_exists "$m"; then run_py_module "$m" "$@"; else echo "[INFO] skip missing module $m"; fi; }
run_py_file_if_exists(){ local f="$1"; shift; if [[ -f "$f" ]]; then run_cmd "$VENV_PYTHON" "$f" "$@"; else echo "[INFO] skip missing $(basename "$f")"; fi; }
run_r_file_if_exists(){ local f="$1"; shift; if [[ -f "$f" ]]; then run_cmd "$RSCRIPT_BIN" "$f" "$@"; else echo "[INFO] skip missing $(basename "$f")"; fi; }

cd "$PROJECT_ROOT"; export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

announce 0 "init v0.5 commerce registry runner"
echo "[INFO] profile_id=$PROFILE_ID dt=$DT_FROM scenario=$SCENARIO output_dir=$OUTPUT_DIR"
echo "[INFO] log_file=$LOG_FILE"
echo "[INFO] authoritative=v05 commerce; v04 measurement/R analytics are evidence only; v04 semantic/risk/action/ml default disabled"

announce 0.1 "resolve scenario registry"
require_file "$SCENARIO_REGISTRY"
SCENARIO_RESOLVE_FILE="$LOG_DIR/v05_scenario_resolve_${PROFILE_ID}_${DT_FROM}_${SCENARIO}_$$.env"
if py_module_exists pipelines.commerce.scenario.resolve_v05_scenario; then
  "$VENV_PYTHON" -m pipelines.commerce.scenario.resolve_v05_scenario --registry "$SCENARIO_REGISTRY" --scenario-id "$SCENARIO" --format shell > "$SCENARIO_RESOLVE_FILE"
else
  "$VENV_PYTHON" -m simulator.customer_journey_sim.scenario.resolve_v05_scenario --registry "$SCENARIO_REGISTRY" --scenario-id "$SCENARIO" --format shell > "$SCENARIO_RESOLVE_FILE"
fi
# shellcheck disable=SC1090
source "$SCENARIO_RESOLVE_FILE"
echo "[INFO] scenario_family=${SCENARIO_FAMILY} source_generation_scenario=${SOURCE_GENERATION_SCENARIO} expected=${EXPECTED_RISK_FAMILY}"

# CASE-OBS-001 Phase4-C: canonical scenario-specific WC collection missing override.
# Authority layers consume generic Evidence/Pattern only. Concrete app/sdk/event
# names remain scenario/measurement/reference explanation and are not risk inputs.
case "$SCENARIO" in
  source_wc_collection_missing)
    SOURCE_RUNTIME_MODE="wc_collection_missing"
    APPLY_SOURCE_RUNTIME_ANOMALY="false"
    WC_MISSING_RULE_MODE="broad"
    ;;
  source_ios_app_version_collection_missing)
    SOURCE_RUNTIME_MODE="wc_collection_missing"
    APPLY_SOURCE_RUNTIME_ANOMALY="false"
    WC_MISSING_RULE_MODE="segment_targeted"
    WC_MISSING_TARGET_RULE_ID="ios_app_version_collection_missing"
    WC_MISSING_TARGET_REASON="ios app version WC tagging initialization missing"
    WC_MISSING_TARGET_APP_PLATFORM="ios_app"
    WC_MISSING_TARGET_APP_VERSION="${IOS_TARGET_APP_VERSION:-ios-app-5.2.1}"
    WC_MISSING_TARGET_SDK_VERSION="*"
    WC_MISSING_TARGET_RATE="${IOS_APP_VERSION_TARGET_MISSING_RATE:-0.85}"
    WC_MISSING_TARGET_FUNNEL_STAGES="*"
    WC_MISSING_TARGET_EVENT_NAMES="*"
    WC_MISSING_TARGET_CONVERSION_ONLY="false"
    ;;
  source_sdk_version_collection_missing|source_sdk_version_collection_missing|source_ios_sdk_version_collection_missing|source_sdk_version_collection_missing)
    # source_ios_sdk_version_collection_missing is kept as a deprecated alias.
    # The canonical scenario is source_sdk_version_collection_missing because
    # SDK-version tagging failures can affect both iOS and Android apps.
    SOURCE_RUNTIME_MODE="wc_collection_missing"
    APPLY_SOURCE_RUNTIME_ANOMALY="false"
    WC_MISSING_RULE_MODE="segment_targeted"
    WC_MISSING_TARGET_RULE_ID="sdk_version_collection_missing"
    WC_MISSING_TARGET_REASON="mobile SDK version WC beacon dispatch missing"
    WC_MISSING_TARGET_APP_PLATFORM="${SDK_TARGET_APP_PLATFORM:-*}"
    WC_MISSING_TARGET_APP_VERSION="*"
    WC_MISSING_TARGET_SDK_VERSION="${SDK_TARGET_SDK_VERSION:-wc-ios-3.2.1,wc-android-3.2.1}"
    WC_MISSING_TARGET_RATE="${SDK_VERSION_TARGET_MISSING_RATE:-0.85}"
    WC_MISSING_TARGET_FUNNEL_STAGES="*"
    WC_MISSING_TARGET_EVENT_NAMES="*"
    WC_MISSING_TARGET_CONVERSION_ONLY="false"
    ;;
  source_ios_purchase_event_collection_missing)
    SOURCE_RUNTIME_MODE="wc_collection_missing"
    APPLY_SOURCE_RUNTIME_ANOMALY="false"
    WC_MISSING_RULE_MODE="segment_targeted"
    WC_MISSING_TARGET_RULE_ID="ios_purchase_event_collection_missing"
    WC_MISSING_TARGET_REASON="ios purchase/conversion event WC collection missing"
    WC_MISSING_TARGET_APP_PLATFORM="ios_app"
    WC_MISSING_TARGET_APP_VERSION="*"
    WC_MISSING_TARGET_SDK_VERSION="*"
    WC_MISSING_TARGET_RATE="${IOS_PURCHASE_EVENT_TARGET_MISSING_RATE:-0.85}"
    WC_MISSING_TARGET_FUNNEL_STAGES="*"
    WC_MISSING_TARGET_EVENT_NAMES="purchase,purchase_success,payment_success,order_complete,conversion"
    WC_MISSING_TARGET_CONVERSION_ONLY="true"
    ;;
esac
echo "[INFO] use_exogenous=${USE_EXOGENOUS_SCENARIO} apply_source_runtime=${APPLY_SOURCE_RUNTIME_ANOMALY} mode=${SOURCE_RUNTIME_MODE}"
RUN_V04_EVIDENCE_MEASUREMENT="${RUN_V04_EVIDENCE_MEASUREMENT_OVERRIDE:-${RUN_V04_EVIDENCE_MEASUREMENT_RESOLVED:-$RUN_V04_EVIDENCE_MEASUREMENT}}"
RUN_V04_LEGACY_DECISION="${RUN_V04_LEGACY_DECISION_OVERRIDE:-${RUN_V04_LEGACY_DECISION_RESOLVED:-$RUN_V04_LEGACY_DECISION}}"
RUN_V05_PHASE3_PHASE4="${RUN_V05_PHASE3_PHASE4_OVERRIDE:-${RUN_V05_PHASE3_PHASE4_RESOLVED:-$RUN_V05_PHASE3_PHASE4}}"
RUN_INTEGRATED_VALIDATION="${RUN_INTEGRATED_VALIDATION_OVERRIDE:-${RUN_INTEGRATED_VALIDATION_RESOLVED:-$RUN_INTEGRATED_VALIDATION}}"

announce 0.2 "apply schemas"
for ddl in \
  "$PROJECT_ROOT/sql/050_v04_batch_analysis_interface_restore_mariadb.sql" \
  "$PROJECT_ROOT/sql/054_v05_batch_behavior_distribution_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/031_v05_commerce_source_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/032_v05_transaction_state_canonicalization_mariadb.sql" \
  "$PROJECT_ROOT/sql/033_v05_reconciliation_measurement_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/034_v05_semantic_risk_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/064_v05_baseline_reference_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/065_v05_baseline_distribution_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/066_v05_distribution_compare_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/068_v05_time_correlation_analysis_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/069_v05_batch_behavior_anomaly_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/070_v05_batch_metric_delta_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/071_v05_batch_score_contribution_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/072_v05_batch_behavior_anomaly_schema_compat_mariadb.sql" \
  "$PROJECT_ROOT/sql/036_v05_observability_measurement_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/067_v05_observability_core_absorb_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/073_v05_obs_gap_measurement_layer_mariadb.sql" \
  "$PROJECT_ROOT/sql/074_v05_obs_baseline_foundation_mariadb.sql" \
  "$PROJECT_ROOT/sql/075_v05_obs_expected_metric_mariadb.sql" \
  "$PROJECT_ROOT/sql/076_v05_obs_threshold_calibration_mariadb.sql" \
  "$PROJECT_ROOT/sql/077_v05_obs_forecast_metric_interface_mariadb.sql" \
  "$PROJECT_ROOT/sql/078_v05_baseline_science_statistical_evidence_mariadb.sql" \
  "$PROJECT_ROOT/sql/079_v05_batch_metric_delta_history_mariadb.sql" \
  "$PROJECT_ROOT/sql/080_v05_observability_interpretation_mariadb.sql" \
  "$PROJECT_ROOT/sql/081_v05_cross_domain_propagation_evidence_mariadb.sql" \
  "$PROJECT_ROOT/sql/087_v05_pattern_driven_risk_layer_mariadb.sql" \
  "$PROJECT_ROOT/sql/088_v05_pattern_classification_action_catalog_mariadb.sql" \
  "$PROJECT_ROOT/sql/089_v05_action_layer_report_expression_mariadb.sql" \
  "$PROJECT_ROOT/sql/090_v05_criticality_pattern_v2_mariadb.sql" \
  "$PROJECT_ROOT/sql/035_v05_wc_collection_reconciliation_view_mariadb.sql"
do if [[ -f "$ddl" ]]; then echo "[SQL_FILE] $ddl"; mysql_file "$ddl"; else echo "[INFO] optional ddl missing: $(basename "$ddl")"; fi; done


announce 0.21 "ensure scenario identity columns"
run_py_module_if_exists pipelines.commerce.schema.ensure_v05_scenario_identity_columns "${COMMON_DB_ARGS[@]}"

if [[ "$RESET_BEFORE_RUN" == "true" && -z "$RUN_ID_INPUT" && -z "$SOURCE_GEN_RUN_ID_INPUT" ]]; then
  announce 0.25 "scoped reset/truncate for scenario test"
  if [[ -f "$PROJECT_ROOT/deploy/reset_v05_commerce_pipeline_mac_host.sh" ]]; then
    RUN_ID_FILTER="" SOURCE_GEN_RUN_ID_FILTER="" RESET_SOURCE_FILES="${RESET_SOURCE_FILES:-false}" /opt/homebrew/bin/bash "$PROJECT_ROOT/deploy/reset_v05_commerce_pipeline_mac_host.sh" "$DT_FROM" "$DT_TO"
  else
    echo "[WARN] reset_v05_commerce_pipeline_mac_host.sh not found; continuing without reset"
  fi
fi

announce 0.25 "validate semantic/action calibration config"

run_py_module_if_exists \
  pipelines.commerce.validation.validate_v05_semantic_action_calibration \
  --calibration-config "$PROJECT_ROOT/pipelines/commerce/configs/v05_semantic_action_calibration.yaml"

announce 0.3 "preflight commerce assets"
for f in \
  "$PROFILE_CONFIG" \
  "$PROJECT_ROOT/pipelines/ingest/collect_raw_snapshot.py" \
  "$PROJECT_ROOT/pipelines/ingest/load_source_webserver_stage_v04.py" \
  "$PROJECT_ROOT/pipelines/collect/collector_wc_log_hit_v04.py" \
  "$PROJECT_ROOT/pipelines/canonical/load_event_log_raw_v04.py" \
  "$PROJECT_ROOT/pipelines/canonical/build_canonical_events_v04.py" \
  "$PROJECT_ROOT/pipelines/commerce/ingest/load_v05_transaction_state_raw.py" \
  "$PROJECT_ROOT/pipelines/commerce/canonical/build_v05_canonical_transaction_state_events.py" \
  "$PROJECT_ROOT/pipelines/commerce/mapping/build_v05_reconciliation_mapping.py" \
  "$PROJECT_ROOT/pipelines/commerce/measurement/build_v05_reconciliation_measurement.py"
do require_file "$f"; done

announce 0.4 "register pipeline run"
if [[ -n "$RUN_ID_INPUT" ]]; then RUN_ID="$RUN_ID_INPUT"; else RUN_ID="$("$VENV_PYTHON" -m pipelines.control.register_pipeline_run  "${COMMON_DB_ARGS[@]}"  --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --processing-mode stream --runtime-mode replay --scenario-mode "$SOURCE_SCENARIO_MODE" --source-mode "$SOURCE_MODE" --exogenous-mode timeline_db | tail -1)"; fi
echo "[INFO] run_id=$RUN_ID"

EXOGENOUS_SNAPSHOT_ID=""
if [[ "${USE_EXOGENOUS_SCENARIO}" == "true" ]]; then
  announce 1.0 "register external/source scenario provenance"
  SNAPSHOT_OUT="$OUTPUT_DIR/${PROFILE_ID}_${DT_FROM}_${SCENARIO}_exogenous_snapshot.json"
  if py_module_exists pipelines.commerce.source.register_v05_exogenous_scenario; then EXO_MOD=pipelines.commerce.source.register_v05_exogenous_scenario; else EXO_MOD=simulator.customer_journey_sim.source.register_v05_exogenous_scenario; fi
  EXO_JSON="$("$VENV_PYTHON" -m "$EXO_MOD" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --scenario-id "$EXOGENOUS_SCENARIO_ID" --experiment-id "$EXPERIMENT_ID" --seed "$SEED" --replace-timeline --profile-config "$PROFILE_CONFIG" --scenario-config "$SCENARIO_CONFIG" --exogenous-config "$EXOGENOUS_CONFIG" --snapshot-out "$SNAPSHOT_OUT")"
  echo "$EXO_JSON"
  EXOGENOUS_SNAPSHOT_ID="$(printf '%s' "$EXO_JSON" | "$VENV_PYTHON" -c 'import json,sys; data=json.load(sys.stdin); print(data.get("exogenous_snapshot_id") or data.get("snapshot_id") or "")')"
fi
echo "[INFO] exogenous_snapshot_id=${EXOGENOUS_SNAPSHOT_ID:-none}"

announce 1.1 "customer journey source generation: journey -> behavior/transaction/state"
if [[ "$SOURCE_GENERATION_SCENARIO" == "baseline" && "$JOURNEYS" != "0" && "$JOURNEYS" -lt 1000 && "${ALLOW_SMALL_SMOKE_TEST:-0}" != "1" ]]; then echo "[FAIL] baseline completion requires UV-scale traffic. Use journeys=0 or ALLOW_SMALL_SMOKE_TEST=1."; exit 1; fi
run_py_module simulator.customer_journey_sim.runners.generate_phase1 --profile-config "$PROFILE_CONFIG" --event-date "$DT_FROM" --scenario "$SOURCE_GENERATION_SCENARIO" --journeys "$JOURNEYS" --out-dir "$OUTPUT_DIR" --seed "$SEED"
MANIFEST="$OUTPUT_DIR/${PROFILE_ID}_${DT_FROM}_${SOURCE_GENERATION_SCENARIO}_manifest.json"
run_py_module simulator.customer_journey_sim.runners.validate_phase1 --manifest "$MANIFEST"

if [[ "${APPLY_SOURCE_RUNTIME_ANOMALY}" == "true" ]]; then
  announce 1.2 "apply source-only anomaly mutation"
  if py_module_exists pipelines.commerce.source.apply_v05_source_runtime_anomaly; then APPLY_MOD=pipelines.commerce.source.apply_v05_source_runtime_anomaly; else APPLY_MOD=simulator.customer_journey_sim.runners.apply_source_runtime_anomaly; fi
  run_py_module "$APPLY_MOD" --profile-id "$PROFILE_ID" --event-date "$DT_FROM" --scenario-name "$SCENARIO" --source-generation-scenario "$SOURCE_GENERATION_SCENARIO" --input-dir "$OUTPUT_DIR" --mode "$SOURCE_RUNTIME_MODE" --seed "$SEED"
fi

announce 1.3 "register Phase1 source files"
if [[ -n "$SOURCE_GEN_RUN_ID_INPUT" ]]; then
  SOURCE_GEN_RUN_ID="$SOURCE_GEN_RUN_ID_INPUT"
  run_py_module simulator.customer_journey_sim.source.register_phase1_source_files "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --scenario-id "$SCENARIO" --source-generation-scenario "$SOURCE_GENERATION_SCENARIO" --scenario-family "$SCENARIO_FAMILY" --input-dir "$OUTPUT_DIR" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --experiment-id "$EXPERIMENT_ID" ${EXOGENOUS_SNAPSHOT_ID:+--exogenous-snapshot-id "$EXOGENOUS_SNAPSHOT_ID"}
else
  SOURCE_GEN_RUN_ID="$("$VENV_PYTHON" -m simulator.customer_journey_sim.source.register_phase1_source_files "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --scenario-id "$SCENARIO" --source-generation-scenario "$SOURCE_GENERATION_SCENARIO" --scenario-family "$SCENARIO_FAMILY" --input-dir "$OUTPUT_DIR" --experiment-id "$EXPERIMENT_ID" ${EXOGENOUS_SNAPSHOT_ID:+--exogenous-snapshot-id "$EXOGENOUS_SNAPSHOT_ID"} | tail -1)"
fi
echo "[INFO] source_gen_run_id=$SOURCE_GEN_RUN_ID"

announce 2 "behavior raw -> stage -> collector -> raw event -> canonical"
run_py_module pipelines.ingest.collect_raw_snapshot --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --input-dir "$OUTPUT_DIR" "${COMMON_DB_ARGS[@]}"
run_cmd "$VENV_PYTHON" "$PROJECT_ROOT/pipelines/ingest/load_source_webserver_stage_v04.py" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --input-dir "$OUTPUT_DIR" --scenario-name "$SCENARIO" --scenario-id "$SCENARIO" --source-generation-scenario "$SOURCE_GENERATION_SCENARIO" --truncate-target "${COMMON_DB_ARGS[@]}"

announce 2.05 "fast stage scenario identity validation"
run_py_module_if_exists pipelines.commerce.validation.validate_v05_stage_scenario_identity "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --expected-source-generation-scenario "$SOURCE_GENERATION_SCENARIO"


announce 2.06 "purge previous source_gen runs for same scenario"
run_py_module_if_exists pipelines.commerce.maintenance.purge_previous_sourcegen_runs_for_scenario   "${COMMON_DB_ARGS[@]}"   --profile-id "$PROFILE_ID"   --target-date "$DT_FROM"   --scenario-name "$SCENARIO"   --active-source-gen-run-id "$SOURCE_GEN_RUN_ID"


announce 2.07 "validate active source_gen run guard"
run_py_module_if_exists pipelines.commerce.validation.validate_v05_active_sourcegen_run   "${COMMON_DB_ARGS[@]}"   --profile-id "$PROFILE_ID"   --target-date "$DT_FROM"   --scenario-name "$SCENARIO"   --active-source-gen-run-id "$SOURCE_GEN_RUN_ID"

COLLECTOR_ARGS=("$VENV_PYTHON" "$PROJECT_ROOT/pipelines/collect/collector_wc_log_hit_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --drop-rate "$DROP_RATE" --dup-rate "$DUP_RATE" --force-status-200-rate "${FORCE_STATUS_200_RATE:-0.00}" --page-event-mode "${PAGE_EVENT_MODE:-evt_or_page_type}" --host-default "$HOST_DEFAULT" --seed "$SEED" --runtime-mode "${SOURCE_RUNTIME_MODE:-none}" --truncate-target)
if [[ "${SOURCE_RUNTIME_MODE:-none}" == "wc_collection_missing" ]]; then

  echo "[INFO] WC collection anomaly enabled: base=$WC_MISSING_BASE_RATE checkout=$WC_MISSING_CHECKOUT_RATE product=$WC_MISSING_PRODUCT_RATE ios_safari=$WC_MISSING_IOS_SAFARI_RATE rule_mode=$WC_MISSING_RULE_MODE target_rule=$WC_MISSING_TARGET_RULE_ID target_app=$WC_MISSING_TARGET_APP_PLATFORM/$WC_MISSING_TARGET_APP_VERSION target_sdk=$WC_MISSING_TARGET_SDK_VERSION target_rate=$WC_MISSING_TARGET_RATE conversion_only=$WC_MISSING_TARGET_CONVERSION_ONLY"
  COLLECTOR_ARGS+=(--wc-missing-base-rate "$WC_MISSING_BASE_RATE" --wc-missing-checkout-rate "$WC_MISSING_CHECKOUT_RATE" --wc-missing-product-rate "$WC_MISSING_PRODUCT_RATE" --wc-missing-ios-safari-rate "$WC_MISSING_IOS_SAFARI_RATE" --wc-missing-rule-mode "$WC_MISSING_RULE_MODE" --wc-missing-target-rule-id "$WC_MISSING_TARGET_RULE_ID" --wc-missing-target-reason "$WC_MISSING_TARGET_REASON" --wc-missing-target-app-platform "$WC_MISSING_TARGET_APP_PLATFORM" --wc-missing-target-app-version "$WC_MISSING_TARGET_APP_VERSION" --wc-missing-target-sdk-version "$WC_MISSING_TARGET_SDK_VERSION" --wc-missing-target-rate "$WC_MISSING_TARGET_RATE" --wc-missing-target-funnel-stages "$WC_MISSING_TARGET_FUNNEL_STAGES" --wc-missing-target-event-names "$WC_MISSING_TARGET_EVENT_NAMES" --wc-missing-target-conversion-only "$WC_MISSING_TARGET_CONVERSION_ONLY")
else
  echo "[INFO] WC collection anomaly disabled: runtime_mode=${SOURCE_RUNTIME_MODE:-none}; WC missing rates are intentionally not passed"
fi
run_cmd "${COLLECTOR_ARGS[@]}"
if [[ "$RUN_V05_OBSERVABILITY_NATIVE" == "true" && "${SOURCE_RUNTIME_MODE:-none}" == "wc_collection_missing" ]]; then
  announce 2.08 "build v0.5 observability measurement from WebServer/WC stage evidence"
  run_py_module_if_exists pipelines.commerce.observability.build_v05_observability_measurement_day "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --truncate-target
  run_py_module_if_exists pipelines.commerce.trace.materialize_v05_observability_anomaly_trace "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID"
fi
run_cmd "$VENV_PYTHON" "$PROJECT_ROOT/pipelines/canonical/load_event_log_raw_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --truncate-target
run_cmd "$VENV_PYTHON" "$PROJECT_ROOT/pipelines/canonical/build_canonical_events_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate-target


announce 2.1 "v0.4 runtime evidence materialization: batch + stream + operational"
if [[ "$RUN_V04_EVIDENCE_MEASUREMENT" == "true" ]]; then
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/batch/build_stg_event_batch_from_canonical_v04_enriched.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate-target
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/batch/analyzer_b_v5_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --identity-mode uid_pcid_ip --session-timeout-sec 1800 --pv-mode view_only --truncate-target --write-legacy
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/batch/batch_quality_diagnostic_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate
  if [[ "$RUN_STREAM_KAFKA" == "true" ]]; then
    TOPIC="stream.${PROFILE_ID}.${DT_FROM}.canonical.$(date +%Y%m%d%H%M%S)"; CONSUMER_GROUP="reliability-${PROFILE_ID}-${DT_FROM}-canonical-$(date +%Y%m%d%H%M%S)"
    run_py_file_if_exists "$PROJECT_ROOT/pipelines/stream/kafka_producer_from_canonical_events_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --topic "$TOPIC" --kafka-bootstrap "$KAFKA_BOOTSTRAP"
    run_py_file_if_exists "$PROJECT_ROOT/pipelines/stream/kafka_consumer_to_stg_event_stream_v04.py" "${COMMON_DB_ARGS[@]}" --kafka-bootstrap "$KAFKA_BOOTSTRAP" --topic "$TOPIC" --consumer-group "$CONSUMER_GROUP" --truncate-target-for-date "$DT_FROM" --profile-id "$PROFILE_ID" --run-id "$RUN_ID" --max-messages "${CONSUMER_MAX_MESSAGES:-200000}" --idle-timeout-sec 10
  elif [[ "$RUN_COMMERCE_FALLBACK_RUNTIME" == "true" ]]; then
    run_py_module_if_exists pipelines.commerce.runtime.materialize_v05_stream_operational_fallback "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --truncate-target
  fi
  for f in stream_duplicate_runner_v4.py stream_ordering_runner_v3.py stream_latency_runner_v3.py stream_completeness_runner_v3.py stream_reliability_aggregator_v5.py; do
    run_py_file_if_exists "$PROJECT_ROOT/pipelines/stream/$f" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO"
  done
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/stream/stream_validation_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/build_operational_events_from_canonical_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate-target --commit-every "${REPLAY_COMMIT_EVERY:-1000}" --batch-size "${REPLAY_BATCH_SIZE:-1000}"
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/run_batch_from_canonical.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate-target
  [[ "$BASELINE_TPM_INPUT" == "auto" ]] && BASELINE_TPM_INPUT="0"
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/build_pipeline_performance_summary_minute_v6.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate-target --run-id "$RUN_ID" --baseline-throughput-per-minute "$BASELINE_TPM_INPUT" --throughput-baseline-mode "${THROUGHPUT_BASELINE_MODE:-auto_active_minutes}"
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/build_pipeline_performance_summary_day_v2.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate-target
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/build_pipeline_availability_run_v5.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate-target --run-id "$RUN_ID"
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/build_pipeline_availability_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate-target
else
  echo "[INFO] RUN_V04_EVIDENCE_MEASUREMENT=false; skipping v0.4 evidence materialization"
fi

announce 3 "transaction/state raw persistence"
run_py_module pipelines.commerce.ingest.load_v05_transaction_state_raw "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --input-dir "$OUTPUT_DIR" --truncate-target
announce 3.1 "canonical behavior/transaction/state"
run_py_module pipelines.commerce.canonical.build_v05_canonical_transaction_state_events "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --truncate-target
announce 3.2 "mapping metadata"
run_py_module pipelines.commerce.mapping.build_v05_reconciliation_mapping "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --truncate-target
run_py_module_if_exists pipelines.commerce.validation.test_v05_phase2_canonical_mapping "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID"


announce 4 "runtime measurement + analytics evidence layer; v0.4 legacy risk disabled by default"

RUN_V04_EVIDENCE_MEASUREMENT="${RUN_V04_EVIDENCE_MEASUREMENT:-true}"
RUN_V04_BEHAVIOR_ANALYTICS="${RUN_V04_BEHAVIOR_ANALYTICS:-true}"
RUN_V05_RUNTIME_EVIDENCE="${RUN_V05_RUNTIME_EVIDENCE:-true}"
RUN_V04_RELIABILITY_ANALYSIS="${RUN_V04_RELIABILITY_ANALYSIS:-false}"

if [[ "$RUN_V04_EVIDENCE_MEASUREMENT" == "true" ]]; then
  announce 4.1 "measurement evidence: batch / stream / operational / realism"
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_batch_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --scenario-name "$SCENARIO"
  run_py_module pipelines.measurement.python.build_v05_batch_behavior_distribution_day "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --input-dir "$OUTPUT_DIR" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW" --write-baseline-comparison
  if [[ "$BUILD_BASELINE_DISTRIBUTION_IN_RUN" == "true" && "$SCENARIO" == "baseline" ]]; then
    echo "[INFO] build baseline metric snapshot from baseline run output"
    run_py_module_if_exists pipelines.commerce.baseline.build_v05_baseline_metric_snapshot_day "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline --include-target-date --truncate-target
    echo "[INFO] build baseline distribution snapshot from baseline run output"
    run_py_module_if_exists pipelines.commerce.baseline.build_v05_baseline_distribution_snapshot_day "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline --include-target-date --truncate-target
  fi
  run_py_module_if_exists pipelines.measurement.python.build_v05_batch_metric_delta_day "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW" --truncate-target
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_stream_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --scenario-name "$SCENARIO"
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_operational_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --scenario-name "$SCENARIO"
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_realism_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --baseline-dt "$BASELINE_DT" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --truncate-target

  if [[ "$RUN_V05_OBS_GAP_MEASUREMENT" == "true" ]]; then
    announce 4.12 "CASE-OBS-001 Phase2-B gap measurement layer"
    run_py_module_if_exists pipelines.commerce.observability.build_v05_obs_gap_measurement_layer "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --truncate-target --apply-schema
    if [[ "$RUN_V05_OBS_GAP_VALIDATION" == "true" ]]; then
      OBS_GAP_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID")
      if [[ "${REQUIRE_NATIVE_OBS_VALIDATION:-true}" == "true" ]]; then OBS_GAP_VALIDATE_ARGS+=(--require-native); fi
      run_py_module_if_exists pipelines.commerce.validation.validate_v05_obs_gap_measurement_layer "${OBS_GAP_VALIDATE_ARGS[@]}"
    fi
    case "$SCENARIO" in
      source_ios_app_version_collection_missing)
        announce 4.121 "CASE-OBS-001 Phase4-B targeted iOS app-version evidence validation"
        run_py_module_if_exists pipelines.commerce.validation.validate_v05_ios_collection_missing_scenario "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-type app_version --expected-app-version "${IOS_TARGET_APP_VERSION:-ios-app-5.2.1}" --min-app-missing-rate "${MIN_IOS_APP_MISSING_RATE:-0.20}" --min-conversion-gap-rate "${MIN_IOS_CONVERSION_GAP_RATE:-0.20}" --require-targeted-page-rows
        ;;
      source_sdk_version_collection_missing|source_ios_sdk_version_collection_missing|source_sdk_version_collection_missing)
        announce 4.121 "CASE-OBS-001 Phase4-B targeted mobile SDK evidence validation"
        run_py_module_if_exists pipelines.commerce.validation.validate_v05_ios_collection_missing_scenario "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-type sdk_version --expected-sdk-version "${SDK_TARGET_SDK_VERSION:-wc-ios-3.2.1,wc-android-3.2.1}" --min-sdk-missing-rate "${MIN_SDK_MISSING_RATE:-0.20}" --min-conversion-gap-rate "${MIN_IOS_CONVERSION_GAP_RATE:-0.20}" --require-targeted-page-rows
        ;;
      source_ios_purchase_event_collection_missing)
        announce 4.121 "CASE-OBS-001 Phase4-B targeted iOS purchase-event evidence validation"
        run_py_module_if_exists pipelines.commerce.validation.validate_v05_ios_collection_missing_scenario "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-type purchase_event --min-conversion-gap-rate "${MIN_IOS_PURCHASE_CONVERSION_GAP_RATE:-0.50}" --max-pv-gap-rate "${MAX_IOS_PURCHASE_PV_GAP_RATE:-0.12}" --require-targeted-page-rows
        ;;
    esac
  fi

  if [[ "$RUN_V05_OBS_BASELINE_FOUNDATION" == "true" && "$SCENARIO" == "baseline" ]]; then
    announce 4.13 "CASE-OBS-001 Phase2-C1 baseline foundation"
    OBS_BASELINE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline --min-sample-days "$OBS_BASELINE_MIN_SAMPLE_DAYS" --truncate-target --apply-schema --rscript-bin "$RSCRIPT_BIN")
    if [[ "$OBS_BASELINE_INCLUDE_TARGET_DATE" == "true" ]]; then OBS_BASELINE_ARGS+=(--include-target-date true); fi
    run_py_module_if_exists pipelines.commerce.observability.build_v05_obs_baseline_foundation "${OBS_BASELINE_ARGS[@]}"
    if [[ "$RUN_V05_OBS_BASELINE_VALIDATION" == "true" ]]; then
      OBS_BASELINE_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline)
      if [[ "${REQUIRE_NATIVE_OBS_VALIDATION:-true}" == "true" ]]; then OBS_BASELINE_VALIDATE_ARGS+=(--require-native); fi
      if [[ "$OBS_BASELINE_ALLOW_LOW_SAMPLE" == "true" ]]; then OBS_BASELINE_VALIDATE_ARGS+=(--allow-low-sample); fi
      run_py_module_if_exists pipelines.commerce.validation.validate_v05_obs_baseline_foundation "${OBS_BASELINE_VALIDATE_ARGS[@]}"
    fi
  fi


  if [[ "$RUN_V05_OBS_EXPECTED_MODEL" == "true" && "$SCENARIO" == "baseline" ]]; then
    announce 4.14 "CASE-OBS-001 Phase2-C2 expected metric model v1"
    run_r_file_if_exists "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_obs_expected_metric.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline --recent-days "$OBS_EXPECTED_RECENT_DAYS" --min-sample-days "$OBS_EXPECTED_MIN_SAMPLE_DAYS"
    if [[ "$RUN_V05_OBS_EXPECTED_VALIDATION" == "true" ]]; then
      OBS_EXPECTED_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW")
      if [[ "${REQUIRE_NATIVE_OBS_VALIDATION:-true}" == "true" ]]; then OBS_EXPECTED_VALIDATE_ARGS+=(--require-native); fi
      if [[ "$OBS_BASELINE_ALLOW_LOW_SAMPLE" == "true" ]]; then OBS_EXPECTED_VALIDATE_ARGS+=(--allow-low-sample); fi
      run_py_module_if_exists pipelines.commerce.validation.validate_v05_obs_expected_metric "${OBS_EXPECTED_VALIDATE_ARGS[@]}"
    fi
  fi

  if [[ "$RUN_V05_OBS_THRESHOLD_CALIBRATION" == "true" && "$SCENARIO" == "baseline" ]]; then
    announce 4.145 "CASE-OBS-001 Phase2-C3 threshold calibration"
    run_r_file_if_exists "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_obs_threshold_calibration.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline --min-sample-days "$OBS_THRESHOLD_MIN_SAMPLE_DAYS"
    if [[ "$RUN_V05_OBS_THRESHOLD_VALIDATION" == "true" ]]; then
      OBS_THRESHOLD_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW")
      if [[ "${REQUIRE_NATIVE_OBS_VALIDATION:-true}" == "true" ]]; then OBS_THRESHOLD_VALIDATE_ARGS+=(--require-native); fi
      if [[ "$OBS_BASELINE_ALLOW_LOW_SAMPLE" == "true" ]]; then OBS_THRESHOLD_VALIDATE_ARGS+=(--allow-low-sample); fi
      run_py_module_if_exists pipelines.commerce.validation.validate_v05_obs_threshold_calibration "${OBS_THRESHOLD_VALIDATE_ARGS[@]}"
    fi
  fi

  if [[ "$RUN_V05_OBS_FORECAST_INTERFACE_VALIDATION" == "true" && "$SCENARIO" == "baseline" ]]; then
    announce 4.146 "CASE-OBS-001 Phase2-C3 forecast interface validation"
    run_py_module_if_exists pipelines.commerce.validation.validate_v05_obs_forecast_interface "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW"
  fi

  if [[ "$RUN_V05_BASELINE_SCIENCE_STAT_EVIDENCE" == "true" || "$RUN_V05_BASELINE_SCIENCE_STAT_EVIDENCE" == "1" ]]; then
    announce 4.147 "CASE-OBS-001 Phase2-C4 baseline science statistical evidence: batch/observability"
    run_r_file_if_exists "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_baseline_science_statistical_evidence.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline --domains batch,observability --min-sample-days "$BASELINE_SCIENCE_STAT_MIN_SAMPLE_DAYS"
    if [[ "$RUN_V05_BASELINE_SCIENCE_STAT_VALIDATION" == "true" || "$RUN_V05_BASELINE_SCIENCE_STAT_VALIDATION" == "1" ]]; then
      STAT_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW" --domains batch_metric_delta,observability_expected --allow-missing-domain)
      if [[ "${OBS_BASELINE_ALLOW_LOW_SAMPLE:-true}" == "true" ]]; then STAT_VALIDATE_ARGS+=(--allow-low-sample); fi
      run_py_module_if_exists pipelines.commerce.validation.validate_v05_baseline_science_statistical_evidence "${STAT_VALIDATE_ARGS[@]}"
    fi
  fi
fi

announce 4.15 "resolve v0.5 baseline reference for analytics"
run_py_module_if_exists pipelines.commerce.baseline.resolve_v05_baseline_reference "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW" --format shell

if [[ "$RUN_V04_BEHAVIOR_ANALYTICS" == "true" ]]; then
  announce 4.2 "behavior/batch analytics evidence only"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/r_batch_behavior_analysis.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --baseline-dt "$BASELINE_DT" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/build_v05_batch_distribution_analysis.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --baseline-dt "$BASELINE_DT" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/build_v05_batch_behavior_anomaly.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW"
  if [[ "${RUN_V05_BEHAVIOR_SCOPE_VALIDATION:-true}" == "true" ]]; then
    BEHAVIOR_SCOPE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID")
    if [[ "$SCENARIO" != "baseline" ]]; then
      BEHAVIOR_SCOPE_ARGS+=(--require-anomaly-row)
    elif [[ "$RUN_V05_BEHAVIOR_SCOPE_ALLOW_BASELINE_STAT_SUPPRESSION" == "true" || "$RUN_V05_BEHAVIOR_SCOPE_ALLOW_BASELINE_STAT_SUPPRESSION" == "1" ]]; then
      BEHAVIOR_SCOPE_ARGS+=(--allow-baseline-statistical-suppression)
    fi
    run_py_module_if_exists pipelines.commerce.validation.validate_v05_behavior_measurement_scope "${BEHAVIOR_SCOPE_ARGS[@]}"
  fi
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/r_time_pattern_anomaly_v04.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --baseline-dt "$BASELINE_DT" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/r_correlation_anomaly_v04.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --baseline-dt "$BASELINE_DT" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/r_risk_metric_distribution_day.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/r_risk_threshold_profile_v2.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --effective-from "$DT_FROM"
fi

if [[ "$RUN_V04_RELIABILITY_ANALYSIS" == "true" ]]; then
  announce 4.3 "optional v0.4 reliability analysis comparison; not v0.5 authoritative"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/r_reliability_analysis.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --baseline-dt "$BASELINE_DT" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW" --expected-risk-family "$EXPECTED_RISK_FAMILY"
else
  echo "[INFO] skipped r_reliability_analysis.R; v0.4 reliability analysis is risk-like output and not the v0.5 runtime evidence interface"
fi

if [[ "$RUN_V05_RUNTIME_EVIDENCE" == "true" ]]; then
  announce 4.4 "build v0.5 runtime evidence interface"
  run_py_module pipelines.commerce.runtime.build_v05_runtime_evidence_day "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --truncate-target
fi

if [[ "$RUN_V05_PHASE3_PHASE4" == "true" ]]; then
  announce 5 "v0.5 commerce reconciliation measurement"
  run_py_module pipelines.commerce.measurement.build_v05_reconciliation_measurement "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --truncate-target
  if [[ "$RUN_V05_BASELINE_SCIENCE_STAT_EVIDENCE" == "true" || "$RUN_V05_BASELINE_SCIENCE_STAT_EVIDENCE" == "1" ]]; then
    announce 5.1 "CASE-OBS-001 Phase2-C4 baseline science statistical evidence: reconciliation"
    run_r_file_if_exists "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_baseline_science_statistical_evidence.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW" --baseline-scenario baseline --domains reconciliation --min-sample-days "$BASELINE_SCIENCE_STAT_MIN_SAMPLE_DAYS"
    if [[ "$RUN_V05_BASELINE_SCIENCE_STAT_VALIDATION" == "true" || "$RUN_V05_BASELINE_SCIENCE_STAT_VALIDATION" == "1" ]]; then
      RECON_STAT_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW" --domains reconciliation_measurement)
      if [[ "${OBS_BASELINE_ALLOW_LOW_SAMPLE:-true}" == "true" ]]; then RECON_STAT_VALIDATE_ARGS+=(--allow-low-sample); fi
      run_py_module_if_exists pipelines.commerce.validation.validate_v05_baseline_science_statistical_evidence "${RECON_STAT_VALIDATE_ARGS[@]}"
    fi
  fi
  if [[ "$RUN_V05_CROSS_DOMAIN_PROPAGATION_EVIDENCE" == "true" || "$RUN_V05_CROSS_DOMAIN_PROPAGATION_EVIDENCE" == "1" ]]; then
    announce 5.2 "CASE-OBS-001 Phase3-B cross-domain propagation evidence"
    run_r_file_if_exists "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_cross_domain_propagation_evidence.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --baseline-window "$BASELINE_WINDOW"
    if [[ "$RUN_V05_CROSS_DOMAIN_PROPAGATION_VALIDATION" == "true" || "$RUN_V05_CROSS_DOMAIN_PROPAGATION_VALIDATION" == "1" ]]; then
      PROPAGATION_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID")
      if [[ "$SCENARIO" == "baseline" ]]; then
        PROPAGATION_VALIDATE_ARGS+=(--allow-baseline-no-propagation)
      else
        PROPAGATION_VALIDATE_ARGS+=(--require-propagation --min-propagation "${MIN_CROSS_DOMAIN_PROPAGATION:-0.10}" --min-confidence "${MIN_RECONCILIATION_CONFIDENCE:-0.30}" --min-affected-domains "${MIN_AFFECTED_DOMAINS:-1}")
      fi
      run_py_module_if_exists pipelines.commerce.validation.validate_v05_cross_domain_propagation_evidence "${PROPAGATION_VALIDATE_ARGS[@]}"
    fi
  fi

  announce 6 "v0.5 authoritative commerce analytics / semantic / risk / action"
  R_COMMON=(--db-host "$DB_HOST" --db-port "$DB_PORT" --db-user "$DB_USER" --db-pass "$DB_PASSWORD" --db-name "$DB_NAME" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO")
  run_r_script "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_reliability_analysis.R" "${R_COMMON[@]}"
  if [[ "${RUN_V05_AUTHORITY_EVIDENCE_VALIDATION:-true}" == "true" || "${RUN_V05_AUTHORITY_EVIDENCE_VALIDATION:-true}" == "1" ]]; then
    announce 6.015 "Authority Analytics Layer: concentration/criticality evidence validation"
    AUTHORITY_EVIDENCE_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID")
    case "$SCENARIO" in
      baseline) AUTHORITY_EVIDENCE_VALIDATE_ARGS+=(--allow-baseline-zero) ;;
      source_ios_app_version_collection_missing|source_sdk_version_collection_missing|source_ios_sdk_version_collection_missing|source_sdk_version_collection_missing) AUTHORITY_EVIDENCE_VALIDATE_ARGS+=(--require-evidence-signal --require-concentration --min-concentration "${MIN_AUTHORITY_CONCENTRATION_EVIDENCE:-0.15}") ;;
      source_ios_purchase_event_collection_missing) AUTHORITY_EVIDENCE_VALIDATE_ARGS+=(--require-evidence-signal --require-criticality --min-criticality "${MIN_AUTHORITY_CRITICALITY_EVIDENCE:-0.60}" --require-business-kpi-distortion --min-business-kpi-distortion "${MIN_BUSINESS_KPI_DISTORTION:-0.60}" --require-traffic-preservation --min-traffic-preservation "${MIN_TRAFFIC_PRESERVATION:-0.30}") ;;
      *) AUTHORITY_EVIDENCE_VALIDATE_ARGS+=(--require-evidence-signal --min-evidence-signal "${MIN_AUTHORITY_EVIDENCE_SIGNAL:-0.05}") ;;
    esac
    run_py_module_if_exists pipelines.commerce.validation.validate_v05_authority_evidence_layer "${AUTHORITY_EVIDENCE_VALIDATE_ARGS[@]}"
  fi
  if [[ "${RUN_V05_AUTHORITY_PATTERN_VALIDATION:-true}" == "true" || "${RUN_V05_AUTHORITY_PATTERN_VALIDATION:-true}" == "1" ]]; then
    announce 6.02 "Authority Analytics Layer: generic pattern differentiation validation"
    AUTHORITY_PATTERN_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID")
    case "$SCENARIO" in
      baseline) AUTHORITY_PATTERN_VALIDATE_ARGS+=(--allow-baseline-stable) ;;
      source_ios_app_version_collection_missing|source_sdk_version_collection_missing|source_ios_sdk_version_collection_missing|source_sdk_version_collection_missing) AUTHORITY_PATTERN_VALIDATE_ARGS+=(--require-pattern --expected-pattern localized_failure --min-pattern-confidence "${MIN_AUTHORITY_PATTERN_CONFIDENCE:-0.05}") ;;
      source_ios_purchase_event_collection_missing) AUTHORITY_PATTERN_VALIDATE_ARGS+=(--require-pattern --expected-pattern silent_distortion --min-pattern-confidence "${MIN_AUTHORITY_PATTERN_CONFIDENCE:-0.05}") ;;
      *) AUTHORITY_PATTERN_VALIDATE_ARGS+=(--require-pattern --min-pattern-confidence "${MIN_AUTHORITY_PATTERN_CONFIDENCE:-0.05}") ;;
    esac
    run_py_module_if_exists pipelines.commerce.validation.validate_v05_authority_pattern_layer "${AUTHORITY_PATTERN_VALIDATE_ARGS[@]}"
  fi
  if [[ "${RUN_V05_OBSERVABILITY_NATIVE:-true}" == "true" ]]; then
    announce 6.05 "v0.5 observability reliability analysis as native semantic input"
    run_r_file_if_exists "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_observability_reliability_analysis.R" "${R_COMMON[@]}"
    if [[ "$RUN_V05_OBS_INTERPRETATION" == "true" || "$RUN_V05_OBS_INTERPRETATION" == "1" ]]; then
      announce 6.06 "CASE-OBS-001 Phase3-A observability interpretation / root cause confidence"
      run_r_file_if_exists "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_observability_interpretation.R" "${R_COMMON[@]}" --baseline-window "$BASELINE_WINDOW" --top-n "$OBS_INTERPRETATION_TOP_N"
      if [[ "$RUN_V05_OBS_INTERPRETATION_VALIDATION" == "true" || "$RUN_V05_OBS_INTERPRETATION_VALIDATION" == "1" ]]; then
        OBS_INTERPRET_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID")
        if [[ "$SCENARIO" == "baseline" ]]; then OBS_INTERPRET_VALIDATE_ARGS+=(--allow-baseline-no-signal); else OBS_INTERPRET_VALIDATE_ARGS+=(--require-signal --min-confidence "${OBS_INTERPRETATION_MIN_CONFIDENCE:-0.20}"); fi
        run_py_module_if_exists pipelines.commerce.validation.validate_v05_observability_interpretation "${OBS_INTERPRET_VALIDATE_ARGS[@]}"
      fi
    fi
  fi
  run_r_script "$PROJECT_ROOT/pipelines/commerce/score/build_v05_unified_risk_score.R" "${R_COMMON[@]}"
  if [[ "${RUN_V05_PATTERN_DRIVEN_RISK_VALIDATION:-true}" == "true" || "${RUN_V05_PATTERN_DRIVEN_RISK_VALIDATION:-true}" == "1" ]]; then
    announce 6.071 "Authority Risk Layer: pattern-driven risk validation"
    PATTERN_RISK_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID")
    if [[ "$SCENARIO" == "baseline" ]]; then
      PATTERN_RISK_VALIDATE_ARGS+=(--allow-baseline-zero)
    else
      PATTERN_RISK_VALIDATE_ARGS+=(--require-risk-signal --min-likelihood "${MIN_UNIFIED_RISK_LIKELIHOOD:-0.05}" --min-impact "${MIN_UNIFIED_RISK_IMPACT:-0.05}" --min-risk "${MIN_UNIFIED_RISK_SCORE:-0.01}" --min-pattern-confidence "${MIN_AUTHORITY_PATTERN_CONFIDENCE:-0.05}")
    fi
    run_py_module_if_exists pipelines.commerce.validation.validate_v05_pattern_driven_risk_layer "${PATTERN_RISK_VALIDATE_ARGS[@]}"
  fi
  run_r_script "$PROJECT_ROOT/pipelines/commerce/semantic/build_v05_semantic_interpretation.R" "${R_COMMON[@]}"
  run_py_module pipelines.commerce.action.build_v05_action_recommendation "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --truncate-target --calibration-config "$PROJECT_ROOT/pipelines/commerce/configs/v05_semantic_action_calibration.yaml"
  if [[ "${RUN_V05_PATTERN_CLASSIFICATION_ACTION_VALIDATION:-true}" == "true" || "${RUN_V05_PATTERN_CLASSIFICATION_ACTION_VALIDATION:-true}" == "1" ]]; then
    announce 6.09 "Knowledge Base Layer: pattern classification/action catalog validation"
    PATTERN_KB_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID")
    if [[ "$SCENARIO" == "baseline" ]]; then
      PATTERN_KB_VALIDATE_ARGS+=(--allow-baseline-no-action)
    else
      PATTERN_KB_VALIDATE_ARGS+=(--require-pattern-classification --require-pattern-action --min-pattern-confidence "${MIN_AUTHORITY_PATTERN_CONFIDENCE:-0.05}")
    fi
    run_py_module_if_exists pipelines.commerce.validation.validate_v05_pattern_classification_action_catalog "${PATTERN_KB_VALIDATE_ARGS[@]}"
  fi
  if [[ "${RUN_V05_ACTION_LAYER_REPORT_VALIDATION:-true}" == "true" || "${RUN_V05_ACTION_LAYER_REPORT_VALIDATION:-true}" == "1" ]]; then
    announce 6.095 "Knowledge Base Layer: authority action + OBS reference action report validation"
    ACTION_LAYER_REPORT_VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID")
    if [[ "$SCENARIO" == "baseline" ]]; then
      ACTION_LAYER_REPORT_VALIDATE_ARGS+=(--allow-baseline-no-reference)
    else
      ACTION_LAYER_REPORT_VALIDATE_ARGS+=(--require-authority-action --require-reference-action)
    fi
    run_py_module_if_exists pipelines.commerce.validation.validate_v05_action_layer_report_expression "${ACTION_LAYER_REPORT_VALIDATE_ARGS[@]}"
  fi
  if [[ "${RUN_CASE_OBS_001_FIGURES:-true}" == "true" || "${RUN_CASE_OBS_001_FIGURES:-true}" == "1" ]]; then
    announce 6.10 "Visualization Layer: CASE-OBS-001 decision-support figures"
    CASE_OBS_FIGURE_DIR="${CASE_OBS_FIGURE_DIR:-$PROJECT_ROOT/artifacts/case_study/CASE-OBS-001/$DT_FROM/$SCENARIO/figures}"
    run_r_file_if_exists "$PROJECT_ROOT/pipelines/commerce/visualization/build_case_obs_001_figures.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --output-dir "$CASE_OBS_FIGURE_DIR" --view-mode decision_support --include-engineer-appendix true --top-n "${CASE_OBS_FIGURE_TOP_N:-15}"
    if [[ "${RUN_CASE_OBS_001_FIGURE_VALIDATION:-true}" == "true" || "${RUN_CASE_OBS_001_FIGURE_VALIDATION:-true}" == "1" ]]; then
      CASE_OBS_FIGURE_VALIDATE_ARGS=(--profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --figure-dir "$CASE_OBS_FIGURE_DIR" --require-decision-support --require-engineer-appendix)
      if [[ "${RUN_V05_OBSERVABILITY_NATIVE:-true}" == "true" || "${RUN_V05_OBSERVABILITY_NATIVE:-true}" == "1" ]]; then
        CASE_OBS_FIGURE_VALIDATE_ARGS+=(--require-mobile-app-evidence \
      --require-operational-report \
      --require-customer-visual-redesign)
      fi
      run_py_module_if_exists pipelines.commerce.validation.validate_case_obs_001_figures "${CASE_OBS_FIGURE_VALIDATE_ARGS[@]}"
    fi
  fi

fi

if [[ "$RUN_INTEGRATED_VALIDATION" == "true" ]]; then
  announce 7 "integrated validation"
  run_py_module_if_exists pipelines.commerce.validation.test_v05_phase1_to_phase4_pipeline "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID"
  VALIDATE_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO")
  [[ "$ALLOW_LOW_RISK_ANOMALY" == "true" ]] && VALIDATE_ARGS+=(--allow-low-risk-anomaly)
  run_py_module_if_exists pipelines.commerce.validation.validate_v05_commerce_run "${VALIDATE_ARGS[@]}"
fi

announce 8 "authoritative review"
mysql_exec "SELECT 'canonical_behavior_events' table_name, COUNT(*) cnt FROM canonical_behavior_events WHERE profile_id='${PROFILE_ID}' AND target_date='${DT_FROM}' AND run_id=${RUN_ID} UNION ALL SELECT 'canonical_transaction_events', COUNT(*) FROM canonical_transaction_events WHERE profile_id='${PROFILE_ID}' AND target_date='${DT_FROM}' AND run_id=${RUN_ID} UNION ALL SELECT 'canonical_state_events', COUNT(*) FROM canonical_state_events WHERE profile_id='${PROFILE_ID}' AND target_date='${DT_FROM}' AND run_id=${RUN_ID} UNION ALL SELECT 'stg_event_stream', COUNT(*) FROM stg_event_stream WHERE profile_id='${PROFILE_ID}' AND dt='${DT_FROM}' AND run_id=${RUN_ID};" || true
mysql_exec "SELECT behavior_transaction_match_rate, transaction_state_match_rate, behavior_only_count, transaction_only_count, orphan_state_count, transaction_without_state_count FROM v05_reconciliation_measurement_day WHERE profile_id='${PROFILE_ID}' AND target_date='${DT_FROM}' AND run_id=${RUN_ID};" || true
mysql_exec "SELECT dominant_semantic_risk FROM semantic_interpretation_day_v05 WHERE profile_id='${PROFILE_ID}' AND target_date='${DT_FROM}' AND run_id=${RUN_ID};" || true
mysql_exec "SELECT overall_risk_score, final_risk_level FROM unified_reliability_score_day_v05 WHERE profile_id='${PROFILE_ID}' AND target_date='${DT_FROM}' AND run_id=${RUN_ID};" || true
mysql_exec "SELECT action_rank, action_layer, action_catalog_source, action_type, recommended_action FROM action_recommendation_day_v05 WHERE profile_id='${PROFILE_ID}' AND target_date='${DT_FROM}' AND run_id=${RUN_ID} ORDER BY action_rank LIMIT 10;" \
  || mysql_exec "SELECT action_rank, action_type, recommended_action, evidence_signal, mapping_rule_id FROM action_recommendation_day_v05 WHERE profile_id='${PROFILE_ID}' AND target_date='${DT_FROM}' AND run_id=${RUN_ID} ORDER BY action_rank LIMIT 10;" \
  || mysql_exec "SELECT priority, recommended_action, root_cause_direction, risk_alignment_score FROM action_recommendation_day WHERE profile_id='${PROFILE_ID}' AND dt='${DT_FROM}' AND run_id='${RUN_ID}' LIMIT 10;" \
  || true
cat <<DONE
[DONE] v0.5 commerce reliability pipeline completed
PROFILE_ID=$PROFILE_ID
DT=$DT_FROM
SCENARIO=$SCENARIO
SCENARIO_FAMILY=$SCENARIO_FAMILY
SOURCE_GENERATION_SCENARIO=$SOURCE_GENERATION_SCENARIO
AUTHORITATIVE_CHAIN=v05_commerce
V04_EVIDENCE_MEASUREMENT=$RUN_V04_EVIDENCE_MEASUREMENT
V04_LEGACY_DECISION=$RUN_V04_LEGACY_DECISION
RUN_ID=$RUN_ID
SOURCE_GEN_RUN_ID=$SOURCE_GEN_RUN_ID
OUTPUT_DIR=$OUTPUT_DIR
LOG_FILE=$LOG_FILE
DONE
