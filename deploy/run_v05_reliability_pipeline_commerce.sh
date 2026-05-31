#!/usr/bin/env bash
set -euo pipefail

DT_FROM="${1:?target date required, e.g. 2026-05-21}"
SCENARIO="${2:-baseline}"
JOURNEYS="${3:-0}"
RUN_ID_INPUT="${4:-}"
SOURCE_GEN_RUN_ID_INPUT="${5:-}"

PROJECT_ROOT="${PROJECT_ROOT:-/home/dwkim_nethru/data/etl/data-reliability-platform}"

# v0.5 commerce calibration profile for R analytics
export V05_COMMERCE_CALIBRATION_CONFIG="${V05_COMMERCE_CALIBRATION_CONFIG:-$PROJECT_ROOT/pipelines/commerce/configs/v05_commerce_calibration_profile.json}"
VENV_PYTHON="${VENV_PYTHON:-$PROJECT_ROOT/.venv/bin/python3}"
[[ -x "$VENV_PYTHON" ]] || VENV_PYTHON="${PYTHON_BIN:-python3}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"
DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB_USER="${DB_USER:-nethru}"; DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"; DB_NAME="${DB_NAME:-weblog}"
KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-127.0.0.1:9092}"
PROFILE_ID="${PROFILE_ID:-commerce_deliver}"
SOURCE_LOG_ROOT="${SOURCE_LOG_ROOT:-/mnt/d/etl_storage/log/logdata/source}"
OUTPUT_DIR="${OUTPUT_DIR:-$SOURCE_LOG_ROOT/$PROFILE_ID/$DT_FROM/$SCENARIO}"
DT_TO="${DT_TO:-$DT_FROM}"
SEED="${SEED:-42}"
DROP_RATE="${DROP_RATE:-0.00}"; DUP_RATE="${DUP_RATE:-0.00}"
WC_MISSING_BASE_RATE="${WC_MISSING_BASE_RATE:-0.18}"
WC_MISSING_CHECKOUT_RATE="${WC_MISSING_CHECKOUT_RATE:-0.35}"
WC_MISSING_PRODUCT_RATE="${WC_MISSING_PRODUCT_RATE:-0.22}"
WC_MISSING_IOS_SAFARI_RATE="${WC_MISSING_IOS_SAFARI_RATE:-0.40}"
RUN_V05_OBSERVABILITY_NATIVE="${RUN_V05_OBSERVABILITY_NATIVE:-true}"
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
RUN_COMMERCE_FALLBACK_RUNTIME="${RUN_COMMERCE_FALLBACK_RUNTIME:-true}"
ALLOW_LOW_RISK_ANOMALY="${ALLOW_LOW_RISK_ANOMALY:-true}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/artifacts/logs}"
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
if [[ "$SCENARIO" == "source_wc_collection_missing" ]]; then
  SOURCE_RUNTIME_MODE="wc_collection_missing"
  APPLY_SOURCE_RUNTIME_ANOMALY="false"
fi
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
  "$PROJECT_ROOT/sql/036_v05_observability_measurement_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/067_v05_observability_core_absorb_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/035_v05_wc_collection_reconciliation_view_mariadb.sql"
do if [[ -f "$ddl" ]]; then echo "[SQL_FILE] $ddl"; mysql_file "$ddl"; else echo "[INFO] optional ddl missing: $(basename "$ddl")"; fi; done


announce 0.21 "ensure scenario identity columns"
run_py_module_if_exists pipelines.commerce.schema.ensure_v05_scenario_identity_columns "${COMMON_DB_ARGS[@]}"

