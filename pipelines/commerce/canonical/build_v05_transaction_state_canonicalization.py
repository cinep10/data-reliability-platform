#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

import pymysql

RAW_TX = "v05_transaction_log_raw"
RAW_STATE = "v05_state_log_raw"
CANON_TX = "canonical_transaction_events"
CANON_STATE = "canonical_state_events"
CANON_BEHAVIOR_TABLES = ["canonical_behavior_events", "canonical_events"]
MAP_BT = "behavior_transaction_mapping"
MAP_TS = "transaction_state_mapping"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", dest="target_date")
    p.add_argument("--dt", dest="target_date")
    p.add_argument("--scenario-name", default="baseline")
    p.add_argument("--run-id", type=int, default=0)
    p.add_argument("--source-gen-run-id", type=int, default=0)
    p.add_argument("--truncate-target", action="store_true")
    a = p.parse_args()
    if not a.target_date:
        p.error("one of --target-date or --dt is required")
    return a


def connect(a):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def table_exists(cur, table):
    cur.execute("SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["cnt"]) == 1


def column_meta(cur, table):
    cur.execute(
        """
        SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, DATA_TYPE
        FROM information_schema.columns
        WHERE table_schema=DATABASE()
          AND table_name=%s
        ORDER BY ORDINAL_POSITION
        """,
        (table,),
    )
    return list(cur.fetchall())


def columns(cur, table):
    return [r["COLUMN_NAME"] for r in column_meta(cur, table)]


def json_safe(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return str(v) if not isinstance(v, (str, int, float, bool, type(None), list, dict)) else v


def dumps_safe(obj):
    return json.dumps(obj, ensure_ascii=False, default=json_safe)


def first(row, keys, default=None):
    for k in keys:
        v = row.get(k)
        if v is not None and v != "":
            return v
    return default


def delete_scope(cur, table, a):
    if not table_exists(cur, table):
        return
    cs = columns(cur, table)
    where, params = [], []
    if "profile_id" in cs:
        where.append("profile_id=%s")
        params.append(a.profile_id)
    if "target_date" in cs:
        where.append("target_date=%s")
        params.append(a.target_date)
    elif "dt" in cs:
        where.append("dt=%s")
        params.append(a.target_date)
    elif "event_date" in cs:
        where.append("event_date=%s")
        params.append(a.target_date)
    if "scenario_name" in cs:
        where.append("scenario_name=%s")
        params.append(a.scenario_name)
    elif "scenario_id" in cs:
        where.append("scenario_id=%s")
        params.append(a.scenario_name)
    if where:
        cur.execute(f"DELETE FROM {table} WHERE " + " AND ".join(where), tuple(params))


def read_scope(cur, table, a, limit=None):
    if not table_exists(cur, table):
        return []
    cs = columns(cur, table)
    where, params = [], []
    if "profile_id" in cs:
        where.append("profile_id=%s")
        params.append(a.profile_id)
    if "target_date" in cs:
        where.append("target_date=%s")
        params.append(a.target_date)
    elif "dt" in cs:
        where.append("dt=%s")
        params.append(a.target_date)
    elif "event_date" in cs:
        where.append("event_date=%s")
        params.append(a.target_date)
    if "scenario_name" in cs:
        where.append("scenario_name=%s")
        params.append(a.scenario_name)
    elif "scenario_id" in cs:
        where.append("scenario_id=%s")
        params.append(a.scenario_name)
    sql = f"SELECT * FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql, tuple(params))
    return list(cur.fetchall())


def normalize_event(row, a, idx, kind):
    rid = first(row, ["transaction_id", "order_id", "payment_id", "state_id", "event_id"]) or f"{kind}-{a.profile_id}-{a.target_date}-{a.scenario_name}-{idx}"
    tx_id = first(row, ["transaction_id", "order_id", "payment_id"], rid)
    state_id = first(row, ["state_id", "transaction_state_id"], rid)
    event_time = first(row, ["event_time", "transaction_time", "state_time", "timestamp", "created_at", "log_time"], f"{a.target_date} 00:00:00")
    evt = first(row, ["transaction_event", "state_event", "event_name", "event_type", "transaction_type", "state_transition", "status_event"], kind)
    status = first(row, ["status", "state", "transaction_status", "order_status", "result"], "unknown")
    amount = first(row, ["amount", "order_amount", "payment_amount", "price", "value"], 0)
    user_id = first(row, ["user_id", "uid", "customer_id", "member_id"], "")
    session_id = first(row, ["session_id", "sid"], "")
    visitor_id = first(row, ["visitor_id", "pcid"], "")
    raw_json = first(row, ["raw_json"], None) or dumps_safe(row)
    return {
        "profile_id": a.profile_id, "target_date": a.target_date, "dt": a.target_date, "event_date": a.target_date,
        "run_id": a.run_id, "source_gen_run_id": a.source_gen_run_id, "scenario_name": a.scenario_name, "scenario_id": a.scenario_name,
        "event_id": rid, "transaction_event_id": rid, "state_event_id": rid,
        "transaction_id": tx_id, "order_id": tx_id, "payment_id": tx_id, "state_id": state_id,
        "event_time": event_time, "transaction_time": event_time, "state_time": event_time, "created_time": event_time,
        "event_name": evt, "event_type": evt, "transaction_event": evt, "state_event": evt, "transaction_type": evt, "state_transition": evt,
        "status": status, "transaction_status": status, "state_status": status, "order_status": status, "result": status,
        "amount": amount, "order_amount": amount, "payment_amount": amount,
        "user_id": user_id, "uid": user_id, "customer_id": user_id, "session_id": session_id, "sid": session_id, "visitor_id": visitor_id, "pcid": visitor_id,
        "source_table": RAW_TX if kind == "transaction" else RAW_STATE, "source_type": kind, "record_type": kind, "raw_json": raw_json,
    }


def fallback_value(col, data_type, row, a, kind):
    if col in row:
        return row[col]
    if col == "profile_id":
        return a.profile_id
    if col in ("target_date", "dt", "event_date"):
        return a.target_date
    if col in ("scenario_name", "scenario_id"):
        return a.scenario_name
    if col == "run_id":
        return a.run_id
    if col == "source_gen_run_id":
        return a.source_gen_run_id
    if col.endswith("_id") or col in ("id", "event_key"):
        return row.get("event_id") or f"{kind}-{a.profile_id}-{a.target_date}-{a.scenario_name}"
    if col.endswith("_event") or col in ("event_name", "event_type", "transaction_event", "state_event"):
        return row.get("event_name") or kind
    if col.endswith("_status") or col in ("status", "result", "match_status", "mapping_status"):
        return row.get("status") or "matched"
    if col.endswith("_time") or col in ("event_time", "created_time", "timestamp"):
        return row.get("event_time") or f"{a.target_date} 00:00:00"
    if col.endswith("_amount") or col in ("amount", "value", "price"):
        return row.get("amount") or 0
    if col in ("raw_json", "payload_json", "source_json"):
        return row.get("raw_json") or dumps_safe(row)
    if col in ("created_at", "updated_at", "ingested_at", "loaded_at", "mapped_at"):
        return "__NOW__"
    if data_type in ("int", "bigint", "smallint", "tinyint", "mediumint", "decimal", "float", "double"):
        return 0
    if data_type == "date":
        return a.target_date
    if data_type in ("datetime", "timestamp"):
        return "__NOW__"
    if data_type == "json":
        return row.get("raw_json") or dumps_safe(row)
    return ""


def insert_rows(cur, table, rows, a, kind):
    if not rows or not table_exists(cur, table):
        return 0
    meta = column_meta(cur, table)
    normalized = [normalize_event(r, a, i, kind) for i, r in enumerate(rows, 1)]
    return insert_normalized(cur, table, normalized, meta, a, kind)


def insert_normalized(cur, table, normalized, meta, a, kind):
    if not normalized:
        return 0
    insert_cols = []
    for m in meta:
        c = m["COLUMN_NAME"]
        extra = (m.get("EXTRA") or "").lower()
        if "auto_increment" in extra:
            continue
        if any(c in row for row in normalized):
            insert_cols.append(c)
        elif m["IS_NULLABLE"] == "NO" and m["COLUMN_DEFAULT"] is None:
            insert_cols.append(c)
    if not insert_cols:
        return 0
    dtype = {m["COLUMN_NAME"]: m["DATA_TYPE"] for m in meta}
    placeholders, values = [], []
    for row in normalized:
        ph = []
        for c in insert_cols:
            v = row.get(c)
            if v is None:
                v = fallback_value(c, dtype.get(c, "varchar"), row, a, kind)
            if v == "__NOW__":
                ph.append("NOW()")
            else:
                ph.append("%s")
                values.append(v)
        placeholders.append("(" + ",".join(ph) + ")")
    cur.execute(
        f"INSERT INTO {table} (" + ",".join(f"`{c}`" for c in insert_cols) + ") VALUES " + ",".join(placeholders),
        tuple(values),
    )
    return len(normalized)


def read_behavior_rows(cur, a, limit):
    for t in CANON_BEHAVIOR_TABLES:
        rows = read_scope(cur, t, a, limit=limit)
        if rows:
            return rows
    return []


def build_behavior_transaction_mapping_rows(behavior_rows, tx_rows, a):
    rows = []
    n = min(len(behavior_rows), len(tx_rows))
    for i in range(n):
        b = behavior_rows[i]
        tx = tx_rows[i]
        b_id = first(b, ["event_id", "behavior_event_id"], f"behavior-{i+1}")
        tx_id = first(tx, ["transaction_id", "order_id", "payment_id", "event_id"], f"transaction-{i+1}")
        rows.append({
            "profile_id": a.profile_id, "target_date": a.target_date, "dt": a.target_date, "event_date": a.target_date,
            "run_id": a.run_id, "source_gen_run_id": a.source_gen_run_id, "scenario_name": a.scenario_name, "scenario_id": a.scenario_name,
            "behavior_event_id": b_id, "event_id": b_id, "transaction_id": tx_id, "order_id": tx_id,
            "mapping_key": f"{b_id}:{tx_id}", "match_status": "matched", "mapping_status": "matched",
            "match_score": 1.0, "raw_json": dumps_safe({"behavior_event_id": b_id, "transaction_id": tx_id}),
        })
    return rows


def build_transaction_state_mapping_rows(tx_rows, state_rows, a):
    rows = []
    n = min(len(tx_rows), len(state_rows))
    for i in range(n):
        tx = tx_rows[i]
        st = state_rows[i]
        tx_id = first(tx, ["transaction_id", "order_id", "payment_id", "event_id"], f"transaction-{i+1}")
        st_id = first(st, ["state_id", "event_id"], f"state-{i+1}")
        rows.append({
            "profile_id": a.profile_id, "target_date": a.target_date, "dt": a.target_date, "event_date": a.target_date,
            "run_id": a.run_id, "source_gen_run_id": a.source_gen_run_id, "scenario_name": a.scenario_name, "scenario_id": a.scenario_name,
            "transaction_id": tx_id, "order_id": tx_id, "state_id": st_id,
            "mapping_key": f"{tx_id}:{st_id}", "match_status": "matched", "mapping_status": "matched",
            "match_score": 1.0, "raw_json": dumps_safe({"transaction_id": tx_id, "state_id": st_id}),
        })
    return rows


def insert_mapping(cur, table, rows, a, kind):
    if not rows or not table_exists(cur, table):
        return 0
    meta = column_meta(cur, table)
    return insert_normalized(cur, table, rows, meta, a, kind)


def main():
    a = parse_args()
    con = connect(a)
    try:
        with con.cursor() as cur:
            tx_rows = read_scope(cur, RAW_TX, a)
            state_rows = read_scope(cur, RAW_STATE, a)

            if a.truncate_target:
                for t in [CANON_TX, CANON_STATE, MAP_BT, MAP_TS]:
                    delete_scope(cur, t, a)

            tx_n = insert_rows(cur, CANON_TX, tx_rows, a, "transaction")
            state_n = insert_rows(cur, CANON_STATE, state_rows, a, "state")

            behavior_rows = read_behavior_rows(cur, a, limit=max(len(tx_rows), 1))
            bt_rows = build_behavior_transaction_mapping_rows(behavior_rows, tx_rows, a)
            ts_rows = build_transaction_state_mapping_rows(tx_rows, state_rows, a)
            bt_n = insert_mapping(cur, MAP_BT, bt_rows, a, "behavior_transaction_mapping")
            ts_n = insert_mapping(cur, MAP_TS, ts_rows, a, "transaction_state_mapping")

        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    print(
        "[OK] build_v05_transaction_state_canonicalization "
        f"tx_raw={len(tx_rows)} state_raw={len(state_rows)} canonical_tx={tx_n} canonical_state={state_n} "
        f"behavior_transaction_mapping={bt_n} transaction_state_mapping={ts_n}"
    )


if __name__ == "__main__":
    main()
