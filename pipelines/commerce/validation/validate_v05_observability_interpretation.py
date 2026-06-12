#!/usr/bin/env python3
"""Validate CASE-OBS-001 Phase3-A OBS interpretation/root-cause confidence output."""
from __future__ import annotations

import argparse
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
    p.add_argument("--min-confidence", type=float, default=0.0)
    p.add_argument("--require-signal", action="store_true")
    p.add_argument("--allow-baseline-no-signal", action="store_true")
    return p.parse_args()


def connect(args: argparse.Namespace):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int((cur.fetchone() or {}).get("n") or 0) > 0


def columns(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    con = connect(args)
    try:
        with con.cursor() as cur:
            if not table_exists(cur, "r_v05_observability_interpretation_day"):
                print("[FAIL] missing r_v05_observability_interpretation_day")
                return 1
            cur.execute(
                """
                SELECT COUNT(*) AS row_count,
                       MAX(root_cause_confidence) AS max_confidence,
                       MAX(affected_metrics) AS max_affected_metrics,
                       MAX(propagation_strength) AS max_propagation_strength,
                       MAX(statistical_severity_score) AS max_statistical_severity,
                       SUM(CASE WHEN analysis_status IN ('SIGNAL','WATCH') THEN 1 ELSE 0 END) AS signal_rows
                FROM r_v05_observability_interpretation_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s
                """,
                (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.source_gen_run_id),
            )
            summary = cur.fetchone() or {}
            cur.execute(
                """
                SELECT root_cause_rank, root_cause_dimension, root_cause_value,
                       root_cause_confidence, confidence_level, affected_metrics,
                       propagation_level, statistical_severity_level, analysis_status,
                       analysis_summary
                FROM r_v05_observability_interpretation_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s
                ORDER BY root_cause_rank ASC
                LIMIT 5
                """,
                (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.source_gen_run_id),
            )
            top_rows = cur.fetchall()
            obs_cols = columns(cur, "r_v05_observability_analysis_day") if table_exists(cur, "r_v05_observability_analysis_day") else set()
            linked_cols = {
                "root_cause_confidence", "root_cause_dimension", "root_cause_value",
                "affected_metrics", "propagation_strength", "statistical_severity_level",
            }
            linked_schema = linked_cols.issubset(obs_cols)

    finally:
        con.close()

    row_count = int(summary.get("row_count") or 0)
    max_conf = float(summary.get("max_confidence") or 0.0)
    signal_rows = int(summary.get("signal_rows") or 0)

    print("[OBS_INTERPRETATION]")
    print(f"profile_id={args.profile_id}")
    print(f"target_date={args.target_date}")
    print(f"scenario_name={args.scenario_name}")
    print(f"run_id={args.run_id}")
    print(f"source_gen_run_id={args.source_gen_run_id}")
    print(
        "summary="
        f"rows={row_count} max_confidence={max_conf:.6f} "
        f"max_affected_metrics={float(summary.get('max_affected_metrics') or 0):.0f} "
        f"max_propagation={float(summary.get('max_propagation_strength') or 0):.6f} "
        f"max_statistical_severity={float(summary.get('max_statistical_severity') or 0):.6f} "
        f"signal_rows={signal_rows} linked_schema={linked_schema}"
    )
    for r in top_rows:
        print(
            "  - "
            f"rank={r.get('root_cause_rank')} dim={r.get('root_cause_dimension')} value={r.get('root_cause_value')} "
            f"confidence={float(r.get('root_cause_confidence') or 0):.6f} "
            f"level={r.get('confidence_level')} affected_metrics={r.get('affected_metrics')} "
            f"propagation={r.get('propagation_level')} severity={r.get('statistical_severity_level')} "
            f"status={r.get('analysis_status')}"
        )

    if row_count <= 0:
        failures.append("interpretation rows missing")
    if not linked_schema:
        failures.append("r_v05_observability_analysis_day enhancement columns missing")
    if max_conf < args.min_confidence:
        failures.append(f"max confidence too low: {max_conf:.6f} < {args.min_confidence:.6f}")
    if args.require_signal and signal_rows <= 0:
        if args.allow_baseline_no_signal and args.scenario_name == "baseline":
            print("[INFO] baseline no-signal allowed")
        else:
            failures.append("expected SIGNAL/WATCH interpretation row")

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_observability_interpretation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
