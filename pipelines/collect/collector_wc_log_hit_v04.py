#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path as _Path
from typing import Any

PROJECT_ROOT = _Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pymysql
from pipelines.common.v04_cookie_contract import CONTRACT_DB_COLS

STATIC_EXT_RE = re.compile(r"\.(css|js|png|jpg|jpeg|gif|ico|map|woff|woff2|ttf|eot|svg|webp|zip|txt|xml|json)$", re.I)


def parse_args():
    p = argparse.ArgumentParser(description="WC collector with optional CASE-OBS collection-layer missing mode")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", default="")
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--dt-from", required=True)
    p.add_argument("--dt-to", required=True)
    p.add_argument("--drop-rate", type=float, default=0.05)
    p.add_argument("--dup-rate", type=float, default=0.01)
    p.add_argument("--force-status-200-rate", type=float, default=0.0)
    p.add_argument("--page-event-mode", choices=["view_only", "evt_or_page_type"], default="evt_or_page_type")
    p.add_argument("--truncate-target", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--host-default", default="www.finance-bank.example.com")
    p.add_argument("--runtime-mode", default="none", choices=["none", "wc_collection_missing"])
    p.add_argument("--wc-missing-base-rate", type=float, default=0.18)
    p.add_argument("--wc-missing-checkout-rate", type=float, default=0.35)
    p.add_argument("--wc-missing-product-rate", type=float, default=0.22)
    p.add_argument("--wc-missing-ios-safari-rate", type=float, default=0.40)
    return p.parse_args()


def connect(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset="utf8mb4", autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)


def table_cols(cur, table: str):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def unique_existing_cols(candidates, existing_cols):
    """Return columns that exist in destination/source while preserving order and removing duplicates.

    CONTRACT_DB_COLS may include scenario identity columns already listed explicitly.
    Without this guard, INSERT can fail with:
      Column 'scenario_name' specified twice
    """
    out = []
    seen = set()
    for c in candidates:
        if c in existing_cols and c not in seen:
            out.append(c)
            seen.add(c)
    return out


def is_static(path):
    return bool(STATIC_EXT_RE.search((path or "").lower()))


def is_page_event(r, mode):
    if is_static(r.get("path")):
        return False
    evt = (r.get("evt") or "").lower()
    page_type = r.get("page_type") or ""
    return evt == "view" or (mode == "evt_or_page_type" and page_type != "")


def force_status(status, rate):
    if random.random() < rate:
        return 200
    return int(status or 200)


def wc_collection_missing_rate(r, args):
    if args.runtime_mode != "wc_collection_missing":
        return args.drop_rate
    path = (r.get("path") or "").lower()
    ua = (r.get("ua") or "").lower()
    page_type = (r.get("page_type") or "").lower()
    funnel_stage = (r.get("funnel_stage") or "").lower()
    rate = args.wc_missing_base_rate
    if any(x in path or x in page_type or x in funnel_stage for x in ("checkout", "payment", "order")):
        rate = max(rate, args.wc_missing_checkout_rate)
    elif "product" in path or "product" in page_type or "product" in funnel_stage:
        rate = max(rate, args.wc_missing_product_rate)
    if ("iphone" in ua or "ipad" in ua or "ios" in ua) and "safari" in ua and "chrome" not in ua:
        rate = max(rate, args.wc_missing_ios_safari_rate)
    return min(max(rate, 0.0), 1.0)


def main():
    args = parse_args()
    random.seed(args.seed)
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            src_cols = table_cols(cur, "stg_webserver_log_hit")
            dst_cols = table_cols(cur, "stg_wc_log_hit")
            if args.truncate_target:
                cur.execute("DELETE FROM stg_wc_log_hit WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, args.dt_from, args.dt_to))
            select_cols = [
                "id","profile_id","source_gen_run_id","dt","ts","ip","method","url_raw","url_full","url_norm","host","path","query",
                "status","bytes","ref","ua","kv_raw","uid","pcid","sid","device_type","evt","event_type","accept_lang","cc",
                "page_type","product_type","latency_ms","service_domain","funnel_stage","is_conversion",
                "scenario_id","scenario_name","source_generation_scenario"
            ] + CONTRACT_DB_COLS
            select_cols = unique_existing_cols(select_cols, src_cols)
            where = "profile_id=%s AND dt BETWEEN %s AND %s"
            params: list[Any] = [args.profile_id, args.dt_from, args.dt_to]
            if args.source_gen_run_id and "source_gen_run_id" in src_cols:
                where += " AND source_gen_run_id=%s"
                params.append(args.source_gen_run_id)
            cur.execute(f"SELECT {','.join(select_cols)} FROM stg_webserver_log_hit WHERE {where} ORDER BY dt, ts, id", params)
            rows = cur.fetchall()
            insert_cols = [
                "dt","ts","ip","method","url_raw","url_full","url_norm","host","path","query","status","bytes","ref","ua","kv_raw",
                "uid","pcid","sid","device_type","evt","event_type","accept_lang","cc","page_type","product_type","latency_ms",
                "profile_id","source_gen_run_id","service_domain","funnel_stage","is_conversion",
                "scenario_id","scenario_name","source_generation_scenario"
            ] + CONTRACT_DB_COLS
            insert_cols = unique_existing_cols(insert_cols, dst_cols)
            sql = f"INSERT INTO stg_wc_log_hit ({','.join(insert_cols)}) VALUES ({','.join(['%s']*len(insert_cols))})"
            inserts = []
            page_rows = dropped = dup = 0
            for r in rows:
                if not is_page_event(r, args.page_event_mode):
                    continue
                page_rows += 1
                if random.random() < wc_collection_missing_rate(r, args):
                    dropped += 1
                    continue
                r["status"] = force_status(r.get("status"), args.force_status_200_rate)
                r["host"] = r.get("host") or args.host_default
                vals = [r.get(c) for c in insert_cols]
                inserts.append(vals)
                if random.random() < args.dup_rate:
                    inserts.append(vals)
                    dup += 1
            if inserts:
                cur.executemany(sql, inserts)
        conn.commit()
        if args.runtime_mode == "wc_collection_missing":
            rate_msg = (f"wc_missing_base_rate={args.wc_missing_base_rate} wc_missing_checkout_rate={args.wc_missing_checkout_rate} "
                        f"wc_missing_product_rate={args.wc_missing_product_rate} wc_missing_ios_safari_rate={args.wc_missing_ios_safari_rate}")
        else:
            rate_msg = "wc_missing_rates=not_applied"
        print(f"[collector_wc_log_hit_v04] runtime_mode={args.runtime_mode} source_rows={len(rows)} page_rows={page_rows} dropped={dropped} dup_added={dup} wc_rows={len(inserts)} {rate_msg}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
