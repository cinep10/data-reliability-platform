#!/usr/bin/env python3
"""
v0.5 source anomaly trace materializer.

Purpose:
- Persist source-level anomaly trace JSON into v05_source_anomaly_trace_day.
- Never mutates stage/canonical/measurement runtime tables.
- Schema-aware insert: only inserts columns that exist in current MariaDB table.
- Always supplies trace_id and anomaly_seq when those columns exist.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List

import pymysql


TABLE = "v05_source_anomaly_trace_day"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--input-dir", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    return p.parse_args()


def connect(args: argparse.Namespace):
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


def table_columns(cur) -> List[str]:
    cur.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = %s
        ORDER BY ORDINAL_POSITION
        """,
        (TABLE,),
    )
    return [r["COLUMN_NAME"] for r in cur.fetchall()]


def find_trace_file(input_dir: str, profile_id: str, target_date: str, scenario_name: str) -> str:
    exact = os.path.join(
        input_dir,
        f"{profile_id}_{target_date}_{scenario_name}_source_anomaly_trace.json",
    )
    if os.path.exists(exact):
        return exact

    candidates = sorted(glob.glob(os.path.join(input_dir, "*source_anomaly_trace.json")))
    if candidates:
        return candidates[-1]

    raise FileNotFoundError(f"source anomaly trace json not found under: {input_dir}")


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def as_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


def as_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def first_present(d: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def normalize_trace_rows(payload: Any, args: argparse.Namespace, trace_file: str) -> List[Dict[str, Any]]:
    """
    Accepts several trace JSON shapes:
    - dict summary
    - dict with rows/items/events/anomalies list
    - list of dict rows
    Produces row dicts safe for table insert.
    """
    if isinstance(payload, list):
        raw_rows = payload
        summary = {}
    elif isinstance(payload, dict):
        summary = payload
        raw_rows = first_present(payload, ["rows", "items", "events", "anomalies", "trace_rows"], None)
        if not isinstance(raw_rows, list):
            raw_rows = [payload]
    else:
        summary = {}
        raw_rows = [{"trace_json": payload}]

    trace_id = first_present(
        summary if isinstance(summary, dict) else {},
        ["trace_id", "execution_trace_id"],
        f"{args.profile_id}-{args.target_date}-{args.run_id}-{args.source_gen_run_id}-{args.scenario_name}",
    )

    total_count = as_int(first_present(summary, ["total_count", "final_count", "rows_after", "affected_total"], 0))
    original_count = as_int(first_present(summary, ["original_count", "rows_before", "before_count"], 0))
    final_count = as_int(first_present(summary, ["final_count", "rows_after", "after_count"], total_count or original_count))

    batch_marker_count = as_int(first_present(summary, ["batch_marker_count", "batch_anomaly_count"], 0))
    stream_marker_count = as_int(first_present(summary, ["stream_marker_count", "stream_anomaly_count"], 0))
    operational_marker_count = as_int(first_present(summary, ["operational_marker_count", "operational_anomaly_count"], 0))

    # If trace JSON only has mode, infer marker counts conservatively.
    mode = str(first_present(summary, ["anomaly_mode", "mode", "scenario_name"], args.scenario_name) or args.scenario_name)
    affected = as_int(first_present(summary, ["affected_count", "affected_rows", "mutated_count"], 0))
    if batch_marker_count == 0 and "batch" in mode:
        batch_marker_count = affected
    if stream_marker_count == 0 and "stream" in mode:
        stream_marker_count = affected
    if operational_marker_count == 0 and "operational" in mode:
        operational_marker_count = affected

    rows: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_rows, start=1):
        if not isinstance(raw, dict):
            raw = {"trace_json": raw}

        runtime_layer = first_present(raw, ["runtime_layer", "layer", "source_layer"], None)
        if runtime_layer is None:
            if "operational" in mode:
                runtime_layer = "batch_stream_operational"
            elif "stream" in mode:
                runtime_layer = "batch_stream"
            elif "batch" in mode:
                runtime_layer = "batch"
            else:
                runtime_layer = "source"

        anomaly_type = first_present(raw, ["anomaly_type", "type", "signal"], None)
        if anomaly_type is None:
            anomaly_type = mode

        affected_count = as_int(first_present(raw, ["affected_count", "affected_rows", "count"], affected))
        row_total = as_int(first_present(raw, ["total_count", "total", "rows_after"], total_count or final_count))
        affected_ratio = as_float(first_present(raw, ["affected_ratio", "ratio"], 0.0))
        if affected_ratio == 0.0 and row_total > 0 and affected_count > 0:
            affected_ratio = affected_count / row_total

        evidence_key = first_present(raw, ["evidence_key", "key"], str(anomaly_type))
        evidence_value = first_present(raw, ["evidence_value", "value"], None)
        if evidence_value is None:
            evidence_value = json.dumps(raw, ensure_ascii=False)[:512]

        row_trace_json = raw.get("trace_json", None)
        if row_trace_json is None:
            row_trace_json = json.dumps(raw, ensure_ascii=False)

        row = {
            "profile_id": args.profile_id,
            "target_date": args.target_date,
            "dt": args.target_date,
            "run_id": args.run_id,
            "source_gen_run_id": args.source_gen_run_id,
            "scenario_name": args.scenario_name,
            "anomaly_mode": mode,
            "runtime_layer": runtime_layer,
            "source_layer": first_present(raw, ["source_layer"], "behavior_source_log"),
            "anomaly_type": anomaly_type,
            "affected_count": affected_count,
            "total_count": row_total,
            "affected_ratio": affected_ratio,
            "evidence_key": evidence_key,
            "evidence_value": str(evidence_value)[:512],
            "trace_file": os.path.basename(trace_file),
            "trace_json": row_trace_json,
            "behavior_log_path": first_present(summary, ["behavior_log_path", "behavior_w3c_log"], None),
            "original_count": original_count,
            "final_count": final_count,
            "batch_marker_count": as_int(first_present(raw, ["batch_marker_count", "batch_anomaly_count"], batch_marker_count)),
            "stream_marker_count": as_int(first_present(raw, ["stream_marker_count", "stream_anomaly_count"], stream_marker_count)),
            "operational_marker_count": as_int(first_present(raw, ["operational_marker_count", "operational_anomaly_count"], operational_marker_count)),
            "shifted_hour_count": as_int(first_present(raw, ["shifted_hour_count"], first_present(summary, ["shifted_hour_count"], 0))),
            "promo_shadow_count": as_int(first_present(raw, ["promo_shadow_count"], first_present(summary, ["promo_shadow_count"], 0))),
            "duplicated_count": as_int(first_present(raw, ["duplicated_count", "duplicate_count"], first_present(summary, ["duplicated_count", "duplicate_count"], 0))),
            "dropped_count": as_int(first_present(raw, ["dropped_count"], first_present(summary, ["dropped_count"], 0))),
            "reordered_count": as_int(first_present(raw, ["reordered_count"], first_present(summary, ["reordered_count"], 0))),
            "stream_delay_marker_count": as_int(first_present(raw, ["stream_delay_marker_count"], first_present(summary, ["stream_delay_marker_count"], 0))),
            "operational_5xx_count": as_int(first_present(raw, ["operational_5xx_count"], first_present(summary, ["operational_5xx_count"], 0))),
            "operational_timeout_marker_count": as_int(first_present(raw, ["operational_timeout_marker_count"], first_present(summary, ["operational_timeout_marker_count"], 0))),
            "anomaly_trace_json": json.dumps(payload, ensure_ascii=False)[:65535],
            "trace_id": str(trace_id),
            "anomaly_seq": idx,
            "affected_rows": affected_count,
            "evidence_count": affected_count,
            "anomaly_score": affected_ratio,
        }
        rows.append(row)

    return rows


