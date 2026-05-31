#!/usr/bin/env bash
set -euo pipefail

KAFKA_HOME="${KAFKA_HOME:-$HOME/app/kafka}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KAFKA_CONFIG="${KAFKA_CONFIG:-$SCRIPT_DIR/kafka_server.properties}"
KAFKA_CLUSTER_ID_FILE="${KAFKA_CLUSTER_ID_FILE:-$KAFKA_HOME/.kraft_cluster_id}"

mkdir -p "$KAFKA_HOME/kraft-logs"

if [[ ! -f "$KAFKA_CLUSTER_ID_FILE" ]]; then
  CLUSTER_ID="$("$KAFKA_HOME/bin/kafka-storage.sh" random-uuid)"
  echo "$CLUSTER_ID" > "$KAFKA_CLUSTER_ID_FILE"
  "$KAFKA_HOME/bin/kafka-storage.sh" format -t "$CLUSTER_ID" -c "$KAFKA_CONFIG"
fi

nohup "$KAFKA_HOME/bin/kafka-server-start.sh" "$KAFKA_CONFIG" > "$KAFKA_HOME/kafka.log" 2>&1 &
echo $! > "$KAFKA_HOME/kafka.pid"

echo "[OK] Kafka started"
echo "PID: $(cat "$KAFKA_HOME/kafka.pid")"
echo "LOG: $KAFKA_HOME/kafka.log"
