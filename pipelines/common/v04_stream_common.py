#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

GENERIC_EVENT_NAMES = {"", "view", "click", "conversion", "submit", "success", "browse", "page", "other", "unknown"}
KV_RE = re.compile(r'(?:^|;\s*)([A-Za-z0-9_\-]+)=([^;]*)', re.I)

def json_default(obj: Any) -> str:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat(sep=" ")
    return str(obj)

def parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value

def parse_kv(kv_raw: Optional[str]) -> dict[str, str]:
    if not kv_raw:
        return {}
    return {m.group(1).lower(): m.group(2).strip() for m in KV_RE.finditer(str(kv_raw).strip())}

def first_present(row: dict[str, Any], names: list[str], default: Any = None) -> Any:
    for n in names:
        if n in row and row.get(n) is not None:
            return row.get(n)
    return default

def to_iso(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    return value

def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default

def d(v: Any) -> Decimal:
    try:
        return Decimal(str(v if v is not None else 0))
    except Exception:
        return Decimal("0")

def q(v: Any) -> str:
    return str(Decimal(str(v)).quantize(Decimal("0.000001")))

def clamp01(v: float) -> float:
    return 0.0 if v < 0 else (1.0 if v > 1 else v)

def contains_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)

def infer_event_name(row: dict[str, Any]) -> str:
    kv = parse_kv(row.get("kv_raw"))
    existing = (row.get("semantic_event_name") or row.get("event_name") or row.get("event_type") or "").strip().lower()
    if existing and existing not in GENERIC_EVENT_NAMES:
        return existing

    path = (row.get("path") or "").lower()
    query = (row.get("query") or "").lower()
    url_norm = (row.get("url_norm") or "").lower()
    evt = (row.get("evt") or kv.get("evt") or kv.get("event") or kv.get("action") or "").strip().lower()
    product = (row.get("financial_product") or row.get("product_type") or kv.get("financial_product") or kv.get("product_type") or "").lower()
    stage = (row.get("funnel_stage") or kv.get("funnel_stage") or "").lower()
    auth_result = (kv.get("auth_result") or kv.get("result") or "").lower()
    joined = " | ".join([existing, evt, auth_result, product, stage, path, url_norm, query])

    if "card" in joined and contains_any(joined, ["/card/apply/submit", "/card/complete", "card_apply_submit", "submit", "complete"]):
        return "card_apply_submit"
    if "card" in joined and contains_any(joined, ["/card/apply", "card_apply_start", "start", "step1", "apply"]):
        return "card_apply_start"
    if "loan" in joined and contains_any(joined, ["/loan/apply/submit", "/loan/complete", "loan_apply_submit", "submit", "complete"]):
        return "loan_apply_submit"
    if "loan" in joined and contains_any(joined, ["/loan/apply", "loan_apply_start", "start", "step1", "apply"]):
        return "loan_apply_start"
    if "loan" in joined and contains_any(joined, ["/loan", "/loan/product", "/loan/detail", "loan_view", "view"]):
        return "loan_view"
    if contains_any(joined, ["/auth/success", "auth_success", "auth_result=success"]) or (("auth" in joined or "login" in joined) and contains_any(joined, ["success", "ok"])):
        return "auth_success"
    if contains_any(joined, ["/auth/fail", "auth_fail", "auth_result=fail"]) or (("auth" in joined or "login" in joined) and contains_any(joined, ["fail", "error", "denied"])):
        return "auth_fail"
    if contains_any(joined, ["/otp", "/mfa", "otp_request", "mfa=request"]):
        return "otp_request"
    if contains_any(joined, ["/risk-login", "/auth/risk", "risk_login", "fraud_flag=1"]):
        return "risk_login"
    if contains_any(joined, ["/login/success", "login_success"]):
        return "login_success"
    if contains_any(joined, ["/login", "/auth/login", "/signin", "/cert", "auth_attempt", "login_attempt"]):
        return "auth_attempt"
    return "page_view" if existing in GENERIC_EVENT_NAMES else (existing or "unknown")

def severity_rank(sev: Optional[str]) -> int:
    return {"high": 4, "medium": 3, "low": 2, "info": 1, None: 0, "": 0}.get(sev, 0)
