#!/usr/bin/env python3
"""Build generic observability action recommendations from semantic risk.

This replaces CASE-OBS-001-only action overlay with a semantic-driven action
mapping. Python is used here for action persistence, consistent with existing
v0.5 action builder responsibilities.
"""
from __future__ import annotations

import argparse
from typing import Any, Dict, List

import pymysql

ACTION_MAP = {
    "WC Collection Completeness Risk": [
        (1, "wc collector validation", "Validate WC collector ingest path, beacon delivery, and collector-side drop/retry behavior."),
        (2, "web-wc reconciliation check", "Compare WebServer source hits with WC telemetry by run_id/source_gen_run_id and segment the collection gap."),
        (3, "observability KPI annotation", "Annotate or suppress KPI dashboard decisions until collection completeness is recovered."),
    ],
    "Operational Observability Distortion": [
        (1, "observability evidence audit", "Audit reality-vs-observability evidence before treating KPI degradation as business degradation."),
        (2, "dashboard freshness annotation", "Annotate dashboard with observability degradation and decision-freeze guidance."),
        (3, "collector recovery validation", "Validate collector recovery and backfill/replay completeness."),
    ],
}


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
    return p.parse_args()


def connect(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass, database=args.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["n"] or 0) > 0


def table_cols(cur, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def get_semantic(cur, args) -> tuple[str, float]:
    cur.execute(
        """
        SELECT recommended_semantic_risk, observability_overall_score
        FROM r_v05_observability_analysis_day
        WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
        LIMIT 1
        """,
        (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.source_gen_run_id),
    )
    row = cur.fetchone()
    if not row:
        return "None", 0.0
    return str(row.get("recommended_semantic_risk") or "None"), float(row.get("observability_overall_score") or 0.0)


def insert_actions(cur, args, semantic: str, score: float) -> int:
    actions = ACTION_MAP.get(semantic, [])
    if not actions or score < 0.15:
        return 0
    table = "action_recommendation_day_v05"
    if not table_exists(cur, table):
        raise RuntimeError(f"missing {table}")
    cols = table_cols(cur, table)
    # Remove existing generic observability actions for same run to keep idempotent.
    where = "profile_id=%s AND target_date=%s AND run_id=%s"
    params: List[Any] = [args.profile_id, args.target_date, args.run_id]
    if "source_gen_run_id" in cols:
        where += " AND source_gen_run_id=%s"
        params.append(args.source_gen_run_id)
    if "scenario_name" in cols:
        where += " AND scenario_name=%s"
        params.append(args.scenario_name)
    if "action_type" in cols:
        cur.execute(f"DELETE FROM {table} WHERE {where} AND action_type IN ('wc collector validation','web-wc reconciliation check','observability KPI annotation','observability evidence audit','dashboard freshness annotation','collector recovery validation')", tuple(params))
    inserted = 0
    for rank, action_type, recommended_action in actions:
        row: Dict[str, Any] = {
            "profile_id": args.profile_id,
            "target_date": args.target_date,
            "scenario_name": args.scenario_name,
            "run_id": args.run_id,
            "source_gen_run_id": args.source_gen_run_id,
            "action_rank": rank,
            "action_type": action_type,
            "recommended_action": recommended_action,
            "action_reason": f"semantic={semantic}; observability_score={score:.6f}; source=DIRECT_OBSERVABILITY_MEASUREMENT",
        }
        insert_cols = [c for c in row if c in cols]
        if not insert_cols:
            continue
        sql = f"INSERT INTO {table} ({','.join(insert_cols)}) VALUES ({','.join(['%s']*len(insert_cols))})"
        cur.execute(sql, tuple(row[c] for c in insert_cols))
        inserted += 1
    return inserted


def main() -> int:
    args = parse_args()
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            semantic, score = get_semantic(cur, args)
            inserted = insert_actions(cur, args, semantic, score)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"[OK] build_v05_observability_action_recommendation semantic={semantic} score={score:.6f} inserted={inserted}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
