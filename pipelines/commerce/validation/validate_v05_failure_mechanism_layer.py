#!/usr/bin/env python3
"""Validate CASE-OBS-001 Phase4-D Failure Mechanism layer.

This validator keeps Pattern taxonomy generic while asserting that concrete
scenario differences are represented by failure_mechanism/mechanism_source.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate v0.5 failure mechanism output for CASE-OBS-001.")
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
    p.add_argument("--expected-pattern", required=True)
    p.add_argument("--expected-mechanism", required=True)
    p.add_argument("--expected-mechanism-source", required=True)
    p.add_argument("--min-mechanism-confidence", type=float, default=0.05)
    return p.parse_args()


def conn(a: argparse.Namespace):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)


def fetch(cur, table: str, a: argparse.Namespace) -> dict[str, Any] | None:
    cur.execute(
        f"""
        SELECT * FROM {table}
        WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
        ORDER BY created_at DESC LIMIT 1
        """,
        (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
    )
    return cur.fetchone()


def main() -> int:
    a = parse_args()
    c = conn(a)
    try:
        with c.cursor() as cur:
            row = fetch(cur, "reliability_analysis_result_day_v05", a)
    finally:
        c.close()
    if not row:
        print("[FAIL] missing reliability_analysis_result_day_v05 row", file=sys.stderr)
        return 2
    pattern = str(row.get("risk_pattern") or "")
    mechanism = str(row.get("failure_mechanism") or "")
    source = str(row.get("mechanism_source") or "")
    conf = float(row.get("mechanism_confidence") or 0)
    errors = []
    if pattern != a.expected_pattern:
        errors.append(f"risk_pattern expected={a.expected_pattern} actual={pattern}")
    if mechanism != a.expected_mechanism:
        errors.append(f"failure_mechanism expected={a.expected_mechanism} actual={mechanism}")
    if source != a.expected_mechanism_source:
        errors.append(f"mechanism_source expected={a.expected_mechanism_source} actual={source}")
    if conf < a.min_mechanism_confidence:
        errors.append(f"mechanism_confidence {conf:.6f} < {a.min_mechanism_confidence:.6f}")
    if errors:
        print("[FAIL] validate_v05_failure_mechanism_layer " + "; ".join(errors), file=sys.stderr)
        return 3
    print(
        f"[PASS] validate_v05_failure_mechanism_layer scenario={a.scenario_name} "
        f"risk_pattern={pattern} failure_mechanism={mechanism} mechanism_source={source} mechanism_confidence={conf:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
