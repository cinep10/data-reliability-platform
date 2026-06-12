#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pymysql

TABLES = [
    "v05_obs_app_version_measurement_day",
    "v05_obs_sdk_version_measurement_day",
    "v05_obs_url_gap_day",
    "v05_obs_client_gap_day",
    "v05_obs_metric_gap_day",
]


def parse_args():
    p = argparse.ArgumentParser(description="Validate CASE-OBS-001 Phase2-B Gap Measurement Layer outputs.")
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--require-native", action="store_true")
    p.add_argument("--max-baseline-gap-rate", type=float, default=0.001)
    return p.parse_args()


def connect(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=True, cursorclass=pymysql.cursors.DictCursor)


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["n"] or 0) > 0


def table_count(cur, table: str, a) -> int:
    cur.execute(
        f"""
        SELECT COUNT(*) AS c
        FROM {table}
        WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
        """,
        (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
    )
    return int(cur.fetchone()["c"] or 0)


def main():
    a = parse_args()
    con = connect(a)
    failed = False
    try:
        with con.cursor() as cur:
            for table in TABLES:
                if not table_exists(cur, table):
                    print(f"[FAIL] {table}: missing table")
                    failed = True
                    continue
                cnt = table_count(cur, table, a)
                status = "PASS" if cnt > 0 else "FAIL"
                if cnt <= 0:
                    failed = True
                print(f"[{status}] {table}: rows={cnt}")

            cur.execute(
                """
                SELECT app_platform, COUNT(*) AS row_count, SUM(webserver_events) AS web_events,
                       SUM(wc_events) AS wc_events, MAX(missing_rate) AS max_missing_rate
                FROM v05_obs_app_version_measurement_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
                GROUP BY app_platform
                ORDER BY app_platform
                """,
                (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
            )
            platforms = {r["app_platform"]: r for r in cur.fetchall()}
            for p, r in platforms.items():
                print(f"  - app_platform={p} rows={r['row_count']} web={r['web_events']} wc={r['wc_events']} max_missing_rate={float(r['max_missing_rate'] or 0):.6f}")

            if a.require_native:
                missing = {"ios_app", "android_app"} - set(platforms.keys())
                if missing:
                    print(f"[FAIL] native app platforms missing from app version measurement: {sorted(missing)}")
                    failed = True
                else:
                    print("[PASS] native app platforms present in app version measurement: ios_app/android_app")

            if a.scenario_name == "baseline":
                cur.execute(
                    """
                    SELECT MAX(missing_rate) AS max_app_gap
                    FROM v05_obs_app_version_measurement_day
                    WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
                    """,
                    (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
                )
                max_app_gap = float((cur.fetchone() or {}).get("max_app_gap") or 0)
                if max_app_gap > a.max_baseline_gap_rate:
                    print(f"[FAIL] baseline app version gap too high: {max_app_gap:.6f} > {a.max_baseline_gap_rate:.6f}")
                    failed = True
                else:
                    print(f"[PASS] baseline app version gap within tolerance: {max_app_gap:.6f}")

            cur.execute(
                """
                SELECT dimension_type, metric_name, COUNT(*) AS row_count, MAX(gap_rate) AS max_gap_rate
                FROM v05_obs_metric_gap_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
                GROUP BY dimension_type, metric_name
                ORDER BY dimension_type, metric_name
                """,
                (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
            )
            metric_rows = cur.fetchall()
            for r in metric_rows[:30]:
                print(f"  - metric dimension={r['dimension_type']} metric={r['metric_name']} rows={r['row_count']} max_gap_rate={float(r['max_gap_rate'] or 0):.6f}")
    finally:
        con.close()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
