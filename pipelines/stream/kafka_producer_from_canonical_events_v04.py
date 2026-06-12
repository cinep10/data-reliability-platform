#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pymysql
from kafka import KafkaProducer
from pipelines.common.v04_stream_common import json_default, parse_json, first_present, to_iso, to_int, infer_event_name

def connect_mysql(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset="utf8mb4", autocommit=True,
                           cursorclass=pymysql.cursors.DictCursor)

def table_columns(conn, table_name):
    with conn.cursor() as cur:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s ORDER BY ordinal_position", (table_name,))
        return [r["column_name"] for r in cur.fetchall()]

def normalize_row(row, topic, run_id):
    event_time = first_present(row, ["event_time", "ts", "producer_ts"])
    ts = to_iso(event_time)
    target_date = first_present(row, ["target_date", "event_date", "dt"])
    if target_date is None and isinstance(ts, str) and len(ts) >= 10:
        target_date = ts[:10]
    semantic = infer_event_name(row)
    return {
        "profile_id": row.get("profile_id"),
        "canonical_event_id": row.get("canonical_event_id"),
        "raw_event_id": row.get("raw_event_id") or row.get("canonical_event_id"),
        "run_id": run_id,
        "source_gen_run_id": row.get("source_gen_run_id"),
        "dt": str(target_date) if target_date is not None else None,
        "ts": ts,
        "producer_ts": ts,
        "event_name": semantic,
        "semantic_event_name": semantic,
        "event_type": row.get("event_type") or semantic,
        "service_domain": row.get("service_domain") or "other",
        "funnel_stage": row.get("funnel_stage") or "browse",
        "is_conversion": to_int(row.get("is_conversion"), 0),
        "uid": row.get("uid"),
        "pcid": row.get("pcid"),
        "sid": row.get("session_id") or row.get("sid"),
        "device_type": row.get("device_type"),
        "page_type": row.get("page_type"),
        "product_type": row.get("product_type"),
        "financial_product": row.get("financial_product"),
        "status": to_int(row.get("status_code") or row.get("status"), 200),
        "status_code": to_int(row.get("status_code") or row.get("status"), 200),
        "latency_ms": to_int(row.get("latency_ms"), 0),
        "bytes": to_int(row.get("bytes"), 0),
        "path": row.get("path"),
        "query": row.get("query"),
        "url_norm": row.get("url_norm"),
        "method": row.get("method"),
        "ip": row.get("ip"),
        "ref": row.get("ref"),
        "ua": row.get("ua"),
        "kv_raw": row.get("kv_raw"),
        "evt": row.get("evt") or row.get("event_type"),
        "source_type": row.get("source_type") or "canonical_events",
        "schema_version": row.get("schema_version"),
        "scenario_name": row.get("scenario_name"),
        "anomaly_type": row.get("anomaly_type"),
        "stream_topic": topic,
        "canonical_payload_json": parse_json(row.get("canonical_payload_json")),
    }

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
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--kafka-bootstrap", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = connect_mysql(args)
    producer = None
    sent = 0
    try:
        ce_cols = set(table_columns(conn, "canonical_events"))
        er_cols = set(table_columns(conn, "event_log_raw"))
        ce_base = ["canonical_event_id","raw_event_id","run_id","profile_id","source_gen_run_id","target_date","event_time","event_date","service_domain",
                   "event_type","uid","pcid","session_id","device_type","page_type","product_type","funnel_stage","status_code","bytes","latency_ms",
                   "is_conversion","source_type","canonical_payload_json","schema_version","scenario_name","anomaly_type","financial_product"]
        selects = [f"ce.{c}" for c in ce_base if c in ce_cols]
        for c in ["path","query","url_norm","method","ip","ref","ua","kv_raw","evt","status","bytes","latency_ms"]:
            if c in er_cols:
                selects.append(f"er.{c} AS {c}")
        select_sql = f"""
            SELECT {', '.join(selects)}
            FROM canonical_events ce
            LEFT JOIN event_log_raw er ON ce.raw_event_id = er.raw_event_id
            WHERE ce.profile_id=%s
              AND ce.target_date BETWEEN %s AND %s
              AND ce.run_id=%s
            ORDER BY ce.event_time, ce.canonical_event_id
        """
        if not args.dry_run:
            producer = KafkaProducer(
                bootstrap_servers=args.kafka_bootstrap.split(","),
                value_serializer=lambda x: json.dumps(x, default=json_default, ensure_ascii=False).encode("utf-8"),
                key_serializer=lambda x: str(x).encode("utf-8") if x is not None else None,
            )
        with conn.cursor() as cur:
            cur.execute(select_sql, (args.profile_id, args.dt_from, args.dt_to, args.run_id))
            for row in cur.fetchall():
                payload = normalize_row(row, args.topic, args.run_id)
                key = payload.get("canonical_event_id") or f"{payload.get('dt')}:{sent}"
                if not args.dry_run:
                    producer.send(args.topic, key=key, value=payload)
                sent += 1
        if producer is not None:
            producer.flush()
    finally:
        if producer is not None:
            producer.close()
        conn.close()
    mode = "dry_run" if args.dry_run else "sent"
    print(f"[kafka_producer_from_canonical_events_v04] topic={args.topic} {mode}={sent} profile_id={args.profile_id} dt_from={args.dt_from} dt_to={args.dt_to} run_id={args.run_id}")

if __name__ == "__main__":
    main()
