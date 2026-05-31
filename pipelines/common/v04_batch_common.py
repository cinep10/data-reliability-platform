#!/usr/bin/env python3
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Optional
import pymysql

KV_PAIR_RE = re.compile(r'(?:^|;\s*)([A-Za-z0-9_\-]+)=([^;]*)', re.I)
STATIC_EXT_RE = re.compile(r'\.(css|js|png|jpg|jpeg|gif|ico|map|woff|woff2|ttf|eot|svg|webp|zip|txt)$', re.I)
GENERIC_EVENT_NAMES = {"", "view", "click", "conversion", "submit", "success", "browse", "page", "other"}

def d(val: Any) -> Decimal:
    try:
        return Decimal(str(val if val is not None else 0))
    except Exception:
        return Decimal("0")

def q(v: Any) -> str:
    return str(Decimal(str(v)).quantize(Decimal("0.000001")))

def parse_kv(kv_raw: Optional[str]) -> dict[str, str]:
    if not kv_raw:
        return {}
    return {m.group(1).lower(): m.group(2).strip() for m in KV_PAIR_RE.finditer(str(kv_raw).strip())}

def table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table_name,))
    return int(cur.fetchone()["cnt"]) > 0

def table_columns(cur, table_name: str) -> set[str]:
    if not table_exists(cur, table_name):
        return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table_name,))
    return {r["column_name"] for r in cur.fetchall()}

def choose(cols, *names: str):
    s = set(cols)
    for n in names:
        if n in s:
            return n
    return None

def connect_mysql(args):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )

def contains_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)

def pick_identity(row: dict, kv: dict, mode: str) -> str:
    uid = (row.get("uid") or kv.get("uid") or kv.get("nth_uid") or "").strip()
    pcid = (row.get("pcid") or kv.get("pcid") or kv.get("nth_pcid") or "").strip()
    ip = (row.get("ip") or "").strip()
    if mode == "ip":
        return f"IP:{ip}"
    if mode == "pcid_ip":
        return f"PCID:{pcid}" if pcid else f"IP:{ip}"
    return f"UID:{uid}" if uid else (f"PCID:{pcid}" if pcid else f"IP:{ip}")

def is_static_resource(path: Optional[str]) -> bool:
    return bool(STATIC_EXT_RE.search((path or "").lower()))

def is_pageview(row: dict, kv: dict, pv_mode: str) -> bool:
    method = (row.get("method") or "").upper()
    status = row.get("status") or row.get("status_code")
    path = row.get("path") or ""
    evt = (row.get("evt") or kv.get("evt") or "").strip().lower()
    if status is not None:
        try:
            if not (200 <= int(status) <= 599):
                return False
        except Exception:
            pass
    if method and method not in ("GET", "POST"):
        return False
    if method == "GET" and is_static_resource(path):
        return False
    if pv_mode == "view_only":
        return evt in ("", "view") or (row.get("event_type") or "").lower() in ("", "view")
    return True

def infer_event_name(row: dict, pv_mode: str = "view_only") -> str:
    kv = parse_kv(row.get("kv_raw"))
    existing = (row.get("semantic_event_name") or row.get("event_name") or "").strip().lower()
    if existing and existing not in GENERIC_EVENT_NAMES:
        return existing

    path = (row.get("path") or "").lower()
    url_norm = (row.get("url_norm") or "").lower()
    query = (row.get("query") or "").lower()
    method = (row.get("method") or "").upper()
    evt = (row.get("evt") or row.get("event_type") or kv.get("evt") or kv.get("event") or kv.get("action") or "").strip().lower()
    auth_result = (kv.get("auth_result") or kv.get("result") or "").strip().lower()
    product = (row.get("financial_product") or row.get("product_type") or kv.get("financial_product") or kv.get("product_type") or "").lower()
    stage = (row.get("funnel_stage") or kv.get("funnel_stage") or "").lower()
    joined = " | ".join([existing, evt, auth_result, product, stage, path, url_norm, query])

    if ("card" in joined) and contains_any(joined, ["/card/apply/submit", "/card/application/submit", "/card/complete", "card_apply_submit", "application_result=submitted", "submit", "complete"]):
        return "card_apply_submit"
    if ("card" in joined) and contains_any(joined, ["/card/apply", "/card/application/start", "card_apply_start", "start", "step1", "apply"]):
        return "card_apply_start"
    if ("loan" in joined) and contains_any(joined, ["/loan/apply/submit", "/loan/application/submit", "/loan/complete", "loan_apply_submit", "application_result=submitted", "submit", "complete"]):
        return "loan_apply_submit"
    if ("loan" in joined) and contains_any(joined, ["/loan/apply", "/loan/application/start", "loan_apply_start", "start", "step1", "apply"]):
        return "loan_apply_start"
    if ("loan" in joined) and contains_any(joined, ["/loan", "/loan/product", "/loan/detail", "loan_view", "product=loan", "view"]) and method in ("", "GET", "POST"):
        return "loan_view"

    if contains_any(joined, ["/auth/success", "/auth/complete", "/cert/success", "auth_success", "auth_result=success"]) or (("auth" in joined or "login" in joined) and contains_any(joined, ["success", "ok"])):
        return "auth_success"
    if contains_any(joined, ["/auth/fail", "/login/fail", "/cert/fail", "auth_fail", "auth_result=fail"]) or (("auth" in joined or "login" in joined) and contains_any(joined, ["fail", "error", "denied"])):
        return "auth_fail"
    if contains_any(joined, ["/otp", "/auth/otp", "/mfa", "otp_request", "otp=request", "mfa=request"]) and contains_any(joined, ["otp", "mfa", "request", "send"]):
        return "otp_request"
    if contains_any(joined, ["/risk-login", "/auth/risk", "risk_login", "risk_login=1", "fraud_flag=1"]):
        return "risk_login"
    if contains_any(joined, ["/login/success", "/auth/login/success", "/signin/success", "login_success"]):
        return "login_success"
    if contains_any(joined, ["/login", "/auth/login", "/signin", "/cert", "auth_attempt", "login_attempt", "auth_step=attempt"]):
        return "auth_attempt"
    if is_pageview(row, kv, pv_mode):
        return "page_view"
    return "other"

def safe_ratio(num: Decimal, den: Decimal) -> Decimal:
    return Decimal("0") if den == 0 else num / den
