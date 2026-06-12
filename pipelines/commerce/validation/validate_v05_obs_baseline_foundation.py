#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pymysql

TABLES = [
    "v05_obs_baseline_reference_day",
    "v05_obs_baseline_feature_snapshot_day",
    "v05_obs_baseline_stat_profile_day",
    "v05_obs_baseline_compare_day",
]


def parse_args():
    p = argparse.ArgumentParser(description="Validate CASE-OBS-001 Phase2-C1 Baseline Foundation outputs.")
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
    p.add_argument("--baseline-window", default="30d")
    p.add_argument("--baseline-scenario", default="baseline")
    p.add_argument("--require-native", action="store_true")
    p.add_argument("--allow-low-sample", action="store_true", help="Allow single-day smoke baselines seeded with --include-target-date.")
    p.add_argument("--max-baseline-severity", default="normal", choices=["normal", "watch", "warning", "critical"])
    return p.parse_args()


def connect(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=True, cursorclass=pymysql.cursors.DictCursor)


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["n"] or 0) > 0


def count_where(cur, table: str, where: str, params: tuple) -> int:
    cur.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params)
    return int(cur.fetchone()["n"] or 0)


def sev_rank(s: str) -> int:
    return {"normal": 0, "watch": 1, "warning": 2, "critical": 3}.get(s or "normal", 9)


def main():
    a = parse_args()
    con = connect(a)
    failed = False
    try:
        with con.cursor() as cur:
            for table in TABLES:
                if not table_exists(cur, table):
                    print(f"[FAIL] {table}: missing")
                    failed = True
                    continue
                if table == "v05_obs_baseline_feature_snapshot_day":
                    cnt = count_where(cur, table, "profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s", (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id))
                elif table == "v05_obs_baseline_reference_day":
                    cnt = count_where(cur, table, "profile_id=%s AND target_date=%s AND baseline_window=%s AND baseline_scenario_name=%s", (a.profile_id, a.target_date, a.baseline_window, a.baseline_scenario))
                elif table == "v05_obs_baseline_stat_profile_day":
                    cnt = count_where(cur, table, "profile_id=%s AND target_date=%s AND baseline_window=%s AND baseline_scenario_name=%s", (a.profile_id, a.target_date, a.baseline_window, a.baseline_scenario))
                else:
                    cnt = count_where(cur, table, "profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s", (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id, a.baseline_window))
                status = "PASS" if cnt > 0 else "FAIL"
                if cnt <= 0:
                    failed = True
                print(f"[{status}] {table}: rows={cnt}")

            cur.execute(
                """
                SELECT baseline_type, sample_days, is_usable, quality_score, fallback_policy
                FROM v05_obs_baseline_reference_day
                WHERE profile_id=%s AND target_date=%s AND baseline_window=%s AND baseline_scenario_name=%s
                ORDER BY baseline_type
                """,
                (a.profile_id, a.target_date, a.baseline_window, a.baseline_scenario),
            )
            refs = cur.fetchall()
            for r in refs:
                print(f"  - reference type={r['baseline_type']} sample_days={r['sample_days']} usable={r['is_usable']} quality={float(r['quality_score'] or 0):.6f} policy={r['fallback_policy']}")
            if not a.allow_low_sample and not any(int(r.get("is_usable") or 0) == 1 for r in refs):
                print("[FAIL] no usable baseline reference; rerun with more baseline days or use --allow-low-sample for smoke tests")
                failed = True

            if a.require_native:
                cur.execute(
                    """
                    SELECT DISTINCT dimension_key
                    FROM v05_obs_baseline_feature_snapshot_day
                    WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
                      AND dimension_type='app_platform'
                    """,
                    (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
                )
                keys = {str(r["dimension_key"]) for r in cur.fetchall()}
                missing = {"ios_app", "android_app"} - keys
                if missing:
                    print(f"[FAIL] native app_platform baseline features missing: {sorted(missing)}")
                    failed = True
                else:
                    print("[PASS] native baseline features present: ios_app/android_app")

            cur.execute(
                """
                SELECT severity, COUNT(*) AS row_count, MAX(ABS(COALESCE(z_score,0))) AS max_abs_z
                FROM v05_obs_baseline_compare_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                GROUP BY severity
                ORDER BY severity
                """,
                (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id, a.baseline_window),
            )
            sev_rows = cur.fetchall()
            worst = "normal"
            for r in sev_rows:
                sev = str(r["severity"])
                if sev_rank(sev) > sev_rank(worst):
                    worst = sev
                print(f"  - compare severity={sev} rows={r['row_count']} max_abs_z={float(r['max_abs_z'] or 0):.6f}")
            if a.scenario_name == a.baseline_scenario and sev_rank(worst) > sev_rank(a.max_baseline_severity):
                print(f"[FAIL] baseline scenario produced severity={worst} above allowed {a.max_baseline_severity}")
                failed = True

            cur.execute(
                """
                SELECT dimension_type, metric_name, COUNT(*) AS row_count,
                       MAX(ABS(COALESCE(baseline_delta,0))) AS max_abs_delta
                FROM v05_obs_baseline_compare_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                GROUP BY dimension_type, metric_name
                ORDER BY dimension_type, metric_name
                LIMIT 40
                """,
                (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id, a.baseline_window),
            )
            for r in cur.fetchall():
                print(f"  - compare dimension={r['dimension_type']} metric={r['metric_name']} rows={r['row_count']} max_abs_delta={float(r['max_abs_delta'] or 0):.8f}")
    finally:
        con.close()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
