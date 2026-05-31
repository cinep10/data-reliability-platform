#!/usr/bin/env bash
set -euo pipefail
DT="${1:?target date required}"; JOURNEYS="${2:-0}"
PROJECT_ROOT="${PROJECT_ROOT:-/home/dwkim_nethru/data/etl/data-reliability-platform}"
cd "$PROJECT_ROOT"
echo "[CASE-OBS-001] 1/2 baseline reference"
./deploy/run_case_obs_001_baseline_reference.sh "$DT" "$JOURNEYS"
echo "[CASE-OBS-001] 2/2 WC collection anomaly with baseline"
./deploy/run_case_obs_001_wc_anomaly_with_baseline.sh "$DT" "$JOURNEYS"