if [[ "$RESET_BEFORE_RUN" == "true" && -z "$RUN_ID_INPUT" && -z "$SOURCE_GEN_RUN_ID_INPUT" ]]; then
  announce 0.25 "scoped reset/truncate for scenario test"
  if [[ -x "$PROJECT_ROOT/deploy/reset_v05_commerce_pipeline.sh" ]]; then
    RUN_ID_FILTER="" SOURCE_GEN_RUN_ID_FILTER="" RESET_SOURCE_FILES="${RESET_SOURCE_FILES:-false}" "$PROJECT_ROOT/deploy/reset_v05_commerce_pipeline.sh" "$DT_FROM" "$DT_TO"
  else
    echo "[WARN] reset_v05_commerce_pipeline.sh not found; continuing without reset"
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
if [[ -n "$RUN_ID_INPUT" ]]; then RUN_ID="$RUN_ID_INPUT"; else RUN_ID="$("$VENV_PYTHON" -m pipelines.control.register_pipeline_run --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --processing-mode stream --runtime-mode replay --scenario-mode "$SOURCE_SCENARIO_MODE" --source-mode "$SOURCE_MODE" --exogenous-mode timeline_db | tail -1)"; fi
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
  echo "[INFO] WC collection anomaly enabled: base=$WC_MISSING_BASE_RATE checkout=$WC_MISSING_CHECKOUT_RATE product=$WC_MISSING_PRODUCT_RATE ios_safari=$WC_MISSING_IOS_SAFARI_RATE"
  COLLECTOR_ARGS+=(--wc-missing-base-rate "$WC_MISSING_BASE_RATE" --wc-missing-checkout-rate "$WC_MISSING_CHECKOUT_RATE" --wc-missing-product-rate "$WC_MISSING_PRODUCT_RATE" --wc-missing-ios-safari-rate "$WC_MISSING_IOS_SAFARI_RATE")
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
fi

announce 4.15 "resolve v0.5 baseline reference for analytics"
run_py_module_if_exists pipelines.commerce.baseline.resolve_v05_baseline_reference "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW" --format shell

if [[ "$RUN_V04_BEHAVIOR_ANALYTICS" == "true" ]]; then
  announce 4.2 "behavior/batch analytics evidence only"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/r_batch_behavior_analysis.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --baseline-dt "$BASELINE_DT" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/build_v05_batch_distribution_analysis.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --baseline-dt "$BASELINE_DT" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW"
  run_r_file_if_exists "$PROJECT_ROOT/pipelines/analytics/r/build_v05_batch_behavior_anomaly.R" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --baseline-mode "$BASELINE_MODE" --baseline-window "$BASELINE_WINDOW"
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
  announce 6 "v0.5 authoritative commerce analytics / semantic / risk / action"
  R_COMMON=(--db-host "$DB_HOST" --db-port "$DB_PORT" --db-user "$DB_USER" --db-pass "$DB_PASSWORD" --db-name "$DB_NAME" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO")
  run_r_script "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_reliability_analysis.R" "${R_COMMON[@]}"
  if [[ "${RUN_V05_OBSERVABILITY_NATIVE:-true}" == "true" ]]; then
    announce 6.05 "v0.5 observability reliability analysis as native semantic input"
    run_r_file_if_exists "$PROJECT_ROOT/pipelines/commerce/analytics/build_v05_observability_reliability_analysis.R" "${R_COMMON[@]}"
  fi
  run_r_script "$PROJECT_ROOT/pipelines/commerce/semantic/build_v05_semantic_interpretation.R" "${R_COMMON[@]}"
  run_r_script "$PROJECT_ROOT/pipelines/commerce/score/build_v05_unified_risk_score.R" "${R_COMMON[@]}"
  run_py_module pipelines.commerce.action.build_v05_action_recommendation "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --run-id "$RUN_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --scenario-name "$SCENARIO" --truncate-target --calibration-config "$PROJECT_ROOT/pipelines/commerce/configs/v05_semantic_action_calibration.yaml"
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
mysql_exec "SELECT action_rank, action_type, recommended_action FROM action_recommendation_day_v05 WHERE profile_id='${PROFILE_ID}' AND target_date='${DT_FROM}' AND run_id=${RUN_ID} ORDER BY action_rank LIMIT 10;" || true
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
