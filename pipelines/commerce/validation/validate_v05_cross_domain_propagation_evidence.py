#!/usr/bin/env python3
"""Validate v0.5 Cross-domain Propagation Evidence."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import pymysql


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


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(cur.fetchone()["n"] or 0) > 0



def table_columns(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}

def parse_domains(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    if isinstance(parsed, dict):
        return [str(x) for x in parsed.values()]
    return []


def main() -> int:
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
    p.add_argument("--require-propagation", action="store_true")
    p.add_argument("--min-propagation", type=float, default=0.10)
    p.add_argument("--min-confidence", type=float, default=0.30)
    p.add_argument("--min-affected-domains", type=int, default=1)
    p.add_argument("--allow-baseline-no-propagation", action="store_true")
    args = p.parse_args()

    failures: list[str] = []
    with connect(args) as con:
        with con.cursor() as cur:
            if not table_exists(cur, "v05_cross_domain_propagation_evidence_day"):
                print("[FAIL] missing v05_cross_domain_propagation_evidence_day")
                return 1
            cur.execute(
                """
                SELECT *
                FROM v05_cross_domain_propagation_evidence_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND run_id=%s AND source_gen_run_id=%s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.source_gen_run_id),
            )
            row = cur.fetchone()
            if not row:
                print("[FAIL] no cross-domain propagation evidence row")
                return 1

            domains = parse_domains(row.get("affected_domains"))
            propagation = float(row.get("propagation_strength") or 0)
            confidence = float(row.get("reconciliation_confidence") or 0)
            affected_count = int(row.get("affected_domain_count") or 0)
            level = row.get("propagation_level") or "stable"
            path = row.get("dominant_propagation_path") or ""

            print("[CROSS_DOMAIN_PROPAGATION]")
            print(f"profile_id={args.profile_id}")
            print(f"target_date={args.target_date}")
            print(f"scenario_name={args.scenario_name}")
            print(f"run_id={args.run_id}")
            print(f"source_gen_run_id={args.source_gen_run_id}")
            print(f"affected_domains={domains}")
            print(f"affected_domain_count={affected_count}")
            print(f"propagation_strength={propagation:.6f}")
            print(f"propagation_level={level}")
            print(f"reconciliation_confidence={confidence:.6f}")
            print(f"dominant_propagation_path={path}")

            baseline_like = args.scenario_name.lower() in {"baseline", "normal", "stable"}
            if baseline_like and args.allow_baseline_no_propagation:
                if propagation > 0.08:
                    failures.append(f"baseline propagation should be near zero: {propagation:.6f}")
            elif args.require_propagation:
                if propagation < args.min_propagation:
                    failures.append(f"propagation too low: {propagation:.6f} < {args.min_propagation:.6f}")
                if confidence < args.min_confidence:
                    failures.append(f"reconciliation confidence too low: {confidence:.6f} < {args.min_confidence:.6f}")
                if affected_count < args.min_affected_domains:
                    failures.append(f"affected domains too few: {affected_count} < {args.min_affected_domains}")

            # Optional interface check: reliability analysis should be able to reflect the row after STEP 6.
            if table_exists(cur, "reliability_analysis_result_day_v05"):
                rel_cols = table_columns(cur, "reliability_analysis_result_day_v05")
                required = {"affected_domain_count", "cross_domain_propagation_strength", "reconciliation_confidence", "dominant_propagation_path"}
                if required.issubset(rel_cols):
                    cur.execute(
                        """
                        SELECT affected_domain_count,
                               cross_domain_propagation_strength,
                               reconciliation_confidence,
                               dominant_propagation_path
                        FROM reliability_analysis_result_day_v05
                        WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                          AND run_id=%s AND source_gen_run_id=%s
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.source_gen_run_id),
                    )
                    rel = cur.fetchone()
                    if rel:
                        reflected = rel.get("cross_domain_propagation_strength") is not None
                        print(
                            "[RELIABILITY_REFLECTION] "
                            f"reflected={int(reflected)} "
                            f"propagation={float(rel.get('cross_domain_propagation_strength') or 0):.6f} "
                            f"confidence={float(rel.get('reconciliation_confidence') or 0):.6f} "
                            f"affected_domain_count={int(rel.get('affected_domain_count') or 0)}"
                        )
                else:
                    print("[INFO] reliability_analysis_result_day_v05 propagation columns not yet present; reflection check skipped")

    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        return 1
    print("[OK] validate_v05_cross_domain_propagation_evidence passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
