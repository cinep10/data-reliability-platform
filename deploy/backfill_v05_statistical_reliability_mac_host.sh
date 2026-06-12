#!/usr/bin/env bash
set -euo pipefail

# CASE-OBS-001 Phase2-C4 statistical reliability scenario-calendar backfill.
# Difference from backfill_v05_obs_baseline_mac_host.sh:
#   - obs_baseline backfill: baseline-only reference refresh.
#   - this script: scenario-calendar sensitivity test for Statistical Reliability Analytics.
#
# Calendar policy:
#   - one scenario per day, never all scenarios on the same day.
#   - first days baseline, middle anomaly days, final target-date baseline.
#   - this makes baseline history statistically meaningful while injecting anomaly pulses.

PROJECT_ROOT="${PROJECT_ROOT:-/Users/dwkim/dev/repo/data-reliability-platform}"
RUN_SCRIPT="${RUN_SCRIPT:-$PROJECT_ROOT/deploy/run_v05_reliability_pipeline_commerce_mac_host.sh}"
COMPACT_SCRIPT="${COMPACT_SCRIPT:-$PROJECT_ROOT/deploy/compact_v05_backfill_runtime_mac_host.sh}"
BASH_BIN="${BASH_BIN:-/opt/homebrew/bin/bash}"
VENV_PYTHON="${VENV_PYTHON:-$PROJECT_ROOT/.venv/bin/python3}"
[[ -x "$VENV_PYTHON" ]] || VENV_PYTHON="${PYTHON_BIN:-python3}"

DB_HOST="${DB_HOST:-127.0.0.1}"; DB_PORT="${DB_PORT:-3306}"; DB_USER="${DB_USER:-nethru}"; DB_PASSWORD="${DB_PASSWORD:-${DB_PASS:-nethru1234}}"; DB_NAME="${DB_NAME:-weblog}"
PROFILE_ID="${PROFILE_ID:-commerce_deliver}"
JOURNEYS="${JOURNEYS:-0}"
DAYS="${DAYS:-7}"
TARGET_DATE=""; FROM_DATE=""; TO_DATE=""
BASELINE_SCENARIO="${BASELINE_SCENARIO:-baseline}"
ANOMALY_DAYS="${ANOMALY_DAYS:-3}"
ANOMALY_SCENARIOS="${ANOMALY_SCENARIOS:-source_partial_missing,source_wc_collection_missing,source_partial_missing}"
BASELINE_WINDOW="${BASELINE_WINDOW:-30d}"
MIN_SAMPLE_DAYS="${MIN_SAMPLE_DAYS:-3}"
COMPACT_AFTER_EACH_RUN="${COMPACT_AFTER_EACH_RUN:-true}"
REMOVE_SOURCE_FILES="${REMOVE_SOURCE_FILES:-true}"
ALLOW_LOW_SAMPLE="${ALLOW_LOW_SAMPLE:-false}"
RUN_TARGET_VALIDATION="${RUN_TARGET_VALIDATION:-true}"
RUN_SENSITIVITY_VALIDATION="${RUN_SENSITIVITY_VALIDATION:-true}"
CONTINUE_ON_ERROR="${CONTINUE_ON_ERROR:-false}"
DRY_RUN="${DRY_RUN:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-id) PROFILE_ID="$2"; shift 2 ;;
    --journeys) JOURNEYS="$2"; shift 2 ;;
    --days) DAYS="$2"; shift 2 ;;
    --target-date) TARGET_DATE="$2"; shift 2 ;;
    --from-date) FROM_DATE="$2"; shift 2 ;;
    --to-date) TO_DATE="$2"; shift 2 ;;
    --baseline-scenario) BASELINE_SCENARIO="$2"; shift 2 ;;
    --anomaly-days) ANOMALY_DAYS="$2"; shift 2 ;;
    --anomaly-scenarios) ANOMALY_SCENARIOS="$2"; shift 2 ;;
    --compact-after-each-run) COMPACT_AFTER_EACH_RUN="$2"; shift 2 ;;
    --remove-source-files) REMOVE_SOURCE_FILES="$2"; shift 2 ;;
    --allow-low-sample) ALLOW_LOW_SAMPLE="$2"; shift 2 ;;
    --continue-on-error) CONTINUE_ON_ERROR="true"; shift ;;
    --dry-run) DRY_RUN="true"; shift ;;
    *) echo "[ERROR] unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$FROM_DATE" || -z "$TO_DATE" ]]; then
  [[ -n "$TARGET_DATE" ]] || { echo "[ERROR] provide --target-date with --days, or --from-date/--to-date"; exit 1; }
  TO_DATE="$TARGET_DATE"
  FROM_DATE="$(python3 - <<PY
