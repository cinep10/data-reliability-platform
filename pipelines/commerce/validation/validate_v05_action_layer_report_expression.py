#!/usr/bin/env python3
"""Validate Authority Action + OBS Reference Action report expression.

This validates the reporting contract after Phase4-B Step4/5:
- Authority actions are selected from Authority Pattern Layer.
- OBS reference actions are supporting explanation/audit actions only.
- Neither action layer is a risk engine.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
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
    p.add_argument("--require-authority-action", action="store_true")
    p.add_argument("--require-reference-action", action="store_true")
    p.add_argument("--allow-baseline-no-reference", action="store_true")
    p.add_argument("--figure-manifest")
    p.add_argument("--require-manifest", action="store_true")
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


def columns(cur, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {str(r["column_name"]) for r in cur.fetchall()}


def f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        val = row.get(key)
        return float(val if val is not None else default)
    except Exception:
        return default


def s(row: dict[str, Any], key: str, default: str = "") -> str:
    val = row.get(key)
    return default if val is None else str(val)


def main() -> int:
    a = parse_args()
    failures: list[str] = []
    baseline_like = a.scenario_name.lower() in {"baseline", "normal", "stable"}
    required_cols = {
        "action_layer",
        "reference_action_source",
        "reference_action_reason",
        "authority_action_rank",
        "reference_action_rank",
        "action_catalog_source",
        "action_catalog_mode",
        "action_is_risk_engine",
        "risk_pattern",
    }
    with connect(a) as con:
        with con.cursor() as cur:
            missing = sorted(required_cols - columns(cur, "action_recommendation_day_v05"))
            if missing:
                failures.append("missing action layer columns: " + ",".join(missing))
            cur.execute(
                """
                SELECT * FROM action_recommendation_day_v05
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
                ORDER BY action_rank
                """,
                (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
            )
            rows = list(cur.fetchall())
    if not rows:
        failures.append("missing action rows")
        rows = []

    authority = [r for r in rows if s(r, "action_layer") == "authority_action" or s(r, "action_catalog_source") == "authority_pattern_layer"]
    reference = [r for r in rows if s(r, "action_layer") == "reference_obs_action" or s(r, "action_catalog_source") == "obs_reference_layer"]

    if a.require_authority_action and not authority:
        failures.append("expected at least one authority_action row")
    if a.require_reference_action and not baseline_like and not reference:
        failures.append("expected at least one reference_obs_action row for non-baseline")
    if baseline_like and not a.allow_baseline_no_reference and not reference:
        failures.append("baseline without reference actions requires --allow-baseline-no-reference")

    for r in authority:
        if int(f(r, "action_is_risk_engine", 1)) != 0:
            failures.append("authority action must not be risk engine")
        if s(r, "action_catalog_source") != "authority_pattern_layer":
            failures.append(f"authority action source mismatch: {s(r,'action_catalog_source')}")
        if s(r, "action_layer") not in {"", "authority_action"}:
            failures.append(f"authority action_layer mismatch: {s(r,'action_layer')}")
    for r in reference:
        if int(f(r, "action_is_risk_engine", 1)) != 0:
            failures.append("OBS reference action must not be risk engine")
        if s(r, "action_catalog_source") != "obs_reference_layer":
            failures.append(f"OBS reference source mismatch: {s(r,'action_catalog_source')}")
        if s(r, "action_layer") != "reference_obs_action":
            failures.append(f"OBS reference action_layer mismatch: {s(r,'action_layer')}")
        if not s(r, "reference_action_reason"):
            failures.append("OBS reference action missing reference_action_reason")

    manifest = None
    if a.figure_manifest:
        mp = Path(a.figure_manifest)
        if not mp.is_file():
            if a.require_manifest:
                failures.append(f"missing figure manifest: {mp}")
        else:
            try:
                manifest = json.loads(mp.read_text(encoding="utf-8"))
            except Exception as exc:
                failures.append(f"manifest parse failed: {exc}")
    if manifest:
        als = manifest.get("action_layer_summary") or {}
        if a.require_authority_action and not als.get("authority_actions"):
            failures.append("manifest missing action_layer_summary.authority_actions")
        if a.require_reference_action and not baseline_like and not als.get("reference_obs_actions"):
            failures.append("manifest missing action_layer_summary.reference_obs_actions")
        if manifest.get("authority_action_source") != "authority_pattern_layer":
            failures.append(f"manifest authority_action_source mismatch: {manifest.get('authority_action_source')}")
        if reference and manifest.get("reference_action_source") != "obs_reference_layer":
            failures.append(f"manifest reference_action_source mismatch: {manifest.get('reference_action_source')}")

    print("[ACTION_LAYER_REPORT]")
    print(f"scenario={a.scenario_name} run_id={a.run_id} source_gen_run_id={a.source_gen_run_id}")
    print(f"authority_actions={len(authority)} reference_obs_actions={len(reference)} total_actions={len(rows)}")
    if authority:
        print("authority_first=" + s(authority[0], "recommended_action"))
    if reference:
        print("reference_first=" + s(reference[0], "recommended_action"))
    if failures:
        print("[FAIL] validate_v05_action_layer_report_expression failed")
        for failure in failures:
            print("  - " + failure)
        return 1
    print("[OK] validate_v05_action_layer_report_expression passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
