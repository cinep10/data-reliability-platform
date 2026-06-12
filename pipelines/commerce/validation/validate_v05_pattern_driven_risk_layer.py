#!/usr/bin/env python3
"""Validate Phase4-B Step3 Pattern-driven Authority Risk Layer.

Contract:
- Risk Layer consumes `risk_pattern` produced by Authority Analytics.
- Evidence values are not allowed to be marked as direct risk drivers.
- Numeric risk remains Likelihood x Impact, but likelihood/impact are conditioned by pattern.
- Confidence remains separate from risk.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql

REQUIRED_COLUMNS = {
    "risk_model_version",
    "risk_model_formula",
    "risk_pattern",
    "pattern_confidence",
    "pattern_reason",
    "pattern_is_risk_driver",
    "evidence_direct_to_risk",
    "likelihood_score",
    "impact_score",
    "unified_risk_model_score",
    "overall_risk_score",
    "confidence_separate_from_risk",
    "confidence_score",
    "confidence_level",
    "score_payload_json",
}

ALLOWED_PATTERNS = {
    "stable",
    "localized_failure",
    "systemic_failure",
    "silent_distortion",
    "reconciliation_failure",
    "emerging_reliability_degradation",
    "interpretation_failure",
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
    p.add_argument("--allow-baseline-zero", action="store_true")
    p.add_argument("--require-risk-signal", action="store_true")
    p.add_argument("--min-likelihood", type=float, default=0.05)
    p.add_argument("--min-impact", type=float, default=0.05)
    p.add_argument("--min-risk", type=float, default=0.01)
    p.add_argument("--min-pattern-confidence", type=float, default=0.05)
    p.add_argument("--tolerance", type=float, default=0.0007)
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
            if not table_exists(cur, "unified_reliability_score_day_v05"):
                print("[FAIL] missing unified_reliability_score_day_v05")
                return 1
            missing = sorted(REQUIRED_COLUMNS - columns(cur, "unified_reliability_score_day_v05"))
            if missing:
                print("[FAIL] missing pattern-driven risk columns: " + ",".join(missing))
                return 1

            row = fetchone(
                cur,
                """
                SELECT *
                FROM unified_reliability_score_day_v05
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.source_gen_run_id),
            )
            if not row:
                print("[FAIL] missing unified risk row")
                return 1

            version = str(row.get("risk_model_version") or "")
            formula = str(row.get("risk_model_formula") or "")
            pattern = str(row.get("risk_pattern") or "")
            pattern_conf = fval(row, "pattern_confidence")
            likelihood = fval(row, "likelihood_score")
            impact = fval(row, "impact_score")
            model_score = fval(row, "unified_risk_model_score")
            overall = fval(row, "overall_risk_score")
            evidence_direct = int(row.get("evidence_direct_to_risk") or 0)
            pattern_driver = int(row.get("pattern_is_risk_driver") or 0)
            confidence_sep = int(row.get("confidence_separate_from_risk") or 0)
            level = str(row.get("final_risk_level") or "")
            reason = str(row.get("pattern_reason") or "")
            payload_raw = row.get("score_payload_json") or "{}"

            print("[PATTERN_DRIVEN_RISK]")
            print(f"profile_id={args.profile_id}")
            print(f"target_date={args.target_date}")
            print(f"scenario_name={args.scenario_name}")
            print(f"run_id={args.run_id}")
            print(f"source_gen_run_id={args.source_gen_run_id}")
            print(f"risk_model_version={version}")
            print(f"risk_model_formula={formula}")
            print(f"risk_pattern={pattern}")
            print(f"pattern_confidence={pattern_conf:.6f}")
            print(f"likelihood_score={likelihood:.6f}")
            print(f"impact_score={impact:.6f}")
            print(f"unified_risk_model_score={model_score:.6f}")
            print(f"overall_risk_score={overall:.6f}")
            print(f"final_risk_level={level}")
            print(f"pattern_is_risk_driver={pattern_driver}")
            print(f"evidence_direct_to_risk={evidence_direct}")
            print(f"confidence_separate_from_risk={confidence_sep}")
            print(f"pattern_reason={reason[:240]}")

            if not version.startswith("v05_phase4b_step3"):
                failures.append(f"unexpected risk_model_version={version}")
            if "pattern" not in formula or "evidence" not in formula:
                failures.append("risk_model_formula must mention pattern and evidence bridge")
            if pattern not in ALLOWED_PATTERNS:
                failures.append(f"risk_pattern not in allowed set: {pattern}")
            if pattern_driver != 1:
                failures.append("pattern_is_risk_driver must be 1")
            if evidence_direct != 0:
                failures.append("evidence_direct_to_risk must be 0")
            if confidence_sep != 1:
                failures.append("confidence_separate_from_risk must be 1")
            if abs((likelihood * impact) - overall) > args.tolerance:
                failures.append(f"risk score mismatch: likelihood*impact={likelihood*impact:.6f} overall={overall:.6f}")
            if abs(model_score - overall) > args.tolerance:
                failures.append(f"model_score mismatch: model={model_score:.6f} overall={overall:.6f}")

            try:
                payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
            except Exception as exc:
                failures.append(f"score_payload_json is not valid JSON: {exc}")
                payload = {}
            if isinstance(payload, dict):
                auth = payload.get("authority_input") or {}
                if auth.get("evidence_direct_to_risk") is not False:
                    failures.append("payload.authority_input.evidence_direct_to_risk must be false")
                if auth.get("required_bridge") != "evidence_to_pattern":
                    failures.append("payload.authority_input.required_bridge must be evidence_to_pattern")
                if (payload.get("pattern_model") or {}).get("risk_pattern") != pattern:
                    failures.append("payload.pattern_model.risk_pattern mismatch")

            if baseline_like:
                if not args.allow_baseline_zero and overall > args.min_risk:
                    failures.append(f"baseline risk should be near zero: {overall:.6f}")
                if pattern not in {"stable", "emerging_reliability_degradation"} and args.allow_baseline_zero:
                    failures.append(f"baseline should remain stable-ish, got pattern={pattern}")
            elif args.require_risk_signal:
                if pattern == "stable":
                    failures.append("non-baseline risk pattern must not be stable")
                if pattern_conf < args.min_pattern_confidence:
                    failures.append(f"pattern confidence too low {pattern_conf:.6f} < {args.min_pattern_confidence:.6f}")
                if likelihood < args.min_likelihood:
                    failures.append(f"likelihood too low {likelihood:.6f} < {args.min_likelihood:.6f}")
                if impact < args.min_impact:
                    failures.append(f"impact too low {impact:.6f} < {args.min_impact:.6f}")
                if overall < args.min_risk:
                    failures.append(f"risk too low {overall:.6f} < {args.min_risk:.6f}")

    if failures:
        print("[FAIL] pattern-driven risk validation failed")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("[OK] validate_v05_pattern_driven_risk_layer passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
