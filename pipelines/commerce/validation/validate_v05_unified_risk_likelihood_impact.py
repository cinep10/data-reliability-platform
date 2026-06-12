#!/usr/bin/env python3
"""Validate Phase3-C Step3/4 Unified Risk = Likelihood x Impact.

This validates the Authority Risk Layer contract:
- build_v05_unified_risk_score.R consumes Authority Analytics Interface output.
- risk_score = likelihood_score * impact_score.
- confidence is stored separately and is not multiplied into risk.
- OBS is not marked as an authority risk input.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql

REQUIRED_COLUMNS = {
    "risk_model_version",
    "authority_risk_input_version",
    "risk_model_formula",
    "likelihood_score",
    "impact_score",
    "unified_risk_model_score",
    "statistical_likelihood_score",
    "baseline_deviation_score",
    "propagation_likelihood_score",
    "multi_metric_co_movement_score",
    "business_impact_score",
    "kpi_distortion_impact_score",
    "transaction_impact_score",
    "affected_domain_impact_score",
    "runtime_decision_impact_score",
    "root_cause_confidence",
    "reconciliation_confidence",
    "confidence_score",
    "confidence_level",
    "confidence_separate_from_risk",
    "risk_classification",
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
    p.add_argument("--tolerance", type=float, default=0.0005)
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


def columns(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
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
                print("[FAIL] missing unified risk model columns: " + ",".join(missing))
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

            likelihood = fval(row, "likelihood_score")
            impact = fval(row, "impact_score")
            model_score = fval(row, "unified_risk_model_score")
            overall = fval(row, "overall_risk_score")
            confidence = fval(row, "confidence_score")
            root_conf = fval(row, "root_cause_confidence")
            recon_conf = fval(row, "reconciliation_confidence")
            sep = int(row.get("confidence_separate_from_risk") or 0)
            version = str(row.get("risk_model_version") or "")
            formula = str(row.get("risk_model_formula") or "")
            level = str(row.get("final_risk_level") or "")
            confidence_level = str(row.get("confidence_level") or "")

            print("[UNIFIED_RISK_MODEL]")
            print(f"profile_id={args.profile_id}")
            print(f"target_date={args.target_date}")
            print(f"scenario_name={args.scenario_name}")
            print(f"run_id={args.run_id}")
            print(f"source_gen_run_id={args.source_gen_run_id}")
            print(f"risk_model_version={version}")
            print(f"risk_model_formula={formula}")
            print(f"likelihood_score={likelihood:.6f}")
            print(f"impact_score={impact:.6f}")
            print(f"unified_risk_model_score={model_score:.6f}")
            print(f"overall_risk_score={overall:.6f}")
            print(f"final_risk_level={level}")
            print(f"confidence_score={confidence:.6f}")
            print(f"root_cause_confidence={root_conf:.6f}")
            print(f"reconciliation_confidence={recon_conf:.6f}")
            print(f"confidence_level={confidence_level}")
            print(f"confidence_separate_from_risk={sep}")

            if not version.startswith("v05_phase3c_step3"):
                failures.append(f"unexpected risk_model_version={version}")
            if "likelihood" not in formula or "impact" not in formula:
                failures.append(f"risk_model_formula must describe likelihood x impact: {formula}")
            if sep != 1:
                failures.append("confidence_separate_from_risk must be 1")
            for k in [
                "likelihood_score", "impact_score", "unified_risk_model_score", "overall_risk_score",
                "statistical_likelihood_score", "baseline_deviation_score", "propagation_likelihood_score",
                "multi_metric_co_movement_score", "business_impact_score", "kpi_distortion_impact_score",
                "transaction_impact_score", "affected_domain_impact_score", "runtime_decision_impact_score",
                "root_cause_confidence", "reconciliation_confidence", "confidence_score",
            ]:
                val = fval(row, k)
                if val < -1e-9 or val > 1 + 1e-9:
                    failures.append(f"{k} out of [0,1] range: {val}")

            expected = likelihood * impact
            if abs(model_score - expected) > args.tolerance:
                failures.append(f"model score mismatch: {model_score:.6f} != likelihood*impact {expected:.6f}")
            if abs(overall - model_score) > args.tolerance:
                failures.append(f"overall risk should equal unified model score: {overall:.6f} != {model_score:.6f}")

            payload_text = row.get("score_payload_json") or ""
            if not payload_text:
                failures.append("score_payload_json missing")
            else:
                try:
                    payload = json.loads(payload_text)
                    if payload.get("architecture_layer") != "AUTHORITY_RISK_LAYER":
                        failures.append("payload architecture_layer mismatch")
                    auth = payload.get("authority_input", {})
                    if auth.get("obs_is_authority_risk_input") is not False:
                        failures.append("OBS must not be authority risk input")
                    if auth.get("semantic_is_risk_driver") is not False:
                        failures.append("semantic must not be risk driver")
                    conf = payload.get("confidence_model", {})
                    if conf.get("confidence_separate_from_risk") is not True:
                        failures.append("payload must mark confidence as separate from risk")
                    if payload.get("final", {}).get("risk_score") is None:
                        failures.append("payload final.risk_score missing")
                except Exception as exc:
                    failures.append(f"score_payload_json invalid JSON: {exc}")

            if baseline_like and args.allow_baseline_zero:
                if max(likelihood, impact, model_score, overall) > 0.001:
                    failures.append(
                        f"baseline risk model should be near zero: likelihood={likelihood:.6f} impact={impact:.6f} risk={overall:.6f}"
                    )
            elif args.require_risk_signal:
                if likelihood < args.min_likelihood:
                    failures.append(f"likelihood too low: {likelihood:.6f} < {args.min_likelihood:.6f}")
                if impact < args.min_impact:
                    failures.append(f"impact too low: {impact:.6f} < {args.min_impact:.6f}")
                if overall < args.min_risk:
                    failures.append(f"risk too low: {overall:.6f} < {args.min_risk:.6f}")

    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        return 1
    print("[OK] validate_v05_unified_risk_likelihood_impact passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
