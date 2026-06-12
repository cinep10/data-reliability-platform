#!/usr/bin/env python3
"""Validate Phase4-B Step2 Authority Pattern Layer explicit contract.

Pattern interprets evidence before risk. It is not risk and must not contain
case-specific dimensions such as app_version, sdk_version, browser, URL, or
campaign as authority pattern names.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql

REQUIRED_COLUMNS = {
    "pattern_layer_version",
    "pattern_ready",
    "risk_pattern",
    "pattern_confidence",
    "pattern_reason",
    "pattern_payload_json",
}
ALLOWED_PATTERNS = {
    "stable",
    "localized_failure",
    "systemic_failure",
    "silent_distortion",
    "reconciliation_failure",
    "emerging_reliability_degradation",
}
FORBIDDEN_TOKENS = {
    "app_version", "sdk_version", "ios-app", "wc-ios", "browser", "url", "campaign", "chrome", "safari"
}


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
    p.add_argument("--allow-baseline-stable", action="store_true")
    p.add_argument("--require-pattern", action="store_true")
    p.add_argument("--min-pattern-confidence", type=float, default=0.05)
    p.add_argument("--expected-pattern", default="")
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
    row = fetchone(cur, "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(row.get("n") or 0) > 0


def columns(cur, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {str(r["column_name"]) for r in cur.fetchall()}


def fval(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key)
        return float(value if value is not None else default)
    except Exception:
        return default


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    baseline_like = args.scenario_name.lower() in {"baseline", "normal", "stable"}

    with connect(args) as con:
        with con.cursor() as cur:
            if not table_exists(cur, "reliability_analysis_result_day_v05"):
                print("[FAIL] missing reliability_analysis_result_day_v05")
                return 1
            missing = sorted(REQUIRED_COLUMNS - columns(cur, "reliability_analysis_result_day_v05"))
            if missing:
                print("[FAIL] missing authority pattern layer columns: " + ",".join(missing))
                return 1
            row = fetchone(
                cur,
                """
                SELECT *
                FROM reliability_analysis_result_day_v05
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.source_gen_run_id),
            )
            if not row:
                print("[FAIL] missing reliability analysis result row")
                return 1

            version = str(row.get("pattern_layer_version") or "")
            ready = int(row.get("pattern_ready") or 0)
            risk_pattern = str(row.get("risk_pattern") or "")
            confidence = fval(row, "pattern_confidence")
            reason = str(row.get("pattern_reason") or "")

            print("[AUTHORITY_PATTERN_LAYER]")
            print(f"profile_id={args.profile_id}")
            print(f"target_date={args.target_date}")
            print(f"scenario_name={args.scenario_name}")
            print(f"run_id={args.run_id}")
            print(f"source_gen_run_id={args.source_gen_run_id}")
            print(f"pattern_layer_version={version}")
            print(f"pattern_ready={ready}")
            print(f"risk_pattern={risk_pattern}")
            print(f"pattern_confidence={confidence:.6f}")
            print(f"pattern_reason={reason}")

            if not version.startswith("v05_phase4b_step2_pattern_layer"):
                failures.append(f"unexpected pattern_layer_version={version}")
            if ready != 1:
                failures.append("pattern_ready must be 1")
            if risk_pattern not in ALLOWED_PATTERNS:
                failures.append(f"risk_pattern must be generic allowed pattern, got {risk_pattern}")
            if confidence < -1e-9 or confidence > 1 + 1e-9:
                failures.append(f"pattern_confidence out of [0,1]: {confidence}")
            if args.expected_pattern and risk_pattern != args.expected_pattern:
                failures.append(f"expected risk_pattern={args.expected_pattern}, got {risk_pattern}")
            if baseline_like and args.allow_baseline_stable and risk_pattern != "stable":
                failures.append(f"baseline should be stable pattern, got {risk_pattern}")
            if (not baseline_like) and args.require_pattern:
                if risk_pattern == "stable":
                    failures.append("non-baseline run should not remain stable when --require-pattern is set")
                if confidence < args.min_pattern_confidence:
                    failures.append(f"pattern_confidence too low: {confidence:.6f} < {args.min_pattern_confidence:.6f}")
            lower_pattern = risk_pattern.lower()
            for token in FORBIDDEN_TOKENS:
                if token in lower_pattern:
                    failures.append(f"risk_pattern contains case-specific token: {token}")

            payload_text = row.get("pattern_payload_json") or ""
            if not payload_text:
                failures.append("pattern_payload_json missing")
            else:
                try:
                    payload = json.loads(payload_text)
                    if payload.get("layer") != "AUTHORITY_PATTERN_LAYER":
                        failures.append("pattern_payload_json.layer mismatch")
                    if payload.get("evidence_is_not_risk") is not True:
                        failures.append("pattern payload must state evidence_is_not_risk=true")
                    if payload.get("case_specific_features_disallowed") is not True:
                        failures.append("case-specific features must be disallowed in pattern layer")
                    if payload.get("obs_is_explanation_not_authority") is not True:
                        failures.append("OBS must remain explanation/reference, not authority pattern input")
                    if payload.get("risk_pattern") != risk_pattern:
                        failures.append("payload risk_pattern mismatch")
                    nxt = payload.get("next_step_contract", {})
                    if nxt.get("risk_layer_must_not_consume_case_specific_dimensions_directly") is not True:
                        failures.append("risk layer must not consume case-specific dimensions directly")
                except Exception as exc:
                    failures.append(f"pattern_payload_json invalid JSON: {exc}")

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_authority_pattern_layer passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
