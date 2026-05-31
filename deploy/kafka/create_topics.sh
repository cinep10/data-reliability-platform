#!/usr/bin/env bash
set -euo pipefail

KAFKA_HOME="${KAFKA_HOME:-$HOME/app/kafka}"
BOOTSTRAP="${KAFKA_BOOTSTRAP:-127.0.0.1:9092}"

topics=(
  auth_event_topic
  loan_event_topic
  card_event_topic
  transfer_event_topic
  account_event_topic
  customer_event_topic
  branch_event_topic
  main_event_topic
  other_event_topic
)

for topic in "${topics[@]}"; do
  "$KAFKA_HOME/bin/kafka-topics.sh" \
    --bootstrap-server "$BOOTSTRAP" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions 3 \
    --replication-factor 1
done

echo "[OK] topics created"
