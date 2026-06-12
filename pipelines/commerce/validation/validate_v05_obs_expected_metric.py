from __future__ import annotations

import argparse
import sys
from typing import Any

import pymysql
from pymysql.cursors import DictCursor


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate CASE-OBS-001 Phase2-C2 expected metric model output")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", default="nethru")
    p.add_argument("--db-pass", default="nethru1234")
    p.add_argument("--db-name", default="weblog")
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--baseline-window", default="30d")
    p.add_argument("--require-native", action="store_true")
    p.add_argument("--allow-low-sample", action="store_true")
    return p.parse_args()


def connect(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


def scalar(cur, sql: str, params: tuple[Any, ...]) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    return None if not row else next(iter(row.values()))


def main() -> int:
    a = parse_args()
    errors: list[str] = []
    with connect(a) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS row_count
            FROM v05_obs_expected_metric_day
            WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
              AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
            """,
            (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id, a.baseline_window),
        )
        row_count = int(cur.fetchone()["row_count"] or 0)
        if row_count <= 0:
            errors.append("v05_obs_expected_metric_day has no rows")
        print(f"[PASS] v05_obs_expected_metric_day: rows={row_count}" if row_count > 0 else "[FAIL] v05_obs_expected_metric_day: rows=0")

        cur.execute(
            """
            SELECT model_status, quality_status, COUNT(*) AS row_count,
                   MAX(ABS(COALESCE(expected_delta,0))) AS max_abs_delta,
                   MAX(ABS(COALESCE(expected_delta_rate,0))) AS max_abs_delta_rate
            FROM v05_obs_expected_metric_day
            WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
              AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
            GROUP BY model_status, quality_status
            ORDER BY model_status, quality_status
            """,
            (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id, a.baseline_window),
        )
        for r in cur.fetchall():
            print(
                "  - status model={model_status} quality={quality_status} rows={row_count} "
                "max_abs_delta={max_abs_delta:.8f} max_abs_delta_rate={max_abs_delta_rate:.8f}".format(
                    model_status=r["model_status"],
                    quality_status=r["quality_status"],
                    row_count=int(r["row_count"] or 0),
                    max_abs_delta=float(r["max_abs_delta"] or 0),
                    max_abs_delta_rate=float(r["max_abs_delta_rate"] or 0),
                )
            )

        cur.execute(
            """
            SELECT dimension_type, metric_name, COUNT(*) AS row_count,
                   MIN(selected_sample_days) AS min_days,
                   MAX(expected_breach) AS max_breach
            FROM v05_obs_expected_metric_day
            WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
              AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
            GROUP BY dimension_type, metric_name
            ORDER BY dimension_type, metric_name
            """,
            (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id, a.baseline_window),
        )
        for r in cur.fetchall():
            print(f"  - expected dimension={r['dimension_type']} metric={r['metric_name']} rows={r['row_count']} min_days={r['min_days']} breach={r['max_breach']}")

        if a.require_native:
            cur.execute(
                """
                SELECT dimension_key
                FROM v05_obs_expected_metric_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                  AND dimension_type='app_platform'
                GROUP BY dimension_key
                """,
                (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id, a.baseline_window),
            )
            platforms = {str(r["dimension_key"]) for r in cur.fetchall()}
            missing = {"ios_app", "android_app"} - platforms
            if missing:
                errors.append(f"missing native expected metrics: {sorted(missing)}")
            else:
                print("[PASS] native expected metrics present: ios_app/android_app")

        if not a.allow_low_sample:
            low = int(scalar(
                cur,
                """
                SELECT COUNT(*) AS row_count
                FROM v05_obs_expected_metric_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                  AND model_status IN ('low_sample','missing_baseline')
                """,
                (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id, a.baseline_window),
            ) or 0)
            if low > 0:
                errors.append(f"low-sample expected rows exist: {low}")
        else:
            print("[INFO] allow_low_sample enabled for expected metric validation")

        if a.scenario_name == "baseline":
            max_delta = float(scalar(
                cur,
                """
                SELECT MAX(ABS(COALESCE(expected_delta,0))) AS max_delta
                FROM v05_obs_expected_metric_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                """,
                (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id, a.baseline_window),
            ) or 0)
            if max_delta > 1e-6:
                errors.append(f"baseline expected delta is not zero: {max_delta}")
            else:
                print(f"[PASS] baseline expected delta within tolerance: {max_delta:.8f}")

    if errors:
        for e in errors:
            print(f"[FAIL] {e}")
        return 1
    print("[OK] validate_v05_obs_expected_metric passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
