#!/usr/bin/env python3
"""Validate Phase4-B/Phase4-C Authority Evidence Layer contract.

Evidence is not risk. OBS remains reference. This validator accepts either
persisted evidence-v2 columns or the same values nested in evidence_payload_json,
so existing runs can be validated while the persistence DDL/R patch is rolling out.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql

REQUIRED_COLUMNS = {
    "evidence_layer_version",
    "evidence_ready",
    "baseline_evidence_score",
    "statistical_evidence_group_score",
    "propagation_evidence_score",
    "impact_evidence_score",
    "concentration_evidence_score",
    "criticality_evidence_score",
    "evidence_payload_json",
    "evidence_summary",
}
REQUIRED_GROUPS = {"baseline", "statistical", "propagation", "impact", "concentration", "criticality"}


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
    p.add_argument("--require-evidence-signal", action="store_true")
    p.add_argument("--min-evidence-signal", type=float, default=0.05)
    p.add_argument("--require-concentration", action="store_true")
    p.add_argument("--min-concentration", type=float, default=0.15)
    p.add_argument("--require-criticality", action="store_true")
    p.add_argument("--min-criticality", type=float, default=0.50)
    p.add_argument("--require-business-kpi-distortion", action="store_true")
    p.add_argument("--min-business-kpi-distortion", type=float, default=0.60)
    p.add_argument("--require-traffic-preservation", action="store_true")
    p.add_argument("--min-traffic-preservation", type=float, default=0.30)
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


def payload_float(obj: Any, keys: set[str]) -> float | None:
    """Find the first numeric value in nested payload by any candidate key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k) in keys:
                try:
                    return float(v)
                except Exception:
                    pass
        for v in obj.values():
            found = payload_float(v, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = payload_float(v, keys)
            if found is not None:
                return found
    return None


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    baseline_like = args.scenario_name.lower() in {"baseline", "normal", "stable"}

    with connect(args) as con:
        with con.cursor() as cur:
            if not table_exists(cur, "reliability_analysis_result_day_v05"):
                print("[FAIL] missing reliability_analysis_result_day_v05")
                return 1
            table_cols = columns(cur, "reliability_analysis_result_day_v05")
            missing = sorted(REQUIRED_COLUMNS - table_cols)
            if missing:
                print("[FAIL] missing authority evidence layer columns: " + ",".join(missing))
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

    payload_text = row.get("evidence_payload_json") or ""
    payload: dict[str, Any] = {}
    payload_error: str | None = None
    if payload_text:
        try:
            payload = json.loads(payload_text)
        except Exception as exc:
            payload_error = str(exc)

    version = str(row.get("evidence_layer_version") or "")
    ready = int(row.get("evidence_ready") or 0)
    baseline = fval(row, "baseline_evidence_score")
    statistical = fval(row, "statistical_evidence_group_score")
    propagation = fval(row, "propagation_evidence_score")
    impact = fval(row, "impact_evidence_score")
    concentration = fval(row, "concentration_evidence_score")
    criticality = fval(row, "criticality_evidence_score")
    event_criticality = fval(row, "event_criticality_score")
    conversion_criticality = fval(row, "conversion_criticality_score")
    revenue_criticality = fval(row, "revenue_criticality_score")
    business_kpi_distortion = fval(row, "business_kpi_distortion_score")
    traffic_preservation = fval(row, "traffic_preservation_score")

    # Fallback to payload/log contract values during the transition where R computes
    # evidence-v2 values but older table schemas or insert lists did not persist them.
    business_payload = payload_float(payload, {"business_kpi_distortion_score", "business_kpi_distortion", "business_kpi_distortion_evidence_score"})
    traffic_payload = payload_float(payload, {"traffic_preservation_score", "traffic_preservation", "traffic_preservation_evidence_score"})
    event_payload = payload_float(payload, {"event_criticality_score", "event_criticality"})
    conversion_payload = payload_float(payload, {"conversion_criticality_score", "conversion_criticality"})
    revenue_payload = payload_float(payload, {"revenue_criticality_score", "revenue_criticality"})
    if business_kpi_distortion <= 0 and business_payload is not None:
        business_kpi_distortion = business_payload
    if traffic_preservation <= 0 and traffic_payload is not None:
        traffic_preservation = traffic_payload
    if event_criticality <= 0 and event_payload is not None:
        event_criticality = event_payload
    if conversion_criticality <= 0 and conversion_payload is not None:
        conversion_criticality = conversion_payload
    if revenue_criticality <= 0 and revenue_payload is not None:
        revenue_criticality = revenue_payload

    # max_signal is used for general non-baseline signal detection.
    # For baseline zero validation, do NOT count normal-state evidence such as
    # traffic_preservation_score=1.0. Also, business_kpi_distortion_score may be
    # present as a derived business-readiness value during transition, but it is
    # only an anomaly signal when paired with non-zero criticality/impact evidence.
    max_signal = max(
        baseline,
        statistical,
        propagation,
        impact,
        concentration,
        criticality,
        event_criticality,
        conversion_criticality,
        revenue_criticality,
        business_kpi_distortion,
        traffic_preservation,
    )
    baseline_anomaly_signal = max(
        baseline,
        statistical,
        propagation,
        impact,
        concentration,
        criticality,
        event_criticality,
        conversion_criticality,
        revenue_criticality,
        business_kpi_distortion if max(criticality, event_criticality, conversion_criticality, impact, concentration) > 0.08 else 0.0,
    )

    print("[AUTHORITY_EVIDENCE_LAYER]")
    print(f"profile_id={args.profile_id}")
    print(f"target_date={args.target_date}")
    print(f"scenario_name={args.scenario_name}")
    print(f"run_id={args.run_id}")
    print(f"source_gen_run_id={args.source_gen_run_id}")
    print(f"evidence_layer_version={version}")
    print(f"evidence_ready={ready}")
    print(f"baseline_evidence_score={baseline:.6f}")
    print(f"statistical_evidence_group_score={statistical:.6f}")
    print(f"propagation_evidence_score={propagation:.6f}")
    print(f"impact_evidence_score={impact:.6f}")
    print(f"concentration_evidence_score={concentration:.6f}")
    print(f"criticality_evidence_score={criticality:.6f}")
    print(f"event_criticality_score={event_criticality:.6f}")
    print(f"conversion_criticality_score={conversion_criticality:.6f}")
    print(f"revenue_criticality_score={revenue_criticality:.6f}")
    print(f"business_kpi_distortion_score={business_kpi_distortion:.6f}")
    print(f"traffic_preservation_score={traffic_preservation:.6f}")
    print(f"evidence_summary={row.get('evidence_summary') or ''}")

    # Phase4-D extends the same Authority Evidence Layer contract with
    # Evidence Primitive + Failure Mechanism outputs. Keep backward
    # compatibility with the original Phase4-B validator contract while
    # allowing the new phase4d version emitted by build_v05_reliability_analysis.R.
    allowed_version_prefixes = (
        "v05_phase4b_step1_evidence_layer",
        "v05_phase4d_evidence_primitive_mechanism",
    )
    if not version.startswith(allowed_version_prefixes):
        failures.append(f"unexpected evidence_layer_version={version}")
    if ready != 1:
        failures.append("evidence_ready must be 1")
    for key, val in {
        "baseline_evidence_score": baseline,
        "statistical_evidence_group_score": statistical,
        "propagation_evidence_score": propagation,
        "impact_evidence_score": impact,
        "concentration_evidence_score": concentration,
        "criticality_evidence_score": criticality,
        "event_criticality_score": event_criticality,
        "conversion_criticality_score": conversion_criticality,
        "revenue_criticality_score": revenue_criticality,
        "business_kpi_distortion_score": business_kpi_distortion,
        "traffic_preservation_score": traffic_preservation,
    }.items():
        if val < -1e-9 or val > 1 + 1e-9:
            failures.append(f"{key} out of [0,1] range: {val}")

    if not payload_text:
        failures.append("evidence_payload_json missing")
    elif payload_error:
        failures.append(f"evidence_payload_json invalid JSON: {payload_error}")
    else:
        if payload.get("layer") != "AUTHORITY_EVIDENCE_LAYER":
            failures.append("evidence_payload_json.layer mismatch")
        if payload.get("case_specific_features_disallowed") is not True:
            failures.append("case-specific features must be disallowed in authority evidence layer")
        if payload.get("obs_is_reference_not_authority") is not True:
            failures.append("OBS must remain reference evidence, not authority evidence")
        groups = payload.get("evidence_groups", {})
        missing_groups = sorted(REQUIRED_GROUPS - set(groups.keys())) if isinstance(groups, dict) else sorted(REQUIRED_GROUPS)
        if missing_groups:
            failures.append("missing evidence groups: " + ",".join(missing_groups))
        nxt = payload.get("next_step_contract", {})
        if nxt.get("pattern_layer_required") is not True:
            failures.append("pattern_layer_required must be true")
        if nxt.get("risk_layer_must_not_consume_case_specific_dimensions_directly") is not True:
            failures.append("risk layer must not consume case-specific dimensions directly")

    if baseline_like and args.allow_baseline_zero:
        if baseline_anomaly_signal > 0.08:
            failures.append(f"baseline evidence should be near zero: baseline_anomaly_signal={baseline_anomaly_signal:.6f}")
    elif args.require_evidence_signal and max_signal < args.min_evidence_signal:
        failures.append(f"evidence signal too low: {max_signal:.6f} < {args.min_evidence_signal:.6f}")
    if args.require_concentration and concentration < args.min_concentration:
        failures.append(f"concentration_evidence_score too low: {concentration:.6f} < {args.min_concentration:.6f}")
    if args.require_criticality and criticality < args.min_criticality:
        failures.append(f"criticality_evidence_score too low: {criticality:.6f} < {args.min_criticality:.6f}")
    if args.require_business_kpi_distortion and business_kpi_distortion < args.min_business_kpi_distortion:
        failures.append(f"business_kpi_distortion_score too low: {business_kpi_distortion:.6f} < {args.min_business_kpi_distortion:.6f}")
    if args.require_traffic_preservation and traffic_preservation < args.min_traffic_preservation:
        failures.append(f"traffic_preservation_score too low: {traffic_preservation:.6f} < {args.min_traffic_preservation:.6f}")

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_authority_evidence_layer passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
