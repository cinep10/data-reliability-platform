#!/usr/bin/env python3
"""Validate CASE-OBS-001 Phase2-C3 threshold calibration output."""
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
    p.add_argument("--require-native", action="store_true")
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


def fetchone(cur, sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
    cur.execute(sql, params)
    return cur.fetchone() or {}


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    con = connect(args)
    try:
        with con.cursor() as cur:
            base_params = (
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
                       SUM(CASE WHEN warning_threshold < watch_threshold THEN 1 ELSE 0 END) AS bad_watch_warning,
                       SUM(CASE WHEN critical_threshold < warning_threshold THEN 1 ELSE 0 END) AS bad_warning_critical,
                       MIN(sample_days) AS min_sample_days,
                       MAX(sample_days) AS max_sample_days,
                       SUM(CASE WHEN calibration_status IN ('usable','low_sample','low_volume') THEN 1 ELSE 0 END) AS known_status_rows
                FROM v05_obs_threshold_calibration_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                """,
                base_params,
            )
            count = int(row.get("row_count") or 0)
            if count <= 0:
                failures.append("v05_obs_threshold_calibration_day has no rows")
            if int(row.get("bad_watch_warning") or 0) > 0:
                failures.append("warning_threshold lower than watch_threshold")
            if int(row.get("bad_warning_critical") or 0) > 0:
                failures.append("critical_threshold lower than warning_threshold")

            print(f"[PASS] v05_obs_threshold_calibration_day rows={count} min_days={row.get('min_sample_days')} max_days={row.get('max_sample_days')}")

            cur.execute(
                """
                SELECT dimension_type, COUNT(*) AS row_count,
                       MIN(sample_days) AS min_days,
                       MAX(sample_days) AS max_days,
                       SUM(CASE WHEN calibration_status='usable' THEN 1 ELSE 0 END) AS usable_rows,
                       SUM(CASE WHEN calibration_status='low_volume' THEN 1 ELSE 0 END) AS low_volume_rows
                FROM v05_obs_threshold_calibration_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                GROUP BY dimension_type
                ORDER BY dimension_type
                """,
                base_params,
            )
            dims = {str(r["dimension_type"]): r for r in cur.fetchall()}
            for d, r in dims.items():
                print(
                    f"  - dimension={d} rows={r['row_count']} min_days={r['min_days']} max_days={r['max_days']} usable={r['usable_rows']} low_volume={r['low_volume_rows']}"
                )

            required_dims = {"all", "app_platform", "app_version", "app_sdk", "sdk_version", "client", "url"}
            missing = sorted(required_dims - set(dims))
            if missing:
                failures.append("missing threshold dimensions: " + ",".join(missing))

            if args.require_native:
                cur.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM v05_obs_expected_metric_day
                    WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                      AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                      AND dimension_type IN ('app_platform','app_version','app_sdk')
                      AND (dimension_key LIKE '%%ios%%' OR dimension_key LIKE '%%android%%')
                    """,
                    base_params,
                )
                native_n = int((cur.fetchone() or {}).get("n") or 0)
                if native_n <= 0:
                    failures.append("native expected metrics not available for threshold calibration")
                else:
                    print(f"[PASS] native expected metrics available for calibration rows={native_n}")

            if not args.allow_low_sample:
                low_row = fetchone(
                    cur,
                    """
                    SELECT COUNT(*) AS n
                    FROM v05_obs_threshold_calibration_day
                    WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                      AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                      AND calibration_status='low_sample'
                    """,
                    base_params,
                )
                if int(low_row.get("n") or 0) > 0:
                    failures.append("low_sample calibration rows exist; pass --allow-low-sample for early backfill tests")
    finally:
        con.close()

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_obs_threshold_calibration passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
