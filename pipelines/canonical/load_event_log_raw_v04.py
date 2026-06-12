#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path as _Path

PROJECT_ROOT = _Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json
from typing import Any

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
    p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--dt-from", required=True)
    p.add_argument("--dt-to", required=True)
    p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()

def connect(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass, database=args.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def cols(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}

def key_col(cur, table):
    c = cols(cur, table)
    for k in ("wc_log_id", "id"):
        if k in c:
            return k
    raise RuntimeError(f"no key column found for {table}")

def lineage(cur, args):
    out = {"source_gen_run_id": args.source_gen_run_id, "exogenous_snapshot_id": None, "source_file_id": None, "raw_snapshot_id": None, "source_mode": "simulator_file_generate", "exogenous_mode": "timeline_db"}
    if not args.source_gen_run_id:
        return out
    tables = {}
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE()")
    for r in cur.fetchall():
        tables[r["table_name"]] = True
    if "source_file_manifest" in tables:
        c = cols(cur, "source_file_manifest")
        sel = [x for x in ("source_file_id","exogenous_snapshot_id") if x in c]
        if sel:
            where = ["source_gen_run_id=%s"]
            params: list[Any] = [args.source_gen_run_id]
            if "target_date" in c:
                where.append("target_date=%s"); params.append(args.dt_from)
            cur.execute(f"SELECT {','.join(sel)} FROM source_file_manifest WHERE {' AND '.join(where)} ORDER BY 1 LIMIT 1", params)
            r = cur.fetchone()
            if r:
                out.update({k: r.get(k) for k in sel})
    if "raw_snapshot_manifest" in tables:
        c = cols(cur, "raw_snapshot_manifest")
        sel = [x for x in ("raw_snapshot_id","exogenous_snapshot_id","source_mode") if x in c]
        if sel:
            cur.execute(f"SELECT {','.join(sel)} FROM raw_snapshot_manifest WHERE source_gen_run_id=%s ORDER BY 1 LIMIT 1", (args.source_gen_run_id,))
            r = cur.fetchone()
            if r:
                for k in sel:
                    out[k] = r.get(k) or out.get(k)
    return out

def main():
    args = parse_args()
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            src_cols = cols(cur, "stg_wc_log_hit")
            dst_cols = cols(cur, "event_log_raw")
            k = key_col(cur, "stg_wc_log_hit")
            if args.truncate_target:
                cur.execute("DELETE FROM event_log_raw WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, args.dt_from, args.dt_to))
            select_cols = [k] + [c for c in [
                "dt","ts","ip","method","url_raw","url_full","url_norm","host","path","query","status","bytes","ref","ua","kv_raw",
                "uid","pcid","sid","device_type","evt","event_type","accept_lang","cc","page_type","product_type","latency_ms",
                "profile_id","source_gen_run_id","service_domain","funnel_stage","is_conversion"
            ] + CONTRACT_DB_COLS if c in src_cols]
            where = "profile_id=%s AND dt BETWEEN %s AND %s"
            params: list[Any] = [args.profile_id, args.dt_from, args.dt_to]
            if args.source_gen_run_id and "source_gen_run_id" in src_cols:
                where += " AND source_gen_run_id=%s"; params.append(args.source_gen_run_id)
            cur.execute(f"SELECT {','.join(select_cols)} FROM stg_wc_log_hit WHERE {where} ORDER BY dt, ts, {k}", params)
            rows = cur.fetchall()
            lin = lineage(cur, args)
            insert_cols = [
                "dt","ts","source_row_id","source_table","profile_id","service_domain","funnel_stage","is_conversion","uid","pcid","sid",
                "device_type","page_type","product_type","ip","method","host","path","query","url_raw","url_full","url_norm","status","bytes",
                "latency_ms","ref","ua","kv_raw","evt","event_type","accept_lang","cc","payload_json","source_type","log_date","event_time",
                "status_code","event_name","source_gen_run_id","exogenous_snapshot_id","source_file_id","raw_snapshot_id","source_mode","exogenous_mode"
            ] + CONTRACT_DB_COLS
            insert_cols = [c for c in insert_cols if c in dst_cols]
            sql = f"INSERT INTO event_log_raw ({','.join(insert_cols)}) VALUES ({','.join(['%s']*len(insert_cols))})"
            vals = []
            for r in rows:
                derived = {
                    "source_row_id": r.get(k),
                    "source_table": "stg_wc_log_hit",
                    "source_type": "wc",
                    "log_date": r.get("dt"),
                    "event_time": r.get("ts"),
                    "status_code": r.get("status"),
                    "event_name": r.get("event_type") or r.get("evt") or r.get("page_type") or "view",
                    **lin,
                }
                payload = json.dumps({"source_table":"stg_wc_log_hit","source_id":r.get(k),"raw_fields":dict(r),"lineage":lin}, default=str, ensure_ascii=False)
                rowmap = {**r, **derived, "payload_json": payload}
                vals.append([rowmap.get(c) for c in insert_cols])
            if vals:
                cur.executemany(sql, vals)
        conn.commit()
        print(f"[load_event_log_raw_v04] rows={len(rows)} inserted={len(vals)}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
