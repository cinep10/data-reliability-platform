#!/usr/bin/env bash
set -euo pipefail

# CASE-OBS-001 Phase2-C4 statistical reliability backfill runner.
# Runs 7d/30d history for baseline and selected anomaly scenarios, refreshes target-date
# statistical evidence, validates meaning, and compacts heavy source/canonical runtime rows.

PROJECT_ROOT="${PROJECT_ROOT:-/Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform}"
RUN_SCRIPT="${RUN_SCRIPT:-$PROJECT_ROOT/deploy/run_v05_reliability_pipeline_commerce_mac_host.sh}"
COMPACT_SCRIPT="${COMPACT_SCRIPT:-$PROJECT_ROOT/deploy/compact_v05_backfill_runtime_mac_host.sh}"
BASH_BIN="${BASH_BIN:-/opt/homebrew/bin/bash}"
VENV_PYTHON="${VENV_PYTHON:-$PROJECT_ROOT/.venv/bin/python3}"
[[ -x "$VENV_PYTHON" ]] || VENV_PYTHON="${PYTHON_BIN:-python3}"
RSCRIPT_BIN="${RSCRIPT_BIN:-Rscript}"

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-nethru}"
DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"
DB_NAME="${DB_NAME:-weblog}"
PROFILE_ID="${PROFILE_ID:-commerce_deliver}"
JOURNEYS="${JOURNEYS:-0}"
DAYS="${DAYS:-7}"
FROM_DATE=""
TO_DATE=""
TARGET_DATE=""
SCENARIOS="${SCENARIOS:-baseline,source_partial_missing,source_wc_collection_missing}"

BASELINE_WINDOW="${BASELINE_WINDOW:-30d}"
BASELINE_SCENARIO="${BASELINE_SCENARIO:-baseline}"
BASELINE_SCIENCE_STAT_MIN_SAMPLE_DAYS="${BASELINE_SCIENCE_STAT_MIN_SAMPLE_DAYS:-3}"
OBS_BASELINE_MIN_SAMPLE_DAYS="${OBS_BASELINE_MIN_SAMPLE_DAYS:-3}"
OBS_EXPECTED_RECENT_DAYS="${OBS_EXPECTED_RECENT_DAYS:-7}"
OBS_THRESHOLD_MIN_SAMPLE_DAYS="${OBS_THRESHOLD_MIN_SAMPLE_DAYS:-3}"

COMPACT_AFTER_EACH_RUN="${COMPACT_AFTER_EACH_RUN:-true}"
REMOVE_SOURCE_FILES="${REMOVE_SOURCE_FILES:-true}"
RUN_TARGET_VALIDATION="${RUN_TARGET_VALIDATION:-true}"
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-false}"
DRY_RUN="${DRY_RUN:-false}"
BACKFILL_BEHAVIOR_SCOPE_VALIDATION="${BACKFILL_BEHAVIOR_SCOPE_VALIDATION:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-id) PROFILE_ID="$2"; shift 2 ;;
    --scenarios) SCENARIOS="$2"; shift 2 ;;
    --journeys) JOURNEYS="$2"; shift 2 ;;
    --days) DAYS="$2"; shift 2 ;;
    --target-date) TARGET_DATE="$2"; shift 2 ;;
    --from-date) FROM_DATE="$2"; shift 2 ;;
    --to-date) TO_DATE="$2"; shift 2 ;;
    --compact-after-each-run) COMPACT_AFTER_EACH_RUN="$2"; shift 2 ;;
    --remove-source-files) REMOVE_SOURCE_FILES="$2"; shift 2 ;;
    --continue-on-error) CONTINUE_ON_ERROR="true"; shift ;;
    --dry-run) DRY_RUN="true"; shift ;;
    *) echo "[ERROR] unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$FROM_DATE" || -z "$TO_DATE" ]]; then
  [[ -n "$TARGET_DATE" ]] || { echo "[ERROR] provide --target-date with --days, or --from-date and --to-date"; exit 1; }
  TO_DATE="$TARGET_DATE"
  FROM_DATE="$(python3 - <<PY
from datetime import date, timedelta
end=date.fromisoformat('$TO_DATE')
days=int('$DAYS')
print((end - timedelta(days=days-1)).isoformat())
PY
)"
else
  TARGET_DATE="${TARGET_DATE:-$TO_DATE}"
fi

[[ -f "$RUN_SCRIPT" ]] || { echo "[ERROR] missing RUN_SCRIPT=$RUN_SCRIPT"; exit 1; }
[[ -f "$COMPACT_SCRIPT" ]] || { echo "[ERROR] missing COMPACT_SCRIPT=$COMPACT_SCRIPT"; exit 1; }

cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"
COMMON_DB_ARGS=(--db-host "$DB_HOST" --db-port "$DB_PORT" --db-user "$DB_USER" --db-pass "$DB_PASSWORD" --db-name "$DB_NAME")
run_cmd(){ printf '[RUN]'; printf ' %q' "$@"; printf '\n'; "$@"; }
mysql_db(){ mysql -N -s -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" "$@"; }

mapfile -t DATES < <(python3 - <<PY
from datetime import date, timedelta
start=date.fromisoformat('$FROM_DATE')
end=date.fromisoformat('$TO_DATE')
if end < start:
    raise SystemExit('to-date must be >= from-date')
d=start
while d <= end:
    print(d.isoformat())
    d += timedelta(days=1)
PY
)
IFS=',' read -r -a SCENARIO_LIST <<< "$SCENARIOS"

echo "[STAT_BACKFILL] profile_id=$PROFILE_ID dates=$FROM_DATE..$TO_DATE target_date=$TARGET_DATE days=${#DATES[@]} scenarios=$SCENARIOS"
echo "[STAT_BACKFILL] compact_after_each_run=$COMPACT_AFTER_EACH_RUN remove_source_files=$REMOVE_SOURCE_FILES dry_run=$DRY_RUN"

resolve_lineage(){
  local d="$1"; local scenario="$2"
  DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_NAME="$DB_NAME" PROFILE_ID="$PROFILE_ID" TARGET_DATE="$d" SCENARIO="$scenario" "$VENV_PYTHON" - <<'PYLINEAGE'
import os, sys, pymysql
con = pymysql.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']), user=os.environ['DB_USER'], password=os.environ.get('DB_PASSWORD',''), database=os.environ['DB_NAME'], charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=True)
profile=os.environ['PROFILE_ID']; dt=os.environ['TARGET_DATE']; scenario=os.environ['SCENARIO']
candidates=[('v05_baseline_science_statistical_evidence_day','target_date'),('v05_reconciliation_measurement_day','target_date'),('v05_obs_metric_gap_day','target_date'),('canonical_behavior_events','target_date'),('pipeline_run_registry','dt_from')]
try:
  with con.cursor() as cur:
    for table, date_col in candidates:
      cur.execute("SELECT COUNT(*) c FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
      if cur.fetchone()['c'] == 0: continue
      cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
      cols={r['column_name'] for r in cur.fetchall()}
      if 'run_id' not in cols: continue
      if date_col not in cols:
        date_col = 'target_date' if 'target_date' in cols else ('dt' if 'dt' in cols else None)
      if not date_col: continue
      where=[]; params=[]
      if 'profile_id' in cols: where.append('profile_id=%s'); params.append(profile)
      where.append(f"{date_col}=%s"); params.append(dt)
      if 'scenario_name' in cols: where.append('(scenario_name=%s OR scenario_name IS NULL OR scenario_name=\'\')'); params.append(scenario)
      sg = 'source_gen_run_id' in cols
      sql=f"SELECT run_id{', source_gen_run_id' if sg else ', 0 AS source_gen_run_id'} FROM {table} WHERE {' AND '.join(where)} AND run_id IS NOT NULL ORDER BY run_id DESC{', source_gen_run_id DESC' if sg else ''} LIMIT 1"
      cur.execute(sql, tuple(params)); row=cur.fetchone()
      if row:
        print(f"{int(row['run_id'])}\t{int(row.get('source_gen_run_id') or 0)}\t{table}"); sys.exit(0)
finally:
  con.close()
sys.exit(1)
PYLINEAGE
}

run_pipeline(){
  local d="$1"; local scenario="$2"
  echo
  echo "[STAT_BACKFILL] run date=$d scenario=$scenario"
  local cmd=("$BASH_BIN" "$RUN_SCRIPT" "$d" "$scenario" "$JOURNEYS")
  printf '[RUN]'; printf ' %q' "${cmd[@]}"; printf '\n'
  if [[ "$DRY_RUN" == "true" ]]; then return 0; fi
  PROFILE_ID="$PROFILE_ID" \
  RUN_V05_OBS_EXPECTED_MODEL=true \
  RUN_V05_OBS_EXPECTED_VALIDATION=true \
  RUN_V05_OBS_THRESHOLD_CALIBRATION=true \
  RUN_V05_OBS_THRESHOLD_VALIDATION=true \
  RUN_V05_OBS_FORECAST_INTERFACE_VALIDATION=true \
  RUN_V05_BASELINE_SCIENCE_STAT_EVIDENCE=true \
  RUN_V05_BASELINE_SCIENCE_STAT_VALIDATION=true \
  BASELINE_SCIENCE_STAT_MIN_SAMPLE_DAYS="$BASELINE_SCIENCE_STAT_MIN_SAMPLE_DAYS" \
  RUN_V05_BEHAVIOR_SCOPE_VALIDATION="$BACKFILL_BEHAVIOR_SCOPE_VALIDATION" \
  "${cmd[@]}"
}

compact_run(){
  local d="$1"; local scenario="$2"
  [[ "$COMPACT_AFTER_EACH_RUN" == "true" || "$COMPACT_AFTER_EACH_RUN" == "1" ]] || return 0
  local lineage run_id source_gen_run_id
  lineage="$(resolve_lineage "$d" "$scenario" || true)"
  run_id="$(printf '%s' "$lineage" | awk '{print $1}')"
  source_gen_run_id="$(printf '%s' "$lineage" | awk '{print $2}')"
  [[ -n "${run_id:-}" ]] || run_id="all"
  [[ -n "${source_gen_run_id:-}" && "$source_gen_run_id" != "0" ]] || source_gen_run_id="all"
  echo "[STAT_BACKFILL] compact date=$d scenario=$scenario run_id=$run_id source_gen_run_id=$source_gen_run_id"
  if [[ "$DRY_RUN" == "true" ]]; then return 0; fi
  run_cmd "$BASH_BIN" "$COMPACT_SCRIPT" --profile-id "$PROFILE_ID" --target-date "$d" --scenario "$scenario" --run-id "$run_id" --source-gen-run-id "$source_gen_run_id" --remove-source-files "$REMOVE_SOURCE_FILES"
}

for d in "${DATES[@]}"; do
  for scenario in "${SCENARIO_LIST[@]}"; do
    scenario="$(echo "$scenario" | xargs)"
    [[ -n "$scenario" ]] || continue
    if run_pipeline "$d" "$scenario"; then
      compact_run "$d" "$scenario"
    else
      rc=$?
      echo "[ERROR] pipeline failed date=$d scenario=$scenario rc=$rc"
      if [[ "$CONTINUE_ON_ERROR" == "true" ]]; then continue; fi
      exit "$rc"
    fi
  done
done

if [[ "$RUN_TARGET_VALIDATION" == "true" || "$RUN_TARGET_VALIDATION" == "1" ]]; then
  echo
  echo "[STAT_BACKFILL] target validation target_date=$TARGET_DATE"
  for scenario in "${SCENARIO_LIST[@]}"; do
    scenario="$(echo "$scenario" | xargs)"; [[ -n "$scenario" ]] || continue
    lineage="$(resolve_lineage "$TARGET_DATE" "$scenario" || true)"
    run_id="$(printf '%s' "$lineage" | awk '{print $1}')"
    source_gen_run_id="$(printf '%s' "$lineage" | awk '{print $2}')"
    if [[ -z "${run_id:-}" ]]; then
      echo "[WARN] skip validation; lineage not found target_date=$TARGET_DATE scenario=$scenario"
      continue
    fi
    [[ -n "${source_gen_run_id:-}" && "$source_gen_run_id" != "0" ]] || source_gen_run_id="all"
    echo "[STAT_BACKFILL] validate scenario=$scenario run_id=$run_id source_gen_run_id=$source_gen_run_id"
    run_cmd "$VENV_PYTHON" -m pipelines.commerce.validation.validate_v05_baseline_science_statistical_evidence "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$TARGET_DATE" --scenario-name "$scenario" --run-id "$run_id" --source-gen-run-id "$source_gen_run_id" --baseline-window "$BASELINE_WINDOW" --domains batch_metric_delta,observability_expected,reconciliation_measurement --allow-missing-domain --allow-low-sample
    run_cmd "$VENV_PYTHON" -m pipelines.commerce.validation.validate_v05_reliability_statistical_evidence_interface "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$TARGET_DATE" --scenario-name "$scenario" --run-id "$run_id" --source-gen-run-id "$source_gen_run_id" --baseline-window "$BASELINE_WINDOW" --allow-baseline-suppression
    run_cmd "$VENV_PYTHON" -m pipelines.commerce.validation.validate_v05_statistical_evidence_meaning "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$TARGET_DATE" --scenario-name "$scenario" --run-id "$run_id" --source-gen-run-id "$source_gen_run_id" --baseline-window "$BASELINE_WINDOW" --allow-low-sample
  done
fi

echo "[DONE] CASE-OBS-001 Phase2-C4 statistical reliability backfill completed"
