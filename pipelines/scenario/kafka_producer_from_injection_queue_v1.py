#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, date

import pymysql
from kafka import KafkaProducer


def json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat(sep=" ")
    return str(obj)


def connect_mysql(args):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-host", required=True)
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", default="")
    ap.add_argument("--db-name", required=True)
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--kafka-bootstrap", required=True)
    args = ap.parse_args()

    conn = connect_mysql(args)
    producer = KafkaProducer(
        bootstrap_servers=args.kafka_bootstrap.split(","),
        value_serializer=lambda x: json.dumps(x, default=json_default).encode("utf-8"),
        key_serializer=lambda x: str(x).encode("utf-8"),
    )

    sent = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM stream_injection_event_queue
                WHERE profile_id=%s
                  AND dt BETWEEN %s AND %s
                ORDER BY dt, ts, queue_id
                """,
                (args.profile_id, args.dt_from, args.dt_to),
            )
            for row in cur.fetchall():
                payload = {
                    "raw_event_id": row["raw_event_id"],
                    "dt": str(row["dt"]),
                    "ts": row["ts"],
                    "event_name": row.get("event_name"),
                    "service_domain": row.get("service_domain"),
                    "funnel_stage": row.get("funnel_stage"),
                    "is_conversion": int(row.get("is_conversion") or 0),
                    "uid": row.get("uid"),
                    "pcid": row.get("pcid"),
                    "sid": row.get("sid"),
                    "producer_ts": row.get("ts"),
                    "status": int(row.get("status") or 200),
                    "latency_ms": int(row.get("latency_ms") or 0),
                    "source_type": row.get("source_type") or "weblog",
                    "path": row.get("path"),
                    "evt": row.get("evt"),
                    "anomaly_tag": row.get("anomaly_tag"),
                }
                producer.send(args.topic, key=f"{row['queue_id']}", value=payload)
                sent += 1

        producer.flush()
    finally:
        producer.close()
        conn.close()

    print(f"[kafka_producer_from_injection_queue_v1] topic={args.topic} sent={sent}")


if __name__ == "__main__":
    main()