def delete_existing(cur, cols: List[str], args: argparse.Namespace) -> None:
    where = []
    params = []
    if "profile_id" in cols:
        where.append("profile_id=%s")
        params.append(args.profile_id)
    if "target_date" in cols:
        where.append("target_date=%s")
        params.append(args.target_date)
    elif "dt" in cols:
        where.append("dt=%s")
        params.append(args.target_date)
    if "run_id" in cols:
        where.append("run_id=%s")
        params.append(args.run_id)
    if "source_gen_run_id" in cols:
        where.append("source_gen_run_id=%s")
        params.append(args.source_gen_run_id)
    if "scenario_name" in cols:
        where.append("scenario_name=%s")
        params.append(args.scenario_name)

    if where:
        cur.execute(f"DELETE FROM {TABLE} WHERE " + " AND ".join(where), tuple(params))


def insert_rows(cur, cols: List[str], rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0

    preferred = [
        "profile_id", "target_date", "dt", "run_id", "source_gen_run_id", "scenario_name",
        "anomaly_mode", "runtime_layer", "source_layer", "anomaly_type",
        "affected_count", "total_count", "affected_ratio",
        "evidence_key", "evidence_value", "trace_file", "trace_json", "behavior_log_path",
        "original_count", "final_count",
        "batch_marker_count", "stream_marker_count", "operational_marker_count",
        "shifted_hour_count", "promo_shadow_count", "duplicated_count", "dropped_count",
        "reordered_count", "stream_delay_marker_count", "operational_5xx_count",
        "operational_timeout_marker_count", "anomaly_trace_json",
        "trace_id", "anomaly_seq", "affected_rows", "evidence_count", "anomaly_score",
        "created_at",
    ]

    insert_cols = [c for c in preferred if c in cols and c != "created_at"]
    if "created_at" in cols:
        insert_cols.append("created_at")

    placeholders = []
    values = []
    for row in rows:
        ph = []
        vals = []
        for c in insert_cols:
            if c == "created_at":
                ph.append("NOW()")
            else:
                ph.append("%s")
                vals.append(row.get(c))
        placeholders.append("(" + ",".join(ph) + ")")
        values.extend(vals)

    sql = (
        f"INSERT INTO {TABLE} ("
        + ",".join(f"`{c}`" for c in insert_cols)
        + ") VALUES "
        + ",".join(placeholders)
    )
    cur.execute(sql, tuple(values))
    return len(rows)


def main() -> None:
    args = parse_args()
    trace_file = find_trace_file(args.input_dir, args.profile_id, args.target_date, args.scenario_name)
    payload = load_json(trace_file)
    rows = normalize_trace_rows(payload, args, trace_file)

    conn = connect(args)
    try:
        with conn.cursor() as cur:
            cols = table_columns(cur)
            if not cols:
                raise RuntimeError(f"{TABLE} not found or has no columns")
            delete_existing(cur, cols, args)
            n = insert_rows(cur, cols, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(
        "[OK] build_v05_source_anomaly_trace_day "
        f"profile_id={args.profile_id} dt={args.target_date} run_id={args.run_id} "
        f"source_gen_run_id={args.source_gen_run_id} scenario={args.scenario_name} "
        f"trace_file={os.path.basename(trace_file)} rows={len(rows)}"
    )


if __name__ == "__main__":
    main()
