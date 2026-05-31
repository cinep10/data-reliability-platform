#!/usr/bin/env bash
set -euo pipefail

DT_FROM="${1:?target date required, e.g. 2026-05-18}"
SCENARIO="${2:-baseline}"
JOURNEYS="${3:-0}"
RUN_ID_INPUT="${4:-}"
SOURCE_GEN_RUN_ID_INPUT="${5:-}"

PROJECT_ROOT="${PROJECT_ROOT:-/home/dwkim_nethru/data/etl/data-reliability-platform}"
VENV_PYTHON="${VENV_PYTHON:-$PROJECT_ROOT/.venv/bin/python3}"
[[ -x "$VENV_PYTHON" ]] || VENV_PYTHON="${PYTHON_BIN:-python3}"

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-nethru}"
DB_PASSWORD="${DB_PASSWORD:-nethru1234}"
DB_NAME="${DB_NAME:-weblog}"
PROFILE_ID="${PROFILE_ID:-commerce_deliver}"
SOURCE_LOG_ROOT="${SOURCE_LOG_ROOT:-/mnt/d/etl_storage/log/logdata/source}"
BASE_DIR="${BASE_DIR:-$SOURCE_LOG_ROOT}"
OUTPUT_DIR="${OUTPUT_DIR:-$BASE_DIR/$PROFILE_ID/$DT_FROM/$SCENARIO}"
DT_TO="${DT_TO:-$DT_FROM}"
SEED="${SEED:-42}"
DROP_RATE="${DROP_RATE:-0.00}"
DUP_RATE="${DUP_RATE:-0.00}"
HOST_DEFAULT="${HOST_DEFAULT:-www.commerce-deliver.example.com}"
SOURCE_SCENARIO_MODE="${SOURCE_SCENARIO_MODE:-source_injection}"
SOURCE_MODE="${SOURCE_MODE:-simulator_file_generate}"
PROFILE_CONFIG="${PROFILE_CONFIG:-$PROJECT_ROOT/simulator/customer_journey_sim/configs/${PROFILE_ID}.yaml}"
BASELINE_DT="${BASELINE_DT:-$DT_FROM}"
BASELINE_TPM_INPUT="${BASELINE_TPM_INPUT:-auto}"
RUN_STREAM_KAFKA="${RUN_STREAM_KAFKA:-false}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/artifacts/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_FILE:-$LOG_DIR/run_collection_reliability_only_${PROFILE_ID}_${DT_FROM}_${SCENARIO}_$(date +%Y%m%d%H%M%S).log}"
exec > >(tee -a "$LOG_FILE") 2>&1

COMMON_DB_ARGS=(--db-host "$DB_HOST" --db-port "$DB_PORT" --db-user "$DB_USER" --db-pass "$DB_PASSWORD" --db-name "$DB_NAME")
mysql_file(){ mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < "$1"; }
run_cmd(){ printf '[RUN]'; printf ' %q' "$@"; printf '\n'; "$@"; }
run_py_module(){ run_cmd "$VENV_PYTHON" -m "$@"; }
announce(){ echo; echo "[STEP $1] $2"; }
require_file(){ [[ -f "$1" ]] || { echo "[ERROR] missing required file: $1"; exit 1; }; }
run_py_file_if_exists(){ local f="$1"; shift; if [[ -f "$f" ]]; then run_cmd "$VENV_PYTHON" "$f" "$@"; else echo "[INFO] skip missing $(basename "$f")"; fi; }

cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

announce 0 "init Collection Reliability only runner"
echo "[INFO] profile_id=$PROFILE_ID dt=$DT_FROM scenario=$SCENARIO"
echo "[INFO] output_dir=$OUTPUT_DIR"
echo "[INFO] log_file=$LOG_FILE"
echo "[INFO] scope=Source -> Stage -> Collector -> Raw -> Canonical -> v0.4 Measurement only"
echo "[INFO] excludes=v0.5 transaction/state/reconciliation, R semantic/risk/action, integrated validation"

announce 0.1 "apply required schemas when present"
for ddl in \
  "$PROJECT_ROOT/sql/015_create_v04_cookie_batch_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/016_create_v04_batch_analytics_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/017_create_v04_stream_analytics_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/019_create_v04_baseline_calibration_schema_mariadb.sql" \
  "$PROJECT_ROOT/sql/024_create_v04_phase3_decision_architecture_mariadb.sql" \
  "$PROJECT_ROOT/sql/031_v05_commerce_source_schema_mariadb.sql"
