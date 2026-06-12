#!/usr/bin/env python3
"""Validate CASE-OBS-001 Phase2-C3 forecast interface table.

The forecast interface is intentionally table/interface only. It does not require
trained ML rows. It validates table existence and optional interface seed rows.
"""
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
    p.add_argument("--scenario-name", default="baseline")
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--baseline-window", default="30d")
    p.add_argument("--require-rows", action="store_true", help="Require interface rows. Default only checks schema.")
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


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    con = connect(args)
    try:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS n
                FROM information_schema.tables
                WHERE table_schema=DATABASE()
                  AND table_name='v05_obs_forecast_metric_day'
                """
            )
            exists = int((cur.fetchone() or {}).get("n") or 0) > 0
            if not exists:
                print("[FAIL] missing table v05_obs_forecast_metric_day")
                return 1
            print("[PASS] v05_obs_forecast_metric_day table exists")

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema=DATABASE()
                  AND table_name='v05_obs_forecast_metric_day'
                """
            )
            cols = {str(r["column_name"]) for r in cur.fetchall()}
            required = {
                "profile_id", "target_date", "scenario_name", "run_id", "source_gen_run_id",
                "dimension_type", "dimension_key", "metric_name", "forecast_model_name",
                "forecast_value", "forecast_lower", "forecast_upper", "forecast_confidence",
                "model_status", "quality_status",
            }
            missing = sorted(required - cols)
            if missing:
                failures.append("missing forecast columns: " + ",".join(missing))
            else:
                print("[PASS] forecast interface required columns exist")

            params = (
                args.profile_id,
                args.target_date,
                args.scenario_name,
                args.run_id,
                args.source_gen_run_id,
                args.baseline_window,
            )
            cur.execute(
                """
                SELECT COUNT(*) AS row_count,
                       SUM(CASE WHEN model_status='interface_only' THEN 1 ELSE 0 END) AS interface_rows,
                       SUM(CASE WHEN forecast_confidence <> 0 THEN 1 ELSE 0 END) AS nonzero_confidence_rows
                FROM v05_obs_forecast_metric_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                """,
                params,
            )
            row = cur.fetchone() or {}
            count = int(row.get("row_count") or 0)
            print(f"[INFO] forecast interface rows={count} interface_only={row.get('interface_rows') or 0} nonzero_confidence={row.get('nonzero_confidence_rows') or 0}")
            if args.require_rows and count <= 0:
                failures.append("forecast interface rows required but absent")
    finally:
        con.close()

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_obs_forecast_interface passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
