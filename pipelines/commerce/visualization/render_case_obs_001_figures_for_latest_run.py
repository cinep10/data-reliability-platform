#!/usr/bin/env python3
"""Render CASE-OBS-001 figures for the latest completed run of a scenario.

This helper is intentionally additive. It fixes the common workflow problem where
validate_case_obs_001_figures is run before the scenario's figure_manifest.json
has been regenerated after a visualization patch.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render CASE-OBS-001 figures from latest reliability run.")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", default="nethru")
    p.add_argument("--db-pass", default="nethru1234")
    p.add_argument("--db-name", default="weblog")
    p.add_argument("--profile-id", default="commerce_deliver")
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--repo-root", default=os.getcwd())
    p.add_argument("--top-n", type=int, default=15)
    p.add_argument("--validate", action="store_true")
    p.add_argument("--require-visual-v6", action="store_true")
    return p.parse_args()


def connect(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def latest_run(a: argparse.Namespace) -> dict[str, Any]:
    with connect(a) as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, source_gen_run_id, created_at,
                       risk_pattern, failure_mechanism, mechanism_source
                FROM reliability_analysis_result_day_v05
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                ORDER BY created_at DESC, run_id DESC, source_gen_run_id DESC
                LIMIT 1
                """,
                (a.profile_id, a.target_date, a.scenario_name),
            )
            return cur.fetchone() or {}


def main() -> int:
    a = parse_args()
    repo = Path(a.repo_root).resolve()
    row = latest_run(a)
    if not row:
        print(
            "[FAIL] no reliability_analysis_result_day_v05 row found. "
            "Run the scenario pipeline first, then rerun this renderer.",
            file=sys.stderr,
        )
        return 2
    run_id = int(row["run_id"])
    source_gen_run_id = int(row["source_gen_run_id"])
    out_dir = repo / "artifacts" / "case_study" / "CASE-OBS-001" / a.target_date / a.scenario_name / "figures"
    r_file = repo / "pipelines" / "commerce" / "visualization" / "build_case_obs_001_figures.R"
    if not r_file.exists():
        print(f"[FAIL] missing R figure builder: {r_file}", file=sys.stderr)
        return 2

    cmd = [
        "Rscript", str(r_file),
        "--db-host", a.db_host,
        "--db-port", str(a.db_port),
        "--db-user", a.db_user,
        "--db-pass", a.db_pass,
        "--db-name", a.db_name,
        "--profile-id", a.profile_id,
        "--target-date", a.target_date,
        "--scenario-name", a.scenario_name,
        "--run-id", str(run_id),
        "--source-gen-run-id", str(source_gen_run_id),
        "--output-dir", str(out_dir),
        "--view-mode", "decision_support",
        "--include-engineer-appendix", "true",
        "--top-n", str(a.top_n),
    ]
    print("[RENDER] " + " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(repo))
    if rc != 0:
        return rc

    manifest = out_dir / "figure_manifest.json"
    if not manifest.exists():
        print(f"[FAIL] render completed but manifest is missing: {manifest}", file=sys.stderr)
        return 3

    print(
        "[OK] rendered CASE-OBS-001 figures "
        f"scenario={a.scenario_name} run_id={run_id} source_gen_run_id={source_gen_run_id} "
        f"pattern={row.get('risk_pattern')} mechanism={row.get('failure_mechanism')} source={row.get('mechanism_source')} "
        f"figure_dir={out_dir}"
    )

    if a.validate:
        vcmd = [
            sys.executable, "-m", "pipelines.commerce.validation.validate_case_obs_001_figures",
            "--figure-dir", str(out_dir),
            "--require-operational-report",
            "--require-customer-visual-redesign",
            "--require-engineer-appendix",
        ]
        if a.require_visual_v6:
            vcmd.append("--require-visual-v6")
        print("[VALIDATE] " + " ".join(vcmd))
        return subprocess.call(vcmd, cwd=str(repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
