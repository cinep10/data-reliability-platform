#!/usr/bin/env python3
"""Validate Phase3-C Step2 Reliability Analysis risk input interface.

This validator fixes the boundary between Authority Analytics and Authority Risk:
- build_v05_reliability_analysis.R must expose the exact columns consumed by
  build_v05_unified_risk_score.R.
- OBS may be reflected only as reference/supporting evidence upstream, not as an
  authority risk input here.
- This does not validate or change the risk formula itself.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql

REQUIRED_COLUMNS = {
    "statistical_evidence_effective_score",
    "statistical_significance",
    "cross_domain_propagation_strength",
    "affected_domains",
    "affected_domain_count",
    "reconciliation_confidence",
    "baseline_delta",
    "reconciliation_gap_score",
    "customer_impact_score",
    "transaction_loss_score",
    "authority_interface_version",
    "risk_input_ready",
    "authority_input_payload_json",
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
    p.add_argument("--require-signal", action="store_true")
    p.add_argument("--min-likelihood-input", type=float, default=0.05)
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


def parse_json_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


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
                print("[FAIL] missing risk input interface columns: " + ",".join(missing))
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

            stat = fval(row, "statistical_evidence_effective_score")
            propagation = fval(row, "cross_domain_propagation_strength")
            baseline_delta = fval(row, "baseline_delta")
            reconciliation_gap = fval(row, "reconciliation_gap_score")
            customer_impact = fval(row, "customer_impact_score")
            transaction_loss = fval(row, "transaction_loss_score")
            confidence = fval(row, "reconciliation_confidence")
            affected_count = int(row.get("affected_domain_count") or 0)
            affected = parse_json_list(row.get("affected_domains"))
            ready = int(row.get("risk_input_ready") or 0)
            version = str(row.get("authority_interface_version") or "")
            significance = str(row.get("statistical_significance") or "")

            print("[RELIABILITY_ANALYSIS_RISK_INPUT]")
            print(f"profile_id={args.profile_id}")
            print(f"target_date={args.target_date}")
            print(f"scenario_name={args.scenario_name}")
            print(f"run_id={args.run_id}")
            print(f"source_gen_run_id={args.source_gen_run_id}")
            print(f"interface_version={version}")
            print(f"risk_input_ready={ready}")
            print(f"statistical_evidence_effective_score={stat:.6f}")
            print(f"statistical_significance={significance}")
            print(f"cross_domain_propagation_strength={propagation:.6f}")
            print(f"affected_domains={affected}")
            print(f"affected_domain_count={affected_count}")
            print(f"reconciliation_confidence={confidence:.6f}")
            print(f"baseline_delta={baseline_delta:.6f}")
            print(f"reconciliation_gap_score={reconciliation_gap:.6f}")
            print(f"customer_impact_score={customer_impact:.6f}")
            print(f"transaction_loss_score={transaction_loss:.6f}")

            if not version.startswith("v05_phase3c_step2"):
                failures.append(f"unexpected authority_interface_version={version}")
            if ready != 1:
                failures.append("risk_input_ready must be 1")
            if significance not in {"stable", "low", "watch", "warning", "critical"}:
                failures.append(f"unexpected statistical_significance={significance}")
            for key, val in {
                "statistical_evidence_effective_score": stat,
                "cross_domain_propagation_strength": propagation,
                "reconciliation_confidence": confidence,
                "baseline_delta": baseline_delta,
                "reconciliation_gap_score": reconciliation_gap,
                "customer_impact_score": customer_impact,
                "transaction_loss_score": transaction_loss,
            }.items():
                if val < -1e-9 or val > 1 + 1e-9:
                    failures.append(f"{key} out of [0,1] range: {val}")

            payload_text = row.get("authority_input_payload_json") or ""
            if not payload_text:
                failures.append("authority_input_payload_json missing")
            else:
                try:
                    payload = json.loads(payload_text)
                    if payload.get("layer") != "AUTHORITY_ANALYTICS_LAYER":
                        failures.append("authority_input_payload_json.layer mismatch")
                    if payload.get("consumer") != "build_v05_unified_risk_score.R":
                        failures.append("authority_input_payload_json.consumer mismatch")
                    if payload.get("obs_authority_use") is not False:
                        failures.append("OBS must not be marked as authority risk input")
                    req = payload.get("required_outputs", {})
                    for k in [
                        "statistical_evidence_effective_score",
                        "statistical_significance",
                        "cross_domain_propagation_strength",
                        "affected_domains",
                        "affected_domain_count",
                        "reconciliation_confidence",
                        "baseline_delta",
                        "reconciliation_gap_score",
                        "customer_impact_score",
                        "transaction_loss_score",
                    ]:
                        if k not in req:
                            failures.append(f"authority payload missing required output: {k}")
                except Exception as exc:
                    failures.append(f"authority_input_payload_json invalid JSON: {exc}")

            signal = max(stat, propagation, baseline_delta, reconciliation_gap, customer_impact, transaction_loss)
            if baseline_like and args.allow_baseline_zero:
                if signal > 0.08:
                    failures.append(f"baseline authority risk input should be near zero: max_signal={signal:.6f}")
            elif args.require_signal and signal < args.min_likelihood_input:
                failures.append(f"risk input signal too low: {signal:.6f} < {args.min_likelihood_input:.6f}")

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_reliability_analysis_risk_input_interface passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
