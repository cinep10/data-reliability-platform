#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

import pymysql

TABLES = [
    "source_file_manifest",
    "batch_input_day",
    "source_generation_run",
    "v05_commerce_source_generation_run",
]


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
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--run-id", type=int, default=0)
    p.add_argument("--source-dir", required=True)
    p.add_argument("--source-gen-run-id", type=int, default=0)
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
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
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


def json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    return str(o)


def safe_json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=json_default)


def line_count(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def source_type_for_name(name: str) -> str:
    if name.endswith("_behavior.w3c.log"):
        return "behavior_w3c"
    if name.endswith("_transaction.jsonl"):
        return "transaction_jsonl"
    if name.endswith("_state.jsonl"):
        return "state_jsonl"
    if name.endswith("_journey.jsonl"):
        return "journey_jsonl"
    if name.endswith("_source_anomaly_trace.json"):
        return "source_anomaly_trace"
    if name.endswith(".json"):
        return "summary_json"
    return "source_file"


def discover_files(a) -> List[Dict[str, Any]]:
    paths = sorted(glob.glob(os.path.join(a.source_dir, "*")))
    rows = []

    for path in paths:
        if not os.path.isfile(path):
            continue

        name = os.path.basename(path)
        stype = source_type_for_name(name)
        cnt = line_count(path)
        size = os.path.getsize(path)

        domain = stype or "source_file"

        rows.append(
            {
                "profile_id": a.profile_id,
                "target_date": a.target_date,
                "dt": a.target_date,
                "event_date": a.target_date,
                "run_id": a.run_id,
                "source_gen_run_id": a.source_gen_run_id or a.run_id,
                "scenario_name": a.scenario_name,
                "scenario_id": a.scenario_name,
                "domain": domain,
                "source_domain": domain,
                "source_layer": "source",
                "source_dir": a.source_dir,
                "input_dir": a.source_dir,
                "source_file_path": path,
                "file_path": path,
                "raw_file_path": path,
                "source_file_name": name,
                "file_name": name,
                "raw_file_name": name,
                "source_type": stype,
                "record_type": stype,
                "record_count": cnt,
                "row_count": cnt,
                "line_count": cnt,
                "file_size_bytes": size,
                "status": "REGISTERED",
                "load_status": "REGISTERED",
                "generation_status": "GENERATED",
                "manifest_json": safe_json(
                    {
                        "profile_id": a.profile_id,
                        "target_date": a.target_date,
                        "scenario_name": a.scenario_name,
                        "source_file_path": path,
                        "source_type": stype,
                        "record_count": cnt,
                        "file_size_bytes": size,
                    }
                ),
            }
        )
    return rows


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

    # Do not require source_gen_run_id for cleanup because old duplicate rows may have 0 or stale values.
    if where:
        cur.execute(f"DELETE FROM {table} WHERE " + " AND ".join(where), tuple(params))


def fallback_value(col, data_type, row, a):
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
        return a.source_gen_run_id or a.run_id
    if col in ("domain", "source_domain"):
        return row.get("domain") or row.get("source_type") or "source_file"
    if col in ("source_layer",):
        return "source"
    if col in ("source_file_path", "file_path", "raw_file_path"):
        return row.get("source_file_path") or a.source_dir
    if col in ("source_file_name", "file_name", "raw_file_name"):
        return row.get("source_file_name") or os.path.basename(a.source_dir.rstrip("/"))
    if col in ("source_dir", "input_dir"):
        return a.source_dir
    if col in ("status", "load_status", "generation_status"):
        return "REGISTERED"
    if col in ("created_at", "updated_at", "registered_at", "loaded_at"):
        return "__NOW__"
    if col.endswith("_json") or data_type == "json":
        return row.get("manifest_json") or safe_json(row)
    if data_type in ("int", "bigint", "smallint", "tinyint", "mediumint"):
        return 0
    if data_type in ("decimal", "float", "double"):
        return 0
    if data_type == "date":
        return a.target_date
    if data_type in ("datetime", "timestamp"):
        return "__NOW__"
    return ""


def build_insert_sql(table, insert_cols, update_cols):
    col_sql = ",".join(f"`{c}`" for c in insert_cols)
    placeholder_sql = ",".join(["%s"] * len(insert_cols))

    # MariaDB-compatible idempotent upsert.
    if update_cols:
        update_sql = ",".join(f"`{c}`=VALUES(`{c}`)" for c in update_cols)
        return f"INSERT INTO {table} ({col_sql}) VALUES ({placeholder_sql}) ON DUPLICATE KEY UPDATE {update_sql}"

    return f"INSERT IGNORE INTO {table} ({col_sql}) VALUES ({placeholder_sql})"


def insert_rows(cur, table, rows, a, cleanup_first=True):
    if not rows or not table_exists(cur, table):
        return 0

    if cleanup_first:
        delete_scope(cur, table, a)

    meta = column_meta(cur, table)
    insert_cols = []
    for m in meta:
        c = m["COLUMN_NAME"]
        extra = (m.get("EXTRA") or "").lower()
        if "auto_increment" in extra:
            continue
        if any(c in r for r in rows):
            insert_cols.append(c)
        elif m["IS_NULLABLE"] == "NO" and m["COLUMN_DEFAULT"] is None:
            insert_cols.append(c)

    if not insert_cols:
        return 0

    dtype = {m["COLUMN_NAME"]: m["DATA_TYPE"] for m in meta}

    # avoid updating primary/unique identity-ish columns; update descriptive/count columns only
    no_update = {
        "profile_id", "target_date", "dt", "event_date", "run_id", "source_gen_run_id",
        "scenario_name", "scenario_id", "domain", "source_domain",
        "source_file_path", "file_path", "raw_file_path",
        "source_file_name", "file_name", "raw_file_name",
    }
    update_cols = [c for c in insert_cols if c not in no_update and c not in ("created_at", "registered_at")]

    sql = build_insert_sql(table, insert_cols, update_cols)

    affected = 0
    for row in rows:
        vals = []
        for c in insert_cols:
            v = row.get(c)
            if v is None:
                v = fallback_value(c, dtype.get(c, "varchar"), row, a)
            # PyMySQL cannot bind SQL function NOW() as expression, use datetime object instead.
            if v == "__NOW__":
                v = datetime.now()
            vals.append(v)
        cur.execute(sql, tuple(vals))
        affected += 1

    return affected


def generation_summary_row(a, file_rows):
    behavior_count = sum(r["record_count"] for r in file_rows if r["source_type"] == "behavior_w3c")
    transaction_count = sum(r["record_count"] for r in file_rows if r["source_type"] == "transaction_jsonl")
    state_count = sum(r["record_count"] for r in file_rows if r["source_type"] == "state_jsonl")

    return {
        "profile_id": a.profile_id,
        "target_date": a.target_date,
        "dt": a.target_date,
        "event_date": a.target_date,
        "run_id": a.run_id,
        "source_gen_run_id": a.source_gen_run_id or a.run_id,
        "scenario_name": a.scenario_name,
        "scenario_id": a.scenario_name,
        "domain": "source_generation",
        "source_domain": "source_generation",
        "source_layer": "source",
        "source_dir": a.source_dir,
        "status": "GENERATED",
        "generation_status": "GENERATED",
        "behavior_count": behavior_count,
        "transaction_count": transaction_count,
        "state_count": state_count,
        "file_count": len(file_rows),
        "record_count": behavior_count + transaction_count + state_count,
        "row_count": behavior_count + transaction_count + state_count,
        "summary_json": safe_json(
            {
                "source_dir": a.source_dir,
                "behavior_count": behavior_count,
                "transaction_count": transaction_count,
                "state_count": state_count,
                "file_count": len(file_rows),
            }
        ),
    }


def main():
    a = parse_args()
    file_rows = discover_files(a)
    summary = generation_summary_row(a, file_rows)

    con = connect(a)
    try:
        with con.cursor() as cur:
            inserted = {}
            inserted["source_file_manifest"] = insert_rows(cur, "source_file_manifest", file_rows, a, cleanup_first=True)
            inserted["batch_input_day"] = insert_rows(cur, "batch_input_day", file_rows, a, cleanup_first=True)
            inserted["source_generation_run"] = insert_rows(cur, "source_generation_run", [summary], a, cleanup_first=True)
            inserted["v05_commerce_source_generation_run"] = insert_rows(cur, "v05_commerce_source_generation_run", [summary], a, cleanup_first=True)

        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    print(f"[OK] register_v05_source_files files={len(file_rows)} inserted={inserted}")


if __name__ == "__main__":
    main()