do
  if [[ -f "$ddl" ]]; then echo "[SQL_FILE] $ddl"; mysql_file "$ddl"; else echo "[INFO] optional ddl missing: $(basename "$ddl")"; fi
done

announce 0.2 "preflight required collection assets"
for f in \
  "$PROJECT_ROOT/pipelines/ingest/collect_raw_snapshot.py" \
  "$PROJECT_ROOT/pipelines/ingest/load_source_webserver_stage_v04.py" \
  "$PROJECT_ROOT/pipelines/collect/collector_wc_log_hit_v04.py" \
  "$PROJECT_ROOT/pipelines/ingest/load_event_log_raw_v04.py" \
  "$PROJECT_ROOT/pipelines/canonical/build_canonical_events_v04.py" \
  "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_batch_day.py" \
  "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_stream_day.py" \
  "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_operational_day.py" \
  "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_realism_day.py" \
  "$PROFILE_CONFIG"
do require_file "$f"; done

announce 0.3 "register pipeline run"
if [[ -n "$RUN_ID_INPUT" ]]; then
  RUN_ID="$RUN_ID_INPUT"
else
  RUN_ID="$($VENV_PYTHON -m pipelines.control.register_pipeline_run --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --processing-mode stream --runtime-mode replay --scenario-mode "$SOURCE_SCENARIO_MODE" --source-mode "$SOURCE_MODE" --exogenous-mode timeline_db)"
fi
echo "[INFO] run_id=$RUN_ID"

announce 1 "Phase1 source generation: journey -> behavior/transaction/state source files"
mkdir -p "$OUTPUT_DIR"
if [[ "$SCENARIO" == "baseline" && "$JOURNEYS" != "0" && "$JOURNEYS" -lt 1000 && "${ALLOW_SMALL_SMOKE_TEST:-0}" != "1" ]]; then
  echo "[FAIL] baseline completion requires UV-scale traffic. Use journeys=0 or ALLOW_SMALL_SMOKE_TEST=1."
  exit 1
fi
run_py_module simulator.customer_journey_sim.runners.generate_phase1 \
  --profile-config "$PROFILE_CONFIG" \
  --event-date "$DT_FROM" \
  --scenario "$SCENARIO" \
  --journeys "$JOURNEYS" \
  --out-dir "$OUTPUT_DIR" \
  --seed "$SEED"
MANIFEST="$OUTPUT_DIR/${PROFILE_ID}_${DT_FROM}_${SCENARIO}_manifest.json"
run_py_module simulator.customer_journey_sim.runners.validate_phase1 --manifest "$MANIFEST"

announce 1.1 "register Phase1 source files"
if [[ -n "$SOURCE_GEN_RUN_ID_INPUT" ]]; then
  SOURCE_GEN_RUN_ID="$SOURCE_GEN_RUN_ID_INPUT"
  run_py_module pipelines.commerce.source.register_phase1_source_files "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --input-dir "$OUTPUT_DIR" --source-gen-run-id "$SOURCE_GEN_RUN_ID"
else
  SOURCE_GEN_RUN_ID="$($VENV_PYTHON -m pipelines.commerce.source.register_phase1_source_files "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --scenario-name "$SCENARIO" --input-dir "$OUTPUT_DIR" | tail -1)"
fi
echo "[INFO] source_gen_run_id=$SOURCE_GEN_RUN_ID"

announce 2 "v0.4 behavior raw -> stage -> collector -> raw event -> canonical"
run_py_module pipelines.ingest.collect_raw_snapshot --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --input-dir "$OUTPUT_DIR" "${COMMON_DB_ARGS[@]}"
run_cmd "$VENV_PYTHON" "$PROJECT_ROOT/pipelines/ingest/load_source_webserver_stage_v04.py" --profile-id "$PROFILE_ID" --target-date "$DT_FROM" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --input-dir "$OUTPUT_DIR" --truncate-target "${COMMON_DB_ARGS[@]}"
run_cmd "$VENV_PYTHON" "$PROJECT_ROOT/pipelines/collect/collector_wc_log_hit_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --drop-rate "$DROP_RATE" --dup-rate "$DUP_RATE" --force-status-200-rate "${FORCE_STATUS_200_RATE:-0.00}" --page-event-mode "${PAGE_EVENT_MODE:-evt_or_page_type}" --host-default "$HOST_DEFAULT" --seed "$SEED" --truncate-target
run_cmd "$VENV_PYTHON" "$PROJECT_ROOT/pipelines/ingest/load_event_log_raw_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --truncate-target
run_cmd "$VENV_PYTHON" "$PROJECT_ROOT/pipelines/canonical/build_canonical_events_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --source-gen-run-id "$SOURCE_GEN_RUN_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate-target

