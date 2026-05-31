#!/usr/bin/env bash
set -euo pipefail

GRAFANA_URL="${1:-http://127.0.0.1:3000}"
TOKEN="${2:-}"
DASH_UID="${3:-}"
OUT_DIR="${4:-./grafana_captures}"
FROM_MS="${5:-}"
TO_MS="${6:-}"

ORG_ID="${ORG_ID:-1}"
TZ_NAME="${TZ_NAME:-Asia/Seoul}"
THEME="${THEME:-dark}"
WIDTH="${WIDTH:-1600}"
HEIGHT="${HEIGHT:-900}"
FULL_HEIGHT="${FULL_HEIGHT:-2200}"
EXTRA_QUERY="${EXTRA_QUERY:-}"

if [[ -z "$TOKEN" || -z "$DASH_UID" || -z "$FROM_MS" || -z "$TO_MS" ]]; then
  echo "Usage: bash grafana_capture_dashboard.sh <grafana_url> <token> <dashboard_uid> <out_dir> <from_ms> <to_ms>"
  exit 1
fi

mkdir -p "$OUT_DIR"

META_JSON="$OUT_DIR/dashboard_meta.json"
USER_JSON="$OUT_DIR/api_user_check.json"

echo "[INFO] Check Grafana API auth"
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Grafana-Org-Id: $ORG_ID" \
  "$GRAFANA_URL/api/user" \
  -o "$USER_JSON"

if ! python3 - <<'PY' "$USER_JSON"
import json, sys
p = sys.argv[1]
try:
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    ok = isinstance(data, dict) and ("id" in data or "login" in data or "email" in data)
    raise SystemExit(0 if ok else 1)
except Exception:
    raise SystemExit(1)
PY
then
  echo "[ERROR] Grafana API authentication failed."
  echo "[INFO] Response saved: $USER_JSON"
  sed -n '1,40p' "$USER_JSON" || true
  exit 1
fi

echo "[INFO] Fetch dashboard metadata: uid=$DASH_UID"
curl -sS \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Grafana-Org-Id: $ORG_ID" \
  "$GRAFANA_URL/api/dashboards/uid/$DASH_UID" \
  -o "$META_JSON"

readarray -t META_INFO < <(python3 - <<'PY' "$META_JSON"
import json, re, sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

if "dashboard" not in data:
    print("ERROR")
    print("")
    print(json.dumps(data, ensure_ascii=False)[:1000])
    raise SystemExit(0)

dash = data.get("dashboard", {})
title = dash.get("title", "") or ""
slug = dash.get("slug", "") or ""

if not slug:
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    slug = s or "dashboard"

ids = []

def walk(items):
    for x in items:
        if not isinstance(x, dict):
            continue
        if "id" in x:
            ids.append(str(x["id"]))
        if isinstance(x.get("panels"), list):
            walk(x["panels"])
        if isinstance(x.get("rows"), list):
            walk(x["rows"])

walk(dash.get("panels", []))

seen = set()
ordered = []
for x in ids:
    if x not in seen:
        seen.add(x)
        ordered.append(x)

print(slug)
print(" ".join(ordered))
print("")
PY
)

DASH_SLUG="${META_INFO[0]:-}"
PANEL_IDS="${META_INFO[1]:-}"
META_ERR="${META_INFO[2]:-}"

if [[ "$DASH_SLUG" == "ERROR" ]]; then
  echo "[ERROR] Dashboard metadata response is not a normal dashboard JSON."
  echo "[INFO] Response preview:"
  echo "$META_ERR"
  echo "[INFO] Full response saved: $META_JSON"
  exit 1
fi

if [[ -z "$PANEL_IDS" ]]; then
  echo "[ERROR] No panel IDs found in dashboard metadata."
  echo "[INFO] Check saved metadata: $META_JSON"
  exit 1
fi

BASE_QUERY="orgId=$ORG_ID&from=$FROM_MS&to=$TO_MS&timezone=$TZ_NAME&theme=$THEME&width=$WIDTH&height=$HEIGHT"
if [[ -n "$EXTRA_QUERY" ]]; then
  BASE_QUERY="${BASE_QUERY}&${EXTRA_QUERY}"
fi

download_png() {
  local url="$1"
  local out_file="$2"

  local http_code
  http_code=$(curl -sS -L \
    -H "Authorization: Bearer $TOKEN" \
    -o "$out_file" \
    -w "%{http_code}" \
    "$url")

  if [[ "$http_code" != "200" ]]; then
    echo "[ERROR] HTTP $http_code -> $url"
    return 1
  fi

  if file "$out_file" | grep -qi 'PNG image data'; then
    echo "[OK] saved $out_file"
    return 0
  fi

  echo "[ERROR] Output is not PNG: $out_file"
  sed -n '1,20p' "$out_file" || true
  return 1
}

for PANEL_ID in $PANEL_IDS; do
  OUT_FILE="$OUT_DIR/panel_${PANEL_ID}.png"
  URL="$GRAFANA_URL/render/d-solo/$DASH_UID/$DASH_SLUG?panelId=$PANEL_ID&$BASE_QUERY"
  echo "[INFO] capture panel=$PANEL_ID"
  download_png "$URL" "$OUT_FILE" || echo "[WARN] panel capture failed: $PANEL_ID"
done

DASH_OUT="$OUT_DIR/dashboard_full.png"
FULL_QUERY="orgId=$ORG_ID&from=$FROM_MS&to=$TO_MS&timezone=$TZ_NAME&theme=$THEME&width=$WIDTH&height=$FULL_HEIGHT"
if [[ -n "$EXTRA_QUERY" ]]; then
  FULL_QUERY="${FULL_QUERY}&${EXTRA_QUERY}"
fi
FULL_URL="$GRAFANA_URL/render/d/$DASH_UID/$DASH_SLUG?$FULL_QUERY"

echo "[INFO] capture full dashboard"
download_png "$FULL_URL" "$DASH_OUT" || echo "[WARN] full dashboard capture failed"

echo "[OK] dashboard captures saved to $OUT_DIR"
