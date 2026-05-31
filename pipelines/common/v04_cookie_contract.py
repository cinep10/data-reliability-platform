#!/usr/bin/env python3
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

APACHE_COMBINED_WITH_KV = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ '
    r'\[(?P<ts>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+) (?P<protocol>[^"]+)" '
    r'(?P<status>\d{3}) (?P<bytes>\d+|-)\s+'
    r'"(?P<ref>[^"]*)"\s+'
    r'"(?P<ua>[^"]*)"\s+'
    r'"(?P<kv_raw>[^"]*)"\s*$'
)

SPECIAL_KEYS_PRESERVE_COMMAS = {"al", "accept_lang"}

# Cookie key list. Keep cookie run_id as raw key, but DB columns should use run_id_cookie.
CONTRACT_KEYS = [
    "schema_version","scenario_id","scenario_name","domain","source_layer","anomaly_type","drift","affected",
    "exo_state_id","anomaly_contract_id","experiment_id","run_id","exo_source","weather_type","campaign_flag",
    "system_flag","volume_multiplier","conversion_multiplier","latency_shift_ms","drop_probability",
    "timeout_multiplier","retry_multiplier","duplicate_multiplier","event_time_skew_ms","suppress_input",
    "schema_flag","identity_flag","pcid_stability","session_stability","customer_id_stability","traffic_actor",
    "bot_flag","user_agent_flag","ip_concentration_flag","recovery_flag","backlog_flush","transaction_delay_ms",
    "event_ingestion_delay_ms","privacy_flag","pii_detected","sensitive_field_flag","masking_status",
    "financial_product","state_transition","expected_state","actual_state","amount_expected","amount_actual",
    "amount_delta","approval_result","execution_result","account_status","ledger_status","balance_delta",
    "reconciliation_flag",
]

# DB-safe contract columns: run_id cookie is stored as run_id_cookie to avoid conflict with pipeline run_id.
CONTRACT_DB_COLS = ["run_id_cookie" if k == "run_id" else k for k in CONTRACT_KEYS]

NUMERIC_KEYS = {
    "affected","volume_multiplier","conversion_multiplier","latency_shift_ms","drop_probability",
    "timeout_multiplier","retry_multiplier","duplicate_multiplier","event_time_skew_ms","suppress_input",
    "bot_flag","backlog_flush","transaction_delay_ms","event_ingestion_delay_ms","pii_detected",
    "amount_expected","amount_actual","amount_delta","balance_delta",
}

