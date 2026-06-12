#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
import pymysql
from kafka import KafkaConsumer

INSERT_SQL = """
INSERT INTO stg_event_stream
(
    profile_id, run_id, canonical_event_id, raw_event_id, source_gen_run_id,
    dt, ts, event_name, semantic_event_name, event_type, service_domain, funnel_stage, is_conversion,
    uid, pcid, sid, device_type, page_type, product_type, financial_product,
    stream_topic, stream_partition, stream_offset, sequence_no, producer_ts, ingest_ts, event_delay_ms,
    status, status_code, latency_ms, bytes, source_type, path, query, url_norm, method, ip, ref, ua, kv_raw, evt,
    load_status, anomaly_tag, schema_version, scenario_name, anomaly_type, stream_payload_json
)
VALUES
(
    %s,%s,%s,%s,%s,
    %s,%s,%s,%s,%s,%s,%s,%s,
    %s,%s,%s,%s,%s,%s,%s,
    %s,%s,%s,%s,%s,%s,%s,
    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
    %s,%s,%s,%s,%s,%s
)
"""

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-host", required=True)
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", default="")
    ap.add_argument("--db-name", required=True)
    ap.add_argument("--kafka-bootstrap", required=True)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--consumer-group", required=True)
    ap.add_argument("--truncate-target-for-date", required=True)
    ap.add_argument("--profile-id")
    ap.add_argument("--run-id", type=int)
    ap.add_argument("--max-messages", type=int, default=50000)
    ap.add_argument("--idle-timeout-sec", type=int, default=10)
    ap.add_argument("--poll-timeout-ms", type=int, default=1000)
    return ap.parse_args()

def connect_mysql(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset="utf8mb4", autocommit=False)

def parse_dt(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    s = str(s).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

def to_int(v, default=0):
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default

def row_tuple(args, msg_topic, msg_partition, msg_offset, value, seq, ingest_dt):
    producer_ts = parse_dt(value.get("producer_ts") or value.get("ts"))
    event_dt = value.get("dt") or (producer_ts.date().isoformat() if producer_ts else None)
    event_ts = value.get("ts") or value.get("producer_ts")
    latency_ms = to_int(value.get("latency_ms"), 0)
    status = to_int(value.get("status") or value.get("status_code"), 200)
    return (
        value.get("profile_id") or args.profile_id,
        value.get("run_id") or args.run_id,
        value.get("canonical_event_id"),
        value.get("raw_event_id"),
        value.get("source_gen_run_id"),
        event_dt,
        event_ts,
        value.get("event_name") or value.get("semantic_event_name") or value.get("evt") or "unknown",
        value.get("semantic_event_name") or value.get("event_name") or value.get("evt") or "unknown",
        value.get("event_type") or value.get("event_name"),
        value.get("service_domain") or "other",
        value.get("funnel_stage") or "browse",
        to_int(value.get("is_conversion"), 0),
        value.get("uid"),
        value.get("pcid"),
        value.get("sid"),
        value.get("device_type"),
        value.get("page_type"),
        value.get("product_type"),
        value.get("financial_product"),
        msg_topic,
        msg_partition,
        msg_offset,
        seq,
        producer_ts.strftime("%Y-%m-%d %H:%M:%S") if producer_ts else event_ts,
        ingest_dt.strftime("%Y-%m-%d %H:%M:%S"),
        latency_ms,
        status,
        status,
        latency_ms,
        to_int(value.get("bytes"), 0),
        value.get("source_type") or "canonical_events",
        value.get("path"),
        value.get("query"),
        value.get("url_norm"),
        value.get("method"),
        value.get("ip"),
        value.get("ref"),
        value.get("ua"),
        value.get("kv_raw"),
        value.get("evt"),
        "success",
        value.get("anomaly_tag") or value.get("scenario_name"),
        value.get("schema_version"),
        value.get("scenario_name"),
        value.get("anomaly_type"),
        json.dumps(value, ensure_ascii=False, default=str),
    )

def main():
    args = parse_args()
    conn = connect_mysql(args)
    cur = conn.cursor()
    consumer = KafkaConsumer(
        args.topic,
        bootstrap_servers=args.kafka_bootstrap.split(","),
        group_id=args.consumer_group,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        consumer_timeout_ms=1000,
    )
    batch = []
    total = 0
    seq = 0
    last_msg_time = time.time()

    def flush():
        nonlocal batch
        if batch:
            cur.executemany(INSERT_SQL, batch)
            conn.commit()
            print(f"[kafka_consumer_v04] flushed={len(batch)} total={total}")
            batch = []

    try:
        if args.profile_id and args.run_id:
            cur.execute("DELETE FROM stg_event_stream WHERE profile_id=%s AND dt=%s AND run_id=%s", (args.profile_id, args.truncate_target_for_date, args.run_id))
        else:
            cur.execute("DELETE FROM stg_event_stream WHERE dt=%s", (args.truncate_target_for_date,))
        conn.commit()
        print(f"[INFO] consumer started topic={args.topic} group={args.consumer_group}")
        while True:
            now = time.time()
            got_any = False
            records = consumer.poll(timeout_ms=args.poll_timeout_ms)
            for tp, messages in records.items():
                for msg in messages:
                    got_any = True
                    seq += 1
                    total += 1
                    last_msg_time = now
                    batch.append(row_tuple(args, tp.topic, tp.partition, msg.offset, msg.value, seq, datetime.now()))
                    if len(batch) >= 1000:
                        flush()
                    if total >= args.max_messages:
                        flush()
                        print(f"[kafka_consumer_v04] reached max_messages={args.max_messages}")
                        print(f"[kafka_consumer_v04] consumed={total}")
                        return
            if not got_any and (now - last_msg_time) >= args.idle_timeout_sec:
                flush()
                print(f"[kafka_consumer_v04] idle timeout reached ({args.idle_timeout_sec}s), exiting")
                break
    finally:
        try:
            consumer.close()
        except Exception:
            pass
        cur.close()
        conn.close()
    print(f"[kafka_consumer_v04] consumed={total}")

if __name__ == "__main__":
    main()
