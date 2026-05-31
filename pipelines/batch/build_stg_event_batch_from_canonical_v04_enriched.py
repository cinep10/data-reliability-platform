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
from pipelines.common.v04_cookie_contract import CONTRACT_DB_COLS
from pipelines.common.v04_batch_common import infer_event_name, table_columns

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--dt-from", required=True)
    p.add_argument("--dt-to", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def connect(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass, database=args.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def main():
    args = parse_args()
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            src_cols = table_columns(cur, "canonical_events")
            raw_cols = table_columns(cur, "event_log_raw")
            dst_cols = table_columns(cur, "stg_event_batch")
            if args.truncate_target:
                cur.execute("DELETE FROM stg_event_batch WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, args.dt_from, args.dt_to))

            ce_cols = [
                "canonical_event_id","raw_event_id","run_id","profile_id","source_gen_run_id","target_date","event_time","service_domain",
                "event_type","uid","pcid","session_id","device_type","page_type","product_type","funnel_stage","status_code","bytes",
                "latency_ms","is_conversion","kv_raw","source_table","source_type"
            ] + CONTRACT_DB_COLS
            ce_select = [f"ce.{c}" for c in ce_cols if c in src_cols]

            raw_extra = []
            for c in ["path","query","url_norm","method","ip","ref","ua","evt","kv_raw","status","bytes","latency_ms"]:
                if c in raw_cols:
                    raw_extra.append(f"er.{c} AS raw_{c}")

            cur.execute(
                f"""
                SELECT {', '.join(ce_select + raw_extra)}
                FROM canonical_events ce
                LEFT JOIN event_log_raw er ON ce.raw_event_id = er.raw_event_id
                WHERE ce.profile_id=%s
                  AND ce.target_date BETWEEN %s AND %s
                  AND ce.run_id=%s
                ORDER BY ce.event_time, ce.canonical_event_id
                """,
                (args.profile_id, args.dt_from, args.dt_to, args.run_id),
            )
            rows = cur.fetchall()

            insert_cols = [
                "canonical_event_id","raw_event_id","run_id","profile_id","source_gen_run_id","dt","ts","event_name","semantic_event_name",
                "event_type","service_domain","funnel_stage","is_conversion","uid","pcid","sid","session_id","device_type","page_type",
                "product_type","status","status_code","latency_ms","bytes","path","query","url_norm","method","ip","ref","ua","kv_raw",
                "evt","load_status","batch_payload_json"
            ] + CONTRACT_DB_COLS
            insert_cols = [c for c in insert_cols if c in dst_cols]
            sql = f"INSERT INTO stg_event_batch ({','.join(insert_cols)}) VALUES ({','.join(['%s']*len(insert_cols))})"
            vals = []

            for r in rows:
                row_for_infer = {
                    **r,
                    "path": r.get("raw_path"),
                    "query": r.get("raw_query"),
                    "url_norm": r.get("raw_url_norm"),
                    "method": r.get("raw_method"),
                    "ip": r.get("raw_ip"),
                    "evt": r.get("raw_evt"),
                    "kv_raw": r.get("kv_raw") or r.get("raw_kv_raw"),
                    "status": r.get("status_code") or r.get("raw_status"),
                }
                semantic = infer_event_name(row_for_infer, "view_only")
                rowmap = {
                    **r,
                    "dt": r.get("target_date"),
                    "ts": r.get("event_time"),
                    "event_name": semantic,
                    "semantic_event_name": semantic,
                    "event_type": r.get("event_type") or semantic,
                    "status": r.get("status_code") or r.get("raw_status"),
                    "sid": r.get("session_id"),
                    "path": r.get("raw_path"),
                    "query": r.get("raw_query"),
                    "url_norm": r.get("raw_url_norm"),
                    "method": r.get("raw_method"),
                    "ip": r.get("raw_ip"),
                    "ref": r.get("raw_ref"),
                    "ua": r.get("raw_ua"),
                    "evt": r.get("raw_evt") or r.get("event_type"),
                    "kv_raw": r.get("kv_raw") or r.get("raw_kv_raw"),
                    "latency_ms": r.get("latency_ms") or r.get("raw_latency_ms"),
                    "bytes": r.get("bytes") or r.get("raw_bytes"),
                    "load_status": "success",
                    "batch_payload_json": json.dumps({"canonical_event_id": r.get("canonical_event_id"), "semantic_event_name": semantic, "canonical": r}, default=str, ensure_ascii=False),
                }
                vals.append([rowmap.get(c) for c in insert_cols])
            if vals:
                cur.executemany(sql, vals)
        conn.commit()
        print(f"[build_stg_event_batch_from_canonical_v04_enriched] rows={len(rows)} inserted={len(vals)}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
