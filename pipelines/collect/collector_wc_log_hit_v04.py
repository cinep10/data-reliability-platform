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
    p.add_argument("--runtime-mode", default="none", choices=["none", "wc_collection_missing", "source_partial_missing", "source_latency_degradation", "source_identity_drift", "source_schema_drift", "source_no_data"])
    p.add_argument("--wc-missing-base-rate", type=float, default=0.18)
    p.add_argument("--wc-missing-checkout-rate", type=float, default=0.35)
    p.add_argument("--wc-missing-product-rate", type=float, default=0.22)
    p.add_argument("--wc-missing-ios-safari-rate", type=float, default=0.40)
    p.add_argument("--wc-missing-rule-mode", choices=["broad", "segment_targeted"], default="broad")
    p.add_argument("--wc-missing-target-rule-id", default="none")
    p.add_argument("--wc-missing-target-reason", default="none")
    p.add_argument("--wc-missing-target-app-platform", default="*")
    p.add_argument("--wc-missing-target-app-version", default="*")
    p.add_argument("--wc-missing-target-sdk-version", default="*")
    p.add_argument("--wc-missing-target-rate", type=float, default=0.0)
    p.add_argument("--wc-missing-target-funnel-stages", default="*")
    p.add_argument("--wc-missing-target-event-names", default="*")
    p.add_argument("--wc-missing-target-conversion-only", default="false")
    p.add_argument("--wc-missing-target-action", choices=["drop_row", "null_uid", "rewrite_url"], default="drop_row")
    p.add_argument("--wc-missing-rewrite-from-path", default="/order/chicken")
    p.add_argument("--wc-missing-rewrite-to-path", default="/order/pizza")
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


def _tokens(value: Any) -> set[str]:
    text = str(value or "").strip()
    if not text or text == "*":
        return set()
    return {x.strip().lower() for x in text.split(",") if x.strip()}


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def _match_token(value: Any, expected: str) -> bool:
    """Match wildcard or comma-separated target tokens.

    This lets one generic SDK scenario target both iOS and Android SDK versions
    without adding case-specific authority features downstream.
    """
    expected_raw = str(expected or "*").strip().lower()
    if not expected_raw or expected_raw == "*":
        return True
    actual = str(value or "").strip().lower()
    tokens = [x.strip() for x in expected_raw.split(",") if x.strip()]
    return actual in tokens


def _row_text(r: dict[str, Any]) -> str:
    fields = ["evt", "event_type", "page_type", "funnel_stage", "path", "url_norm", "url_raw", "url_full"]
    return " ".join(str(r.get(k) or "").lower() for k in fields)


def _is_conversion_row(r: dict[str, Any]) -> bool:
    """Strict critical-event detection used by purchase-event targeted missing.

    Do not treat generic checkout/payment pages as conversion rows. Otherwise a
    purchase-event scenario can accidentally remove ordinary PV/page events and
    look like broad collection loss.
    """
    if _truthy(r.get("is_conversion")):
        return True
    evt_text = " ".join(str(r.get(k) or "").strip().lower() for k in ("evt", "event_type"))
    return any(token in evt_text for token in ("conversion", "purchase", "purchase_success", "payment_success", "order_complete"))


def _target_match(r: dict[str, Any], args) -> bool:
    if not _match_token(r.get("app_platform"), args.wc_missing_target_app_platform):
        return False
    if not _match_token(r.get("app_version"), args.wc_missing_target_app_version):
        return False
    if not _match_token(r.get("sdk_version"), args.wc_missing_target_sdk_version):
        return False

    if _truthy(args.wc_missing_target_conversion_only) and not _is_conversion_row(r):
        return False

    stages = _tokens(args.wc_missing_target_funnel_stages)
    if stages:
        hay = _row_text(r)
        if not any(s in hay for s in stages):
            return False

    event_names = _tokens(args.wc_missing_target_event_names)
    if event_names:
        hay = _row_text(r)
        # If conversion_only is true, conversion flag is sufficient. Otherwise use explicit event/path tokens.
        if not (_truthy(args.wc_missing_target_conversion_only) and _is_conversion_row(r)):
            if not any(e in hay for e in event_names):
                return False
    return True



def _replace_path_value(value: Any, from_path: str, to_path: str) -> Any:
    if value is None:
        return value
    text = str(value)
    if not from_path or from_path == "*":
        return text
    return text.replace(from_path, to_path)


def _rewrite_url_value(value: Any, from_path: str, to_path: str, col: str, host: str | None = None) -> tuple[Any, bool]:
    """Rewrite URL/path for semantic attribution collapse scenarios.

    Earlier Phase4-D rewrote only when the literal default path (/order/chicken)
    already existed. In the realistic commerce simulator, order/category URLs may
    be encoded differently, so the SDK semantic scenario could keep all WC paths
    identical to WebServer reality and produce url_semantic_shift=0.

    For rewrite_url action, the meaning is: the targeted SDK collapses the
    observed URL/category attribution into one canonical observed bucket.
    Therefore, if from_path is '*' or the literal source path is absent, force the
    targeted WC row into to_path while preserving the row itself and its identity.
    """
    if value is None:
        text = ""
    else:
        text = str(value)
    force = (not str(from_path or "").strip()) or str(from_path).strip() == "*"
    matched = (not force) and str(from_path) in text
    if matched:
        return text.replace(str(from_path), str(to_path)), True
    if not force and text and str(to_path) in text:
        return text, False
    # Force-collapse to one observed path when the concrete source URL token is
    # not present in the generated data. This is intentional for SDK tagging
    # collapse: traffic remains visible, but semantic URL attribution changes.
    if col in {"path", "url_norm", "url_raw"}:
        return str(to_path), text != str(to_path)
    if col == "url_full":
        h = str(host or "www.finance-bank.example.com").strip() or "www.finance-bank.example.com"
        return f"https://{h}{to_path}", True
    return str(to_path), True