announce 2.1 "v0.4 batch measurement primitives"
run_py_file_if_exists "$PROJECT_ROOT/pipelines/batch/build_stg_event_batch_from_canonical_v04_enriched.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate-target
run_py_file_if_exists "$PROJECT_ROOT/pipelines/batch/analyzer_b_v5_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --identity-mode uid_pcid_ip --session-timeout-sec 1800 --pv-mode view_only --truncate-target --write-legacy
run_py_file_if_exists "$PROJECT_ROOT/pipelines/batch/batch_quality_diagnostic_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate

announce 2.2 "v0.4 stream measurement primitives"
if [[ "$RUN_STREAM_KAFKA" == "true" ]]; then
  KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-127.0.0.1:9092}"
  TOPIC="stream.${PROFILE_ID}.${DT_FROM}.canonical.$(date +%Y%m%d%H%M%S)"
  CONSUMER_GROUP="collection-${PROFILE_ID}-${DT_FROM}-canonical-$(date +%Y%m%d%H%M%S)"
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/stream/kafka_producer_from_canonical_events_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --topic "$TOPIC" --kafka-bootstrap "$KAFKA_BOOTSTRAP"
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/stream/kafka_consumer_to_stg_event_stream_v04.py" "${COMMON_DB_ARGS[@]}" --kafka-bootstrap "$KAFKA_BOOTSTRAP" --topic "$TOPIC" --consumer-group "$CONSUMER_GROUP" --truncate-target-for-date "$DT_FROM" --profile-id "$PROFILE_ID" --run-id "$RUN_ID" --max-messages "${CONSUMER_MAX_MESSAGES:-200000}" --idle-timeout-sec 10
else
  echo "[INFO] RUN_STREAM_KAFKA=false; stream runners use available staged/canonical inputs only"
fi
for f in stream_duplicate_runner_v4.py stream_ordering_runner_v3.py stream_latency_runner_v3.py stream_completeness_runner_v3.py stream_reliability_aggregator_v5.py; do
  run_py_file_if_exists "$PROJECT_ROOT/pipelines/stream/$f" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO"
done
run_py_file_if_exists "$PROJECT_ROOT/pipelines/stream/stream_validation_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate

announce 2.3 "v0.4 operational measurement primitives"
run_py_file_if_exists "$PROJECT_ROOT/pipelines/operational/build_operational_events_from_canonical_v04.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate-target --commit-every "${REPLAY_COMMIT_EVERY:-1000}" --batch-size "${REPLAY_BATCH_SIZE:-1000}"
run_py_file_if_exists "$PROJECT_ROOT/pipelines/batch/run_batch_from_canonical.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --truncate-target
[[ "$BASELINE_TPM_INPUT" == "auto" ]] && BASELINE_TPM_INPUT="0"
run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/build_pipeline_performance_summary_minute_v6.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate-target --run-id "$RUN_ID" --baseline-throughput-per-minute "$BASELINE_TPM_INPUT" --throughput-baseline-mode "${THROUGHPUT_BASELINE_MODE:-auto_active_minutes}"
run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/build_pipeline_performance_summary_day_v2.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate-target
run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/build_pipeline_availability_run_v5.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate-target --run-id "$RUN_ID"
run_py_file_if_exists "$PROJECT_ROOT/pipelines/risk_ops/build_pipeline_availability_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --truncate-target

announce 3 "materialize Collection Reliability measurement day tables only"
run_py_file_if_exists "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_batch_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --truncate-target
run_py_file_if_exists "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_stream_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --truncate-target
run_py_file_if_exists "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_operational_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt-from "$DT_FROM" --dt-to "$DT_TO" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --truncate-target
run_py_file_if_exists "$PROJECT_ROOT/pipelines/measurement/python/build_measurement_realism_day.py" "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --dt "$DT_FROM" --baseline-dt "$BASELINE_DT" --run-id "$RUN_ID" --scenario-name "$SCENARIO" --truncate-target

cat <<DONE
[DONE] Collection Reliability only pipeline completed
PROFILE_ID=$PROFILE_ID
DT=$DT_FROM
SCENARIO=$SCENARIO
RUN_ID=$RUN_ID
SOURCE_GEN_RUN_ID=$SOURCE_GEN_RUN_ID
DROP_RATE=$DROP_RATE
DUP_RATE=$DUP_RATE
OUTPUT_DIR=$OUTPUT_DIR
LOG_FILE=$LOG_FILE
DONE
