#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import pymysql

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

def json_default(obj: Any) -> str:
    # datetime.isoformat supports sep; date.isoformat does not.
    if isinstance(obj, datetime):
        return obj.isoformat(sep=" ")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)

def normalize_json_obj(obj: Any) -> Any:
    # PyMySQL DictCursor can return Decimal/date/datetime nested in dict/list.
    if isinstance(obj, dict):
        return {str(k): normalize_json_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_json_obj(v) for v in obj]
    if isinstance(obj, tuple):
        return [normalize_json_obj(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat(sep=" ")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return obj

def to_json(obj: Any) -> str:
    return json.dumps(normalize_json_obj(obj), ensure_ascii=False, default=json_default)

def dec(v: Any) -> Decimal:
    try:
        if v is None or v == "":
            return Decimal("0")
        return Decimal(str(v))
    except Exception:
        return Decimal("0")

def q(v: Any) -> str:
    return str(Decimal(str(v)).quantize(Decimal("0.000001")))

def clamp(v: Decimal, lo: Decimal = Decimal("0"), hi: Decimal = Decimal("100")) -> Decimal:
    return max(lo, min(hi, v))

def grade(score: Decimal) -> str:
    if score < Decimal("20"):
        return "stable"
    if score < Decimal("40"):
        return "watch"
    if score < Decimal("70"):
        return "degraded"
    return "critical"

def level_from_score(score_0_100: Decimal) -> str:
    if score_0_100 < Decimal("20"):
        return "normal"
    if score_0_100 < Decimal("40"):
        return "low"
    if score_0_100 < Decimal("70"):
        return "medium"
    return "high"

def table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table_name,),
    )
    return int(cur.fetchone()["cnt"] or 0) > 0

def table_columns(cur, table_name: str) -> set[str]:
    if not table_exists(cur, table_name):
        return set()
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table_name,),
    )
    return {r["column_name"] for r in cur.fetchall()}

def first_col(cols: set[str], *names: str) -> Optional[str]:
    for n in names:
        if n in cols:
            return n
    return None

def insert_integrated_signal(cur, *,
    profile_id: str,
    dt: Any,
    layer_name: str,
    entity_scope: str,
    signal_name: str,
    signal_group: str,
    signal_level: str,
    signal_score: Any,
    metric_value: Any = None,
    source_table: str = None,
    source_ref: str = None,
    detail: dict | None = None,
):
    score = clamp(dec(signal_score), Decimal("0"), Decimal("100"))
    detail_json = to_json(detail or {})
    cur.execute(
        """
        REPLACE INTO integrated_risk_signal_day_v04
        (profile_id, dt, layer_name, entity_scope, signal_name, signal_group, signal_level,
         signal_score, metric_value, source_table, source_ref, detail_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            profile_id,
            dt,
            layer_name,
            entity_scope,
            signal_name,
            signal_group,
            signal_level,
            q(score),
            q(metric_value or 0),
            source_table,
            source_ref,
            detail_json,
        ),
    )

    # Existing compatibility table. Use 0~1 signal_score because legacy risk_layer did so.
    legacy_score = score / Decimal("100")
    cur.execute(
        """
        REPLACE INTO risk_layer_signal_day
        (dt, profile_id, processing_mode, runtime_mode, entity_scope, signal_group, signal_name,
         signal_level, signal_score, source_table, source_ref, metric_value, detail_json)
        VALUES (%s,%s,'integrated','source_derived',%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            dt,
            profile_id,
            entity_scope,
            signal_group,
            signal_name,
            signal_level,
            q(legacy_score),
            source_table,
            source_ref,
            q(metric_value or 0),
            detail_json,
        ),
    )
