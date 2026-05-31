#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path as _Path

PROJECT_ROOT = _Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pymysql

from pipelines.common.v04_cookie_contract import CONTRACT_DB_COLS, filter_existing_columns, parse_apache_line


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--source-gen-run-id", required=True, type=int)
    p.add_argument("--input-dir", required=True)
    p.add_argument("--source-file-path")
    p.add_argument("--recursive", action="store_true", default=True)
    p.add_argument("--truncate-target", action="store_true")
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--scenario-name")
    p.add_argument("--scenario-id")
    p.add_argument("--source-generation-scenario")
    p.add_argument("--prefer-query-source-scenario", action="store_true", default=True)
    return p.parse_args()


def unique_preserve_order(items):
    out = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        out.append(item)
        seen.add(item)
    return out


def connect(args):
    return pymysql.connect(
        host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass,
        database=args.db_name, charset="utf8mb4", autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def has_table(cur, table):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["cnt"]) > 0


def has_column(cur, table, col):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s", (table, col))
    return int(cur.fetchone()["cnt"]) > 0


def manifest_files(cur, args) -> list[Path]:
    if not has_table(cur, "source_file_manifest"):
        return []
    path_cols = ["source_file_path", "file_path", "path", "output_file", "out_file"]
    cols = [c for c in path_cols if has_column(cur, "source_file_manifest", c)]
    if not cols:
        return []
    date_col = "dt" if has_column(cur, "source_file_manifest", "dt") else ("target_date" if has_column(cur, "source_file_manifest", "target_date") else None)
    where = []
    params: list[Any] = []
    if has_column(cur, "source_file_manifest", "profile_id"):
        where.append("profile_id=%s")
        params.append(args.profile_id)
    if date_col:
        where.append(f"{date_col}=%s")
        params.append(args.target_date)
    if has_column(cur, "source_file_manifest", "source_gen_run_id"):
        where.append("source_gen_run_id=%s")
        params.append(args.source_gen_run_id)
    sql = "SELECT " + ",".join(cols) + " FROM source_file_manifest"
    if where:
        sql += " WHERE " + " AND ".join(where)
    cur.execute(sql, tuple(params))
    out = []
    for r in cur.fetchall():
        for c in cols:
            if r.get(c):
                out.append(Path(str(r[c])))
                break
    return out


def discover_files(cur, args) -> list[Path]:
    files = []
    if args.source_file_path:
        files.append(Path(args.source_file_path))
    files.extend(manifest_files(cur, args))
    d = Path(args.input_dir)
    if d.exists():
        files.extend(d.rglob("*.log") if args.recursive else d.glob("*.log"))
    uniq = []
    seen = set()
    for f in files:
        try:
            rp = str(f.resolve())
        except Exception:
            rp = str(f)
        if rp in seen:
            continue
        if f.exists() and f.is_file() and f.suffix == ".log":
            uniq.append(f)
            seen.add(rp)
    if not uniq:
        raise FileNotFoundError(f"no .log files found. input_dir={d}, source_gen_run_id={args.source_gen_run_id}.")
    return sorted(uniq)


def query_params(row: dict[str, Any]) -> dict[str, str]:
    raw = row.get("url_raw") or row.get("url_full") or ""
    try:
        parsed = urlparse(str(raw))
        q = parse_qs(parsed.query, keep_blank_values=True)
        return {k: (v[0] if v else "") for k, v in q.items()}
    except Exception:
        return {}


def normalize_identity(row: dict[str, Any], args) -> dict[str, Any]:
    qp = query_params(row)
    cookie_scenario_name = row.get("scenario_name")
    cookie_scenario_id = row.get("scenario_id")
    query_source_scenario = (
        qp.get("v05_source_scenario")
        or qp.get("source_scenario")
        or qp.get("exo_source")
        or row.get("v05_source_scenario")
        or row.get("exo_source")
    )

    requested = args.scenario_name or (query_source_scenario if args.prefer_query_source_scenario else None) or cookie_scenario_name
    requested_id = args.scenario_id or requested or cookie_scenario_id
    source_generation = args.source_generation_scenario or cookie_scenario_name or cookie_scenario_id or requested

    if requested:
        row["scenario_name"] = requested
    if requested_id:
        row["scenario_id"] = requested_id
    if source_generation:
        row["source_generation_scenario"] = source_generation

    if query_source_scenario and not row.get("v05_source_scenario"):
        row["v05_source_scenario"] = query_source_scenario
    for key in ("source_anomaly", "v05_runtime_layer", "identity_flag", "pcid_stability"):
        if qp.get(key):
            row[key] = qp.get(key)
    return row


def insert_rows(cur, rows):
    base_cols = [
        "profile_id","source_gen_run_id","dt","ts","ip","method","protocol","url_raw","url_full","url_norm","host","path","query",
        "status","bytes","latency_ms","ref","ref_host","ua","kv_raw","uid","pcid","sid","device_type","evt","event_type",
        "page_type","product_type","service_domain","funnel_stage","is_conversion","accept_lang","cc",
        "scenario_id","scenario_name","source_generation_scenario",
    ]
    candidate_cols = unique_preserve_order(base_cols + list(CONTRACT_DB_COLS))
    cols = unique_preserve_order(filter_existing_columns(cur, "stg_webserver_log_hit", candidate_cols))
    sql = f"INSERT INTO stg_webserver_log_hit ({','.join('`'+c+'`' for c in cols)}) VALUES ({','.join(['%s']*len(cols))})"
    values = [[r.get(c) for c in cols] for r in rows]
    if values:
        cur.executemany(sql, values)


def main():
    args = parse_args()
    conn = connect(args)
    inserted = 0
    bad = 0
    scenario_counts: dict[tuple[str | None, str | None, str | None], int] = {}
    try:
        with conn.cursor() as cur:
            files = discover_files(cur, args)
            print("[INFO] source_files=" + ",".join(str(f) for f in files))
            if args.truncate_target:
                cur.execute(
                    "DELETE FROM stg_webserver_log_hit WHERE profile_id=%s AND dt=%s AND source_gen_run_id=%s",
                    (args.profile_id, args.target_date, args.source_gen_run_id),
                )
            batch = []
            for fp in files:
                with fp.open("r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        try:
                            r = parse_apache_line(line)
                            if r["dt"] != args.target_date:
                                continue
                            r = normalize_identity(r, args)
                            r["profile_id"] = args.profile_id
                            r["source_gen_run_id"] = args.source_gen_run_id
                            key = (r.get("scenario_id"), r.get("scenario_name"), r.get("source_generation_scenario"))
                            scenario_counts[key] = scenario_counts.get(key, 0) + 1
                            batch.append(r)
                            if len(batch) >= 1000:
                                insert_rows(cur, batch)
                                inserted += len(batch)
                                batch = []
                        except Exception as e:
                            bad += 1
                            if bad <= 5:
                                print(f"[WARN] parse/insert failed file={fp} err={e}", file=sys.stderr)
            if batch:
                insert_rows(cur, batch)
                inserted += len(batch)
        conn.commit()
        print(f"[load_source_webserver_stage_v04] inserted={inserted} bad_rows={bad}")
        for (sid, sname, sgen), cnt in sorted(scenario_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"[SCENARIO_IDENTITY] scenario_id={sid} scenario_name={sname} source_generation_scenario={sgen} cnt={cnt}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
