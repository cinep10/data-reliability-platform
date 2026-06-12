#!/usr/bin/env python3
"""Validate that v0.5 reliability analysis reflects reconciliation statistical evidence.

This validator intentionally separates raw statistical evidence from the effective
risk contribution. Baseline runs may suppress the effective score to avoid false
positive risk, but they must still preserve/refect the raw evidence interface so
we can prove build_v05_reliability_analysis.R actually read
v05_baseline_science_statistical_evidence_day domain=reconciliation_measurement.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", default="")
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", default="baseline")
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--baseline-window", default="30d")
    p.add_argument("--allow-baseline-suppression", action="store_true")
    p.add_argument("--tolerance", type=float, default=1e-9)
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
        return float(row.get(key) if row.get(key) is not None else default)
    except Exception:
        return default


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    baseline_like = args.scenario_name.lower() in {"baseline", "normal", "stable"}
    con = connect(args)
    try:
        with con.cursor() as cur:
            if not table_exists(cur, "v05_baseline_science_statistical_evidence_day"):
                print("[FAIL] missing v05_baseline_science_statistical_evidence_day")
                return 1
            if not table_exists(cur, "reliability_analysis_result_day_v05"):
                print("[FAIL] missing reliability_analysis_result_day_v05")
                return 1

            evidence = fetchone(
                cur,
                """
                SELECT COUNT(*) AS row_count,
                       MAX(COALESCE(statistical_score,0)) AS raw_score,
                       MAX(ABS(COALESCE(z_score,0))) AS max_z,
                       MAX(COALESCE(historical_percentile,0)) AS max_percentile,
                       SUM(CASE WHEN control_limit_breach=1 THEN 1 ELSE 0 END) AS breach_count,
                       MIN(COALESCE(sample_days,0)) AS min_sample_days,
                       MAX(COALESCE(sample_days,0)) AS max_sample_days
                FROM v05_baseline_science_statistical_evidence_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s AND baseline_window=%s
                  AND evidence_domain='reconciliation_measurement'
                """,
                (
                    args.profile_id,
                    args.target_date,
                    args.scenario_name,
                    args.run_id,
                    args.source_gen_run_id,
                    args.baseline_window,
                ),
            )
            ev_count = int(evidence.get("row_count") or 0)
            ev_raw = fval(evidence, "raw_score")
            ev_max_z = fval(evidence, "max_z")
            ev_pct = fval(evidence, "max_percentile")
            ev_breach = int(evidence.get("breach_count") or 0)
            ev_min_days = int(evidence.get("min_sample_days") or 0)
            ev_max_days = int(evidence.get("max_sample_days") or 0)
            print(
                f"[EVIDENCE] domain=reconciliation_measurement rows={ev_count} "
                f"raw_score={ev_raw:.6f} max_z={ev_max_z:.6f} "
                f"max_percentile={ev_pct:.4f} breach={ev_breach} "
                f"sample_days={ev_min_days}..{ev_max_days}"
            )
            if ev_count <= 0:
                failures.append("no reconciliation_measurement statistical evidence rows")

            rel_cols = columns(cur, "reliability_analysis_result_day_v05")
            wanted = {
                "statistical_evidence_score",
                "statistical_evidence_raw_score",
                "statistical_evidence_effective_score",
                "statistical_evidence_reflected",
                "statistical_evidence_row_count",
                "statistical_evidence_min_sample_days",
                "statistical_evidence_max_sample_days",
                "analysis_payload_json",
            }
            missing_cols = sorted(wanted - rel_cols)
            if missing_cols:
                failures.append("missing reliability statistical interface columns: " + ",".join(missing_cols))

            rel = fetchone(
                cur,
                """
                SELECT *
                FROM reliability_analysis_result_day_v05
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s
                LIMIT 1
                """,
                (
                    args.profile_id,
                    args.target_date,
                    args.scenario_name,
                    args.run_id,
                    args.source_gen_run_id,
                ),
            )
            if not rel:
                failures.append("missing reliability_analysis_result_day_v05 row")
            else:
                raw = fval(rel, "statistical_evidence_raw_score", fval(rel, "statistical_evidence_score"))
                effective = fval(rel, "statistical_evidence_effective_score", fval(rel, "statistical_evidence_score"))
                legacy = fval(rel, "statistical_evidence_score")
                reflected = int(rel.get("statistical_evidence_reflected") or 0)
                row_count = int(rel.get("statistical_evidence_row_count") or 0)
                min_days = int(rel.get("statistical_evidence_min_sample_days") or 0)
                max_days = int(rel.get("statistical_evidence_max_sample_days") or 0)
                sig = str(rel.get("statistical_significance") or "")
                print(
                    f"[RELIABILITY] reflected={reflected} rows={row_count} "
                    f"raw={raw:.6f} effective={effective:.6f} legacy_stat={legacy:.6f} "
                    f"sample_days={min_days}..{max_days} sig={sig}"
                )
                if reflected != 1:
                    failures.append("reliability analysis did not mark statistical evidence as reflected")
                if row_count != ev_count:
                    failures.append(f"reliability evidence row_count mismatch: {row_count} != {ev_count}")
                if abs(raw - ev_raw) > args.tolerance:
                    failures.append(f"raw statistical score mismatch: reliability={raw} evidence={ev_raw}")
                if min_days != ev_min_days or max_days != ev_max_days:
                    failures.append(
                        f"sample_days mismatch: reliability={min_days}..{max_days} evidence={ev_min_days}..{ev_max_days}"
                    )
                if baseline_like:
                    if effective != 0 and args.allow_baseline_suppression:
                        failures.append("baseline-like run should suppress effective statistical contribution to zero")
                    elif not args.allow_baseline_suppression and ev_raw > args.tolerance and effective == 0:
                        failures.append("effective score is suppressed; pass --allow-baseline-suppression for baseline runs")
                elif abs(effective - ev_raw) > args.tolerance:
                    failures.append(f"non-baseline effective score should equal raw score: {effective} != {ev_raw}")

                payload_text = rel.get("analysis_payload_json") or ""
                if payload_text:
                    try:
                        payload = json.loads(payload_text)
                        block = payload.get("baseline_science_statistical_evidence", {})
                        if block.get("domain") != "reconciliation_measurement":
                            failures.append("payload baseline_science_statistical_evidence.domain mismatch")
                        if block.get("uses_observability_results") is not False:
                            failures.append("v0.5 reliability payload should state uses_observability_results=false")
                    except Exception as exc:
                        failures.append(f"analysis_payload_json is not valid JSON: {exc}")
                else:
                    failures.append("analysis_payload_json missing")
    finally:
        con.close()

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_reliability_statistical_evidence_interface passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