from datetime import date,timedelta
end=date.fromisoformat('$TO_DATE'); days=int('$DAYS')
print((end-timedelta(days=days-1)).isoformat())
PY
)"
else
  TARGET_DATE="${TARGET_DATE:-$TO_DATE}"
fi

[[ -f "$RUN_SCRIPT" ]] || { echo "[ERROR] missing RUN_SCRIPT=$RUN_SCRIPT"; exit 1; }
cd "$PROJECT_ROOT"; export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"
COMMON_DB_ARGS=(--db-host "$DB_HOST" --db-port "$DB_PORT" --db-user "$DB_USER" --db-pass "$DB_PASSWORD" --db-name "$DB_NAME")
run_cmd(){ printf '[RUN]'; printf ' %q' "$@"; printf '\n'; "$@"; }
mysql_file(){ mysql -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" < "$1"; }

if [[ -f "$PROJECT_ROOT/sql/079_v05_batch_metric_delta_history_mariadb.sql" ]]; then
  echo "[SQL_FILE] $PROJECT_ROOT/sql/079_v05_batch_metric_delta_history_mariadb.sql"
  mysql_file "$PROJECT_ROOT/sql/079_v05_batch_metric_delta_history_mariadb.sql"
fi

mapfile -t DATES < <(python3 - <<PY
from datetime import date,timedelta
s=date.fromisoformat('$FROM_DATE'); e=date.fromisoformat('$TO_DATE')
if e<s: raise SystemExit('to-date must be >= from-date')
d=s
while d<=e:
  print(d.isoformat()); d+=timedelta(days=1)
PY
)
IFS=',' read -r -a ANOMS <<< "$ANOMALY_SCENARIOS"

make_calendar(){
  python3 - <<PY
from datetime import date,timedelta
start=date.fromisoformat('$FROM_DATE'); end=date.fromisoformat('$TO_DATE')
base='$BASELINE_SCENARIO'; anoms=[x.strip() for x in '$ANOMALY_SCENARIOS'.split(',') if x.strip()]
anomaly_days=int('$ANOMALY_DAYS')
dates=[]; d=start
while d<=end:
  dates.append(d.isoformat()); d+=timedelta(days=1)
n=len(dates)
slots=[]
if anomaly_days>0 and n>=4:
  first=max(1, (n-anomaly_days)//2)
  slots=list(range(first, min(first+anomaly_days, n-1)))
for i,dt in enumerate(dates):
  sc=base
  if i in slots:
    sc=anoms[slots.index(i)%len(anoms)] if anoms else base
  if i==n-1:
    sc=base
  print(f'{dt}\t{sc}')
PY
}
mapfile -t CALENDAR < <(make_calendar)

echo "[STAT_BACKFILL] profile_id=$PROFILE_ID dates=$FROM_DATE..$TO_DATE target_date=$TARGET_DATE days=${#DATES[@]}"
echo "[STAT_BACKFILL] baseline_scenario=$BASELINE_SCENARIO anomaly_days=$ANOMALY_DAYS anomaly_scenarios=$ANOMALY_SCENARIOS"
echo "[STAT_BACKFILL] one scenario per day calendar:"
printf '  %s\n' "${CALENDAR[@]}"

resolve_lineage(){
  local d="$1"; local scenario="$2"
  DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" DB_NAME="$DB_NAME" PROFILE_ID="$PROFILE_ID" TARGET_DATE="$d" SCENARIO="$scenario" "$VENV_PYTHON" - <<'PYLINEAGE'
import os, sys, pymysql
con=pymysql.connect(host=os.environ['DB_HOST'],port=int(os.environ['DB_PORT']),user=os.environ['DB_USER'],password=os.environ.get('DB_PASSWORD',''),database=os.environ['DB_NAME'],charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor,autocommit=True)
profile=os.environ['PROFILE_ID']; dt=os.environ['TARGET_DATE']; scenario=os.environ['SCENARIO']
candidates=[('v05_baseline_science_statistical_evidence_day','target_date'),('v05_reconciliation_measurement_day','target_date'),('v05_batch_metric_delta_day','dt'),('canonical_behavior_events','target_date'),('pipeline_run_registry','dt_from')]
try:
  with con.cursor() as cur:
    for table,date_col in candidates:
      cur.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s',(table,)); cols={r['column_name'] for r in cur.fetchall()}
      if not cols or 'run_id' not in cols: continue
      if date_col not in cols: date_col='target_date' if 'target_date' in cols else ('dt' if 'dt' in cols else None)
      if not date_col: continue
      where=[]; params=[]
      if 'profile_id' in cols: where.append('profile_id=%s'); params.append(profile)
      where.append(f'{date_col}=%s'); params.append(dt)
      if 'scenario_name' in cols: where.append('(scenario_name=%s OR scenario_name IS NULL OR scenario_name="")'); params.append(scenario)
      sg='source_gen_run_id' in cols
      sql=f"SELECT run_id{', source_gen_run_id' if sg else ', 0 AS source_gen_run_id'} FROM {table} WHERE {' AND '.join(where)} AND run_id IS NOT NULL ORDER BY run_id DESC{', source_gen_run_id DESC' if sg else ''} LIMIT 1"
      cur.execute(sql,tuple(params)); row=cur.fetchone()
      if row:
        print(f"{int(row['run_id'])}\t{int(row.get('source_gen_run_id') or 0)}\t{table}"); sys.exit(0)
finally: con.close()
sys.exit(1)
PYLINEAGE
}

run_pipeline(){
  local d="$1"; local scenario="$2"
  echo; echo "[STAT_BACKFILL] run date=$d scenario=$scenario"
  local cmd=("$BASH_BIN" "$RUN_SCRIPT" "$d" "$scenario" "$JOURNEYS")
  printf '[RUN]'; printf ' %q' "${cmd[@]}"; printf '\n'
  [[ "$DRY_RUN" == "true" ]] && return 0
  PROFILE_ID="$PROFILE_ID" RUN_V05_OBS_EXPECTED_MODEL=true RUN_V05_OBS_EXPECTED_VALIDATION=true RUN_V05_OBS_THRESHOLD_CALIBRATION=true RUN_V05_OBS_THRESHOLD_VALIDATION=true RUN_V05_OBS_FORECAST_INTERFACE_VALIDATION=true RUN_V05_BASELINE_SCIENCE_STAT_EVIDENCE=true RUN_V05_BASELINE_SCIENCE_STAT_VALIDATION=true BASELINE_SCIENCE_STAT_MIN_SAMPLE_DAYS="$MIN_SAMPLE_DAYS" RUN_V05_BEHAVIOR_SCOPE_VALIDATION=false "${cmd[@]}"
}

compact_run(){
  local d="$1"; local scenario="$2"
  [[ "$COMPACT_AFTER_EACH_RUN" == "true" || "$COMPACT_AFTER_EACH_RUN" == "1" ]] || return 0
  [[ -f "$COMPACT_SCRIPT" ]] || { echo "[WARN] missing compact script; skip"; return 0; }
  local lineage run_id sgid
  lineage="$(resolve_lineage "$d" "$scenario" || true)"; run_id="$(printf '%s' "$lineage" | awk '{print $1}')"; sgid="$(printf '%s' "$lineage" | awk '{print $2}')"
  [[ -n "${run_id:-}" ]] || run_id="all"; [[ -n "${sgid:-}" && "$sgid" != "0" ]] || sgid="all"
  run_cmd "$BASH_BIN" "$COMPACT_SCRIPT" --profile-id "$PROFILE_ID" --target-date "$d" --scenario "$scenario" --run-id "$run_id" --source-gen-run-id "$sgid" --remove-source-files "$REMOVE_SOURCE_FILES"
}

for entry in "${CALENDAR[@]}"; do
  d="$(printf '%s' "$entry" | awk '{print $1}')"; sc="$(printf '%s' "$entry" | awk '{print $2}')"
  if run_pipeline "$d" "$sc"; then compact_run "$d" "$sc"; else rc=$?; echo "[ERROR] pipeline failed date=$d scenario=$sc rc=$rc"; [[ "$CONTINUE_ON_ERROR" == "true" ]] || exit "$rc"; fi
done

if [[ "$RUN_TARGET_VALIDATION" == "true" || "$RUN_TARGET_VALIDATION" == "1" ]]; then
  echo; echo "[STAT_BACKFILL] target validation target_date=$TARGET_DATE scenario=$BASELINE_SCENARIO"
  lineage="$(resolve_lineage "$TARGET_DATE" "$BASELINE_SCENARIO" || true)"; run_id="$(printf '%s' "$lineage" | awk '{print $1}')"; sgid="$(printf '%s' "$lineage" | awk '{print $2}')"
  if [[ -n "${run_id:-}" ]]; then
    [[ -n "${sgid:-}" && "$sgid" != "0" ]] || sgid="all"
    run_cmd "$VENV_PYTHON" -m pipelines.commerce.validation.validate_v05_baseline_science_statistical_evidence "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$TARGET_DATE" --scenario-name "$BASELINE_SCENARIO" --run-id "$run_id" --source-gen-run-id "$sgid" --baseline-window "$BASELINE_WINDOW" --domains batch_metric_delta,observability_expected,reconciliation_measurement --allow-missing-domain --allow-low-sample
    MEANING_ARGS=("${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --target-date "$TARGET_DATE" --scenario-name "$BASELINE_SCENARIO" --run-id "$run_id" --source-gen-run-id "$sgid" --baseline-window "$BASELINE_WINDOW" --domains batch_metric_delta,observability_expected,reconciliation_measurement --min-sample-days "$MIN_SAMPLE_DAYS")
    [[ "$ALLOW_LOW_SAMPLE" == "true" || "$ALLOW_LOW_SAMPLE" == "1" ]] && MEANING_ARGS+=(--allow-low-sample)
    run_cmd "$VENV_PYTHON" -m pipelines.commerce.validation.validate_v05_statistical_evidence_meaning "${MEANING_ARGS[@]}"
  else
    echo "[WARN] target lineage not found; skip target validators"
  fi
  if [[ "$RUN_SENSITIVITY_VALIDATION" == "true" || "$RUN_SENSITIVITY_VALIDATION" == "1" ]]; then
    run_cmd "$VENV_PYTHON" -m pipelines.commerce.validation.validate_v05_scenario_sensitivity "${COMMON_DB_ARGS[@]}" --profile-id "$PROFILE_ID" --from-date "$FROM_DATE" --to-date "$TO_DATE" --baseline-scenario "$BASELINE_SCENARIO" --anomaly-scenarios "$ANOMALY_SCENARIOS" --min-anomaly-days "$ANOMALY_DAYS" --allow-no-sensitivity
  fi
fi

echo "[DONE] CASE-OBS-001 Phase2-C4 statistical reliability scenario-calendar backfill completed"