def _apply_target_action(r: dict[str, Any], args) -> dict[str, Any]:
    """Apply realistic WC-layer corruption while keeping WebServer reality intact.

    drop_row: collection completeness loss.
    null_uid: identity integrity breakage; keep the hit but remove login identity.
    rewrite_url: semantic/attribution distortion; keep the hit and identity but rewrite URL/path.
    """
    action = getattr(args, "wc_missing_target_action", "drop_row")
    if action == "null_uid":
        r["uid"] = None
        # Keep pcid/sid so traffic remains visible while login/user identity is damaged.
        kv = str(r.get("kv_raw") or "")
        if kv:
            kv = re.sub(r"(^|[;&\s])uid=[^;&\s]*", r"\1uid=", kv)
            kv = re.sub(r"(^|[;&\s])login_id=[^;&\s]*", r"\1login_id=", kv)
            r["kv_raw"] = kv
    elif action == "rewrite_url":
        from_path = str(getattr(args, "wc_missing_rewrite_from_path", "*") or "*")
        to_path = str(getattr(args, "wc_missing_rewrite_to_path", "/order/pizza") or "/order/pizza")
        host = str(r.get("host") or getattr(args, "host_default", "www.finance-bank.example.com"))
        for col in ("path", "url_raw", "url_full", "url_norm"):
            if col in r:
                r[col], _ = _rewrite_url_value(r.get(col), from_path, to_path, col, host)
        # Keep original service/funnel identity untouched; this simulates a tagging semantic collapse, not a business state change.
    return r

def wc_collection_missing_rate(r, args):
    if args.runtime_mode != "wc_collection_missing":
        return args.drop_rate
    if args.wc_missing_rule_mode == "segment_targeted":
        if _target_match(r, args):
            return min(max(args.wc_missing_target_rate, 0.0), 1.0)
        return min(max(args.drop_rate, 0.0), 1.0)
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
                "app_platform","app_version","sdk_version",
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
                "app_platform","app_version","sdk_version",
                "scenario_id","scenario_name","source_generation_scenario"
            ] + CONTRACT_DB_COLS
            insert_cols = unique_existing_cols(insert_cols, dst_cols)
            sql = f"INSERT INTO stg_wc_log_hit ({','.join(insert_cols)}) VALUES ({','.join(['%s']*len(insert_cols))})"
            inserts = []
            page_rows = dropped = dup = 0
            targeted_page_rows = targeted_dropped = targeted_mutated = 0
            for r0 in rows:
                if not is_page_event(r0, args.page_event_mode):
                    continue
                page_rows += 1
                r = dict(r0)
                is_targeted = args.runtime_mode == "wc_collection_missing" and args.wc_missing_rule_mode == "segment_targeted" and _target_match(r, args)
                if is_targeted:
                    targeted_page_rows += 1
                rate = wc_collection_missing_rate(r, args)
                action = getattr(args, "wc_missing_target_action", "drop_row") if is_targeted else "drop_row"
                if random.random() < rate:
                    if action == "drop_row":
                        dropped += 1
                        if is_targeted:
                            targeted_dropped += 1
                        continue
                    r = _apply_target_action(r, args)
                    targeted_mutated += 1
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
            rate_msg = (f"wc_missing_rule_mode={args.wc_missing_rule_mode} "
                        f"wc_missing_base_rate={args.wc_missing_base_rate} wc_missing_checkout_rate={args.wc_missing_checkout_rate} "
                        f"wc_missing_product_rate={args.wc_missing_product_rate} wc_missing_ios_safari_rate={args.wc_missing_ios_safari_rate} "
                        f"target_rule={args.wc_missing_target_rule_id} target_app={args.wc_missing_target_app_platform}/{args.wc_missing_target_app_version} "
                        f"target_sdk={args.wc_missing_target_sdk_version} target_rate={args.wc_missing_target_rate:.2f} "
                        f"target_event_names={args.wc_missing_target_event_names} conversion_only={args.wc_missing_target_conversion_only} "
                        f"target_action={args.wc_missing_target_action} rewrite={args.wc_missing_rewrite_from_path}->{args.wc_missing_rewrite_to_path} "
                        f"targeted_page_rows={targeted_page_rows} targeted_dropped={targeted_dropped} targeted_mutated={targeted_mutated}")
        else:
            rate_msg = "wc_missing_rates=not_applied"
        print(f"[collector_wc_log_hit_v04] runtime_mode={args.runtime_mode} source_rows={len(rows)} page_rows={page_rows} dropped={dropped} dup_added={dup} wc_rows={len(inserts)} {rate_msg}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
