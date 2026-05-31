#!/usr/bin/env python3
"""Build v0.5 Operational Observability measurement.

This module is intentionally a measurement materializer, not a risk/semantic
interpreter. It compares same-run WebServer reality evidence with WC collector
telemetry and canonical behavior events.

Role boundary:
- Python: count and persist DIRECT_OBSERVABILITY_MEASUREMENT deltas.
- R: interpret those deltas into risk score / semantic risk.
- SQL: persist tables and views.
- Shell: orchestrate only.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Iterable, List, Tuple

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", default="")
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--truncate-target", action="store_true")
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


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(cur.fetchone()["n"] or 0) > 0


def table_cols(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return {r["column_name"] for r in cur.fetchall()}


def safe_div(num: int | float, den: int | float) -> float:
    den = float(den or 0)
    if den <= 0:
        return 0.0
    return max(0.0, min(1.0, float(num or 0) / den))


def count_rows(cur, table: str, where: str, params: Iterable[Any]) -> int:
    if not table_exists(cur, table):
        return 0
    cur.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", tuple(params))
    return int(cur.fetchone()["c"] or 0)


def aggregate_stage(cur, table: str, args: argparse.Namespace) -> Dict[str, int]:
    if not table_exists(cur, table):
        return {k: 0 for k in ("hits", "uv", "checkout", "product", "payment", "browse", "search", "other")}

    cols = table_cols(cur, table)
    date_col = "dt" if "dt" in cols else "target_date"
    where = ["profile_id=%s", f"{date_col}=%s"]
    params: List[Any] = [args.profile_id, args.target_date]
    if "source_gen_run_id" in cols:
        where.append("source_gen_run_id=%s")
        params.append(args.source_gen_run_id)
    if "scenario_name" in cols and table == "stg_webserver_log_hit":
        where.append("scenario_name=%s")
        params.append(args.scenario_name)
    where_sql = " AND ".join(where)

    # Use SQL literals with escaped %% because PyMySQL uses % formatting.
    path_expr = "LOWER(COALESCE(path,''))" if "path" in cols else "''"
    stage_expr = "LOWER(COALESCE(funnel_stage,page_type,''))" if {"funnel_stage", "page_type"}.intersection(cols) else "''"
    uv_expr = "COUNT(DISTINCT ip)" if table == "stg_webserver_log_hit" else "COUNT(DISTINCT COALESCE(NULLIF(pcid,''), NULLIF(sid,''), ip))"

    sql = f"""
    SELECT
      COUNT(*) AS hits,
      {uv_expr} AS uv,
      SUM(CASE WHEN {path_expr} LIKE '%%checkout%%' OR {path_expr} LIKE '%%payment%%' OR {stage_expr} LIKE '%%checkout%%' OR {stage_expr} LIKE '%%payment%%' THEN 1 ELSE 0 END) AS checkout,
      SUM(CASE WHEN {path_expr} LIKE '%%product%%' OR {stage_expr} LIKE '%%product%%' THEN 1 ELSE 0 END) AS product,
      SUM(CASE WHEN {path_expr} LIKE '%%payment%%' OR {stage_expr} LIKE '%%payment%%' THEN 1 ELSE 0 END) AS payment,
      SUM(CASE WHEN {stage_expr} LIKE '%%browse%%' THEN 1 ELSE 0 END) AS browse,
      SUM(CASE WHEN {stage_expr} LIKE '%%search%%' THEN 1 ELSE 0 END) AS search,
      SUM(CASE WHEN {stage_expr} NOT LIKE '%%checkout%%' AND {stage_expr} NOT LIKE '%%payment%%' AND {stage_expr} NOT LIKE '%%product%%' AND {stage_expr} NOT LIKE '%%browse%%' AND {stage_expr} NOT LIKE '%%search%%' THEN 1 ELSE 0 END) AS other
    FROM {table}
    WHERE {where_sql}
    """
    cur.execute(sql, tuple(params))
    row = cur.fetchone() or {}
    return {k: int(row.get(k) or 0) for k in ("hits", "uv", "checkout", "product", "payment", "browse", "search", "other")}


def count_canonical_behavior(cur, args: argparse.Namespace) -> int:
    if not table_exists(cur, "canonical_behavior_events"):
        return 0
    cols = table_cols(cur, "canonical_behavior_events")
    where = ["profile_id=%s", "target_date=%s"]
    params: List[Any] = [args.profile_id, args.target_date]
    if "run_id" in cols:
        where.append("run_id=%s")
        params.append(args.run_id)
    if "source_gen_run_id" in cols:
        where.append("source_gen_run_id=%s")
        params.append(args.source_gen_run_id)
    if "scenario_name" in cols:
        where.append("scenario_name=%s")
        params.append(args.scenario_name)
    elif "scenario_id" in cols:
        where.append("scenario_id=%s")
        params.append(args.scenario_name)
    return count_rows(cur, "canonical_behavior_events", " AND ".join(where), params)


def top_missing_stage(web: Dict[str, int], wc: Dict[str, int]) -> str:
    candidates = []
    for stage in ("checkout", "product", "payment", "browse", "search", "other"):
        candidates.append((stage, max(0, web.get(stage, 0) - wc.get(stage, 0)), web.get(stage, 0)))
    stage, gap, total = max(candidates, key=lambda x: x[1])
    if gap <= 0 or total <= 0:
        return "none"
    return stage


def build_measurement(cur, args: argparse.Namespace) -> Dict[str, Any]:
    web = aggregate_stage(cur, "stg_webserver_log_hit", args)
    wc = aggregate_stage(cur, "stg_wc_log_hit", args)
    canonical = count_canonical_behavior(cur, args)

    web_hits = web["hits"]
    wc_hits = wc["hits"]
    collection_gap_count = max(0, web_hits - wc_hits)
    canonical_gap_count = max(0, web_hits - canonical)

    row: Dict[str, Any] = {
        "profile_id": args.profile_id,
        "target_date": args.target_date,
        "scenario_name": args.scenario_name,
        "run_id": args.run_id,
        "source_gen_run_id": args.source_gen_run_id,
        "baseline_mode": "same_run_evidence_baseline",
        "delta_source_type": "DIRECT_OBSERVABILITY_MEASUREMENT",
        "web_hits": web_hits,
        "wc_hits": wc_hits,
        "canonical_behavior_events": canonical,
        "collection_gap_count": collection_gap_count,
        "collection_gap_rate": safe_div(collection_gap_count, web_hits),
        "canonical_gap_count": canonical_gap_count,
        "canonical_gap_rate": safe_div(canonical_gap_count, web_hits),
        "web_uv_ip": web["uv"],
        "wc_uv_pcid": wc["uv"],
        "uv_gap_rate": safe_div(max(0, web["uv"] - wc["uv"]), web["uv"]),
        "web_checkout_hits": web["checkout"],
        "wc_checkout_hits": wc["checkout"],
        "checkout_missing_rate": safe_div(max(0, web["checkout"] - wc["checkout"]), web["checkout"]),
        "web_product_hits": web["product"],
        "wc_product_hits": wc["product"],
        "product_missing_rate": safe_div(max(0, web["product"] - wc["product"]), web["product"]),
        "web_payment_hits": web["payment"],
        "wc_payment_hits": wc["payment"],
        "payment_missing_rate": safe_div(max(0, web["payment"] - wc["payment"]), web["payment"]),
        "top_missing_stage": top_missing_stage(web, wc),
        "suspected_root_cause": "wc_collector_collection_gap" if collection_gap_count > 0 else "none",
        "detail_json": json.dumps({"web_stage": web, "wc_stage": wc}, ensure_ascii=False),
    }
    return row


def upsert_measurement(cur, row: Dict[str, Any], truncate: bool) -> None:
    if truncate:
        cur.execute(
            """
            DELETE FROM v05_observability_measurement_day
            WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
            """,
            (row["profile_id"], row["target_date"], row["scenario_name"], row["run_id"], row["source_gen_run_id"]),
        )
    cols = list(row.keys())
    placeholders = ",".join(["%s"] * len(cols))
    assignments = ",".join([f"{c}=VALUES({c})" for c in cols if c not in ("profile_id", "target_date", "scenario_name", "run_id", "source_gen_run_id")])
    sql = f"INSERT INTO v05_observability_measurement_day ({','.join(cols)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {assignments}"
    cur.execute(sql, tuple(row[c] for c in cols))


def main() -> int:
    args = parse_args()
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            if not table_exists(cur, "v05_observability_measurement_day"):
                raise RuntimeError("missing v05_observability_measurement_day; apply sql/036_v05_observability_measurement_schema_mariadb.sql first")
            row = build_measurement(cur, args)
            upsert_measurement(cur, row, args.truncate_target)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(
        "[OK] build_v05_observability_measurement_day "
        f"scenario={args.scenario_name} run_id={args.run_id} source_gen_run_id={args.source_gen_run_id} "
        f"web_hits={row['web_hits']} wc_hits={row['wc_hits']} canonical_behavior_events={row['canonical_behavior_events']} "
        f"gap={row['collection_gap_rate']:.6f} baseline_mode={row['baseline_mode']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
