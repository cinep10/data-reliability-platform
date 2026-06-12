#!/usr/bin/env python3
"""Validate CASE-OBS-001 Phase2-C4 Baseline Science Statistical Evidence Interface."""
from __future__ import annotations

import argparse
from typing import Any

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
    p.add_argument("--scenario-name", default="baseline")
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--baseline-window", default="30d")
    p.add_argument("--domains", default="batch,observability,reconciliation")
    p.add_argument("--allow-missing-domain", action="store_true")
    p.add_argument("--allow-low-sample", action="store_true")
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


def fetchone(cur, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    cur.execute(sql, params)
    return cur.fetchone() or {}


def table_exists(cur, table: str) -> bool:
    row = fetchone(
        cur,
        "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(row.get("n") or 0) > 0


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    requested_domains = {d.strip() for d in args.domains.split(",") if d.strip()}
    con = connect(args)
    try:
        with con.cursor() as cur:
            if not table_exists(cur, "v05_baseline_science_statistical_evidence_day"):
                print("[FAIL] missing v05_baseline_science_statistical_evidence_day")
                return 1

            base = (
                args.profile_id,
                args.target_date,
                args.scenario_name,
                args.run_id,
                args.source_gen_run_id,
                args.baseline_window,
            )
            row = fetchone(
                cur,
                """
                SELECT COUNT(*) AS row_count,
                       MAX(ABS(COALESCE(z_score,0))) AS max_abs_z,
                       MAX(COALESCE(historical_percentile,0)) AS max_percentile,
                       SUM(CASE WHEN control_limit_breach=1 THEN 1 ELSE 0 END) AS breach_count,
                       MAX(COALESCE(co_movement_score,0)) AS max_co_movement,
                       SUM(CASE WHEN statistical_significance IN ('stable','low','watch','warning','critical') THEN 1 ELSE 0 END) AS known_level_rows
                FROM v05_baseline_science_statistical_evidence_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                """,
                base,
            )
            row_count = int(row.get("row_count") or 0)
            print(
                f"[PASS] v05_baseline_science_statistical_evidence_day rows={row_count} "
                f"max_abs_z={float(row.get('max_abs_z') or 0):.6f} "
                f"max_percentile={float(row.get('max_percentile') or 0):.4f} "
                f"breach_count={int(row.get('breach_count') or 0)} "
                f"max_co_movement={float(row.get('max_co_movement') or 0):.6f}"
            )
            if row_count <= 0:
                failures.append("no statistical evidence rows")

            cur.execute(
                """
                SELECT evidence_domain, COUNT(*) AS row_count,
                       COUNT(DISTINCT metric_name) AS metric_count,
                       MIN(sample_days) AS min_sample_days,
                       MAX(sample_days) AS max_sample_days,
                       MAX(COALESCE(statistical_score,0)) AS max_score,
                       SUM(CASE WHEN control_limit_breach=1 THEN 1 ELSE 0 END) AS breach_count
                FROM v05_baseline_science_statistical_evidence_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                GROUP BY evidence_domain
                ORDER BY evidence_domain
                """,
                base,
            )
            domains = {str(r["evidence_domain"]): r for r in cur.fetchall()}
            for d, r in domains.items():
                print(
                    f"  - domain={d} rows={r['row_count']} metrics={r['metric_count']} "
                    f"min_days={r['min_sample_days']} max_days={r['max_sample_days']} "
                    f"max_score={float(r.get('max_score') or 0):.6f} breach={r.get('breach_count') or 0}"
                )

            missing = sorted(requested_domains - set(domains))
            if missing and not args.allow_missing_domain:
                failures.append("missing evidence domains: " + ",".join(missing))

            # Confirm enriched batch metric delta columns can be queried when batch domain exists.
            if "batch_metric_delta" in domains and table_exists(cur, "v05_batch_metric_delta_day"):
                batch_row = fetchone(
                    cur,
                    """
                    SELECT COUNT(*) AS row_count,
                           MAX(COALESCE(statistical_score,0)) AS max_score,
                           MAX(COALESCE(historical_percentile,0)) AS max_percentile
                    FROM v05_batch_metric_delta_day
                    WHERE profile_id=%s AND dt=%s AND scenario_name=%s
                      AND run_id=%s AND baseline_window=%s
                    """,
                    (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.baseline_window),
                )
                print(
                    f"[PASS] v05_batch_metric_delta_day enriched rows={batch_row.get('row_count') or 0} "
                    f"max_score={float(batch_row.get('max_score') or 0):.6f} "
                    f"max_percentile={float(batch_row.get('max_percentile') or 0):.4f}"
                )
    finally:
        con.close()

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_baseline_science_statistical_evidence passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
