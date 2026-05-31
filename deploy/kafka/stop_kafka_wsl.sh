#!/usr/bin/env bash
set -euo pipefail

KAFKA_HOME="${KAFKA_HOME:-$HOME/app/kafka}"

if [[ -f "$KAFKA_HOME/kafka.pid" ]]; then
  PID="$(cat "$KAFKA_HOME/kafka.pid")"
  kill "$PID" || true
  rm -f "$KAFKA_HOME/kafka.pid"
  echo "[OK] Kafka stopped"
else
  echo "[INFO] kafka.pid not found"
fi
