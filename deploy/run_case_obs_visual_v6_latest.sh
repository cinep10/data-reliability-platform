#!/usr/bin/env bash
set -euo pipefail
DT="${1:?usage: $0 YYYY-MM-DD scenario_name}"
SCENARIO="${2:?usage: $0 YYYY-MM-DD scenario_name}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${REPO_ROOT}/.venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi
exec "$PYTHON" -m pipelines.commerce.visualization.render_case_obs_001_figures_for_latest_run \
  --repo-root "$REPO_ROOT" \
  --target-date "$DT" \
  --scenario-name "$SCENARIO" \
  --validate \
  --require-visual-v6
