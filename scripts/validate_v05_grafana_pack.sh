#!/usr/bin/env bash
set -euo pipefail
PACK_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
for f in "$PACK_DIR"/dashboards/*.json; do
  echo "[CHECK] $f"
  python3 -m json.tool "$f" >/dev/null
  grep -q "DS_MYSQL" "$f" || { echo "[FAIL] DS_MYSQL missing: $f"; exit 1; }
done
echo "[OK] dashboard JSON validation passed"