def parse_kv_tail(kv_raw: Optional[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not kv_raw:
        return out
    for part in str(kv_raw).split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out

def extract_kv(kv_raw: Optional[str], key: str) -> Optional[str]:
    if not kv_raw:
        return None
    kv = parse_kv_tail(kv_raw)
    if key in kv:
        return kv[key] or None
    text = str(kv_raw)
    delimiters = [";", "&", "|"]
    if key not in SPECIAL_KEYS_PRESERVE_COMMAS:
        delimiters.append(",")
    for delim in delimiters:
        if delim in text:
            for part in text.split(delim):
                part = part.strip()
                if part.startswith(f"{key}="):
                    val = part.split("=", 1)[1].strip()
                    return val or None
    return None

def safe_int(v: Any) -> Optional[int]:
    if v in (None, "", "-"):
        return None
    try:
        return int(float(v))
    except Exception:
        return None

def safe_float(v: Any) -> Optional[float]:
    if v in (None, "", "-"):
        return None
    try:
        return float(v)
    except Exception:
        return None

def normalize_contract_value(key_or_col: str, val: Any) -> Any:
    key = "run_id" if key_or_col == "run_id_cookie" else key_or_col
    if key in NUMERIC_KEYS:
        if key.endswith("_multiplier") or key == "drop_probability":
            return safe_float(val)
        return safe_int(val)
    return val

def split_path_query(raw_path: str) -> tuple[Optional[str], Optional[str]]:
    if not raw_path:
        return None, None
    if "?" in raw_path:
        p, q = raw_path.split("?", 1)
        return p, q
    return raw_path, None

def parse_apache_ts(raw_ts: str) -> datetime:
    return datetime.strptime(raw_ts, "%d/%b/%Y:%H:%M:%S %z")

def extract_ref_host(ref: Optional[str]) -> Optional[str]:
    if not ref or ref == "-":
        return None
    try:
        return urlparse(ref).netloc or None
    except Exception:
        return None

def infer_device_type(ua: Optional[str], kv_device: Optional[str] = None) -> Optional[str]:
    if kv_device:
        return kv_device
    x = (ua or "").lower()
    if not x:
        return None
    if "ipad" in x or "tablet" in x:
        return "tablet"
    if "iphone" in x or "android" in x or "mobile" in x:
        return "mobile"
    return "desktop"

def infer_service_domain(path: Optional[str], kv_domain: Optional[str] = None) -> str:
    if kv_domain:
        return kv_domain
    p = (path or "").lower()
    for name in ("loan", "card", "deposit", "transfer", "auth", "account", "customer", "branch"):
        if f"/{name}/" in p:
            return name
    return "web"

def infer_event_type(path: Optional[str], evt: Optional[str], event_type: Optional[str]) -> str:
    if event_type:
        return event_type
    if evt:
        return evt
    p = (path or "").lower()
    if "/submit" in p:
        return "conversion"
    if "/apply" in p or "/step" in p:
        return "click"
    return "view"

def infer_page_type(path: Optional[str], page_type: Optional[str]) -> Optional[str]:
    if page_type:
        return page_type
    p = (path or "").lower()
    for name in ("loan", "card", "deposit", "transfer"):
        if f"/{name}/" in p:
            return name
    if "/auth/" in p or "/login" in p:
        return "login"
    if "/account/" in p:
        return "account"
    if "/dashboard" in p:
        return "dashboard"
    if "/main" in p:
        return "home"
    return "page" if p else None

def infer_funnel_stage(path: Optional[str], page_type: Optional[str], kv_stage: Optional[str]) -> str:
    if kv_stage:
        return kv_stage
    if page_type:
        return page_type
    p = (path or "").lower()
    if "/submit" in p:
        return "submit"
    if "/apply" in p:
        return "apply"
    if "/product" in p:
        return "product"
    if "/status" in p:
        return "status"
    return "browse"

def infer_is_conversion(path: Optional[str], evt: Optional[str], event_type: Optional[str]) -> int:
    e = (event_type or evt or "").lower()
    p = (path or "").lower()
    return 1 if e in ("conversion", "submit", "success") or "/submit" in p or "/complete" in p or "/success" in p else 0

def parse_apache_line(line: str) -> dict[str, Any]:
    m = APACHE_COMBINED_WITH_KV.match(line.strip())
    if not m:
        raise ValueError(f"unrecognized apache combined + kv line: {line[:300]}")
    gd = m.groupdict()
    ts = parse_apache_ts(gd["ts"])
    raw_path = gd.get("path")
    path, query = split_path_query(raw_path or "")
    kv_raw = gd.get("kv_raw") or ""
    kv = parse_kv_tail(kv_raw)
    event_type = infer_event_type(path, kv.get("evt"), kv.get("event_type"))
    page_type = infer_page_type(path, kv.get("page_type"))
    funnel_stage = infer_funnel_stage(path, page_type, kv.get("funnel_stage"))
    service_domain = infer_service_domain(path, kv.get("domain"))
    row = {
        "dt": ts.date().isoformat(),
        "ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "ip": gd.get("ip"),
        "method": gd.get("method"),
        "protocol": gd.get("protocol"),
        "url_raw": raw_path,
        "url_full": raw_path,
        "url_norm": path,
        "host": None,
        "path": path,
        "query": query,
        "status": safe_int(gd.get("status")),
        "bytes": safe_int(gd.get("bytes")),
        "latency_ms": safe_int(kv.get("latency_ms")),
        "ref": None if gd.get("ref") == "-" else gd.get("ref"),
        "ref_host": extract_ref_host(gd.get("ref")),
        "ua": gd.get("ua"),
        "kv_raw": kv_raw,
        "uid": kv.get("uid"),
        "pcid": kv.get("pcid"),
        "sid": kv.get("sid"),
        "device_type": infer_device_type(gd.get("ua"), kv.get("device")),
        "evt": kv.get("evt"),
        "event_type": event_type,
        "page_type": page_type,
        "product_type": kv.get("product_type"),
        "service_domain": service_domain,
        "funnel_stage": funnel_stage,
        "is_conversion": infer_is_conversion(path, kv.get("evt"), kv.get("event_type")),
        "accept_lang": kv.get("al") or kv.get("accept_lang"),
        "cc": kv.get("cc"),
    }
    for key in CONTRACT_KEYS:
        db_col = "run_id_cookie" if key == "run_id" else key
        row[db_col] = normalize_contract_value(db_col, kv.get(key))
    return row

def table_columns(cur, table_name: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table_name,),
    )
    return {r["column_name"] for r in cur.fetchall()}

def filter_existing_columns(cur, table_name: str, requested: list[str]) -> list[str]:
    existing = table_columns(cur, table_name)
    return [c for c in requested if c in existing]

def first_existing_column(cur, table_name: str, requested: list[str]) -> Optional[str]:
    existing = table_columns(cur, table_name)
    for c in requested:
        if c in existing:
            return c
    return None


def dict_subset(row: dict, keys: list[str]) -> dict:
    return {k: row.get(k) for k in keys}
