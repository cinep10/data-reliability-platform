#!/usr/bin/env bash
set -euo pipefail
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_TOKEN="${GRAFANA_TOKEN:?Set GRAFANA_TOKEN}"
DS_MYSQL_UID="${DS_MYSQL_UID:-mysql-weblog}"
PACK_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
for f in "$PACK_DIR"/dashboards/*.json; do
  echo "[IMPORT] $f"
  tmp="$(mktemp)"
  python3 -c 'import json,sys; p,ds=sys.argv[1],sys.argv[2]; d=json.load(open(p)); d=json.loads(json.dumps(d).replace("${DS_MYSQL}",ds)); print(json.dumps({"dashboard":d,"overwrite":True,"inputs":[{"name":"DS_MYSQL","type":"datasource","pluginId":"mysql","value":ds}]}))' "$f" "$DS_MYSQL_UID" > "$tmp"
  curl -fsS -H "Authorization: Bearer $GRAFANA_TOKEN" -H "Content-Type: application/json" -X POST "$GRAFANA_URL/api/dashboards/import" -d @"$tmp" >/dev/null
  rm -f "$tmp"
done
echo "[OK] imported v0.5 dashboards"
