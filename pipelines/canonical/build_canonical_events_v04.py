#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path as _Path

PROJECT_ROOT = _Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json

import pymysql

from pipelines.common.v04_cookie_contract import CONTRACT_DB_COLS

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
    p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def connect(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass, database=args.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def cols(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}

def main():
    args = parse_args()
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            src_cols = cols(cur, "event_log_raw")
            dst_cols = cols(cur, "canonical_events")
            if args.truncate_target:
                cur.execute("DELETE FROM canonical_events WHERE profile_id=%s AND target_date BETWEEN %s AND %s AND run_id=%s", (args.profile_id, args.dt_from, args.dt_to, args.run_id))
            select_cols = [c for c in [
                "raw_event_id","profile_id","source_gen_run_id","exogenous_snapshot_id","source_file_id","raw_snapshot_id","dt","ts","service_domain",
                "event_type","event_name","uid","pcid","sid","device_type","page_type","product_type","funnel_stage","status_code","status","bytes",
                "latency_ms","is_conversion","source_table","source_type","source_mode","exogenous_mode","kv_raw","payload_json"
            ] + CONTRACT_DB_COLS if c in src_cols]
            where = "profile_id=%s AND dt BETWEEN %s AND %s"
            params = [args.profile_id, args.dt_from, args.dt_to]
            if args.source_gen_run_id and "source_gen_run_id" in src_cols:
                where += " AND source_gen_run_id=%s"; params.append(args.source_gen_run_id)
            cur.execute(f"SELECT {','.join(select_cols)} FROM event_log_raw WHERE {where} ORDER BY dt, ts, raw_event_id", params)
            rows = cur.fetchall()
            insert_cols = [
                "run_id","profile_id","source_gen_run_id","exogenous_snapshot_id","source_file_id","raw_snapshot_id","raw_event_id","target_date",
                "event_time","event_date","service_domain","event_type","uid","pcid","session_id","device_type","page_type","product_type",
                "funnel_stage","channel","status_code","bytes","latency_ms","is_conversion","source_table","source_type","source_mode",
                "exogenous_mode","kv_raw","canonical_payload_json"
            ] + CONTRACT_DB_COLS
            insert_cols = [c for c in insert_cols if c in dst_cols]
            sql = f"INSERT INTO canonical_events ({','.join(insert_cols)}) VALUES ({','.join(['%s']*len(insert_cols))})"
            vals = []
            for r in rows:
                event_type = r.get("event_type") or r.get("event_name") or "view"
                rowmap = {
                    **r,
                    "run_id": args.run_id,
                    "target_date": r.get("dt"),
                    "event_time": r.get("ts"),
                    "event_date": r.get("dt"),
                    "session_id": r.get("sid"),
                    "status_code": r.get("status_code") or r.get("status"),
                    "channel": r.get("cc"),
                    "event_type": event_type,
                    "canonical_payload_json": json.dumps({"raw_event_id":r.get("raw_event_id"),"event_log_raw":r}, default=str, ensure_ascii=False),
                }
                vals.append([rowmap.get(c) for c in insert_cols])
            if vals:
                cur.executemany(sql, vals)
        conn.commit()
        print(f"[build_canonical_events_v04] rows={len(rows)} inserted={len(vals)}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
