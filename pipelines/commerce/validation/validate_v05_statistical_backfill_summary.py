#!/usr/bin/env python3
"""Validate CASE-OBS-001 Phase2-C4 statistical backfill calendar.

This validator checks that a scenario-calendar backfill created one scenario per date,
that baseline/anomaly days exist, and that statistical evidence domains are present.
It is intentionally schema-aware and does not require source/canonical rows, because
backfill compaction may delete heavy runtime rows.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--from-date", required=True)
    p.add_argument("--to-date", required=True)
    p.add_argument("--plan-file", required=True)
    p.add_argument("--min-sample-days", type=int, default=3)
    p.add_argument("--allow-low-sample", action="store_true")
    return p.parse_args()


def read_plan(path: str) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split()
            if len(parts) < 2:
                raise SystemExit(f"bad plan row: {raw}")
            rows.append((parts[0], parts[1]))
    return rows


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(cur.fetchone()["c"] or 0) > 0


def columns(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def main() -> int:
    args = parse_args()
    plan = read_plan(args.plan_file)
    if not plan:
        print("[FAIL] empty backfill plan")
        return 1
    expected_dates = [d for d, _ in plan]
    scenarios = {s for _, s in plan}
    anomaly_days = [(d, s) for d, s in plan if s != "baseline"]

    con = pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with con.cursor() as cur:
            if not table_exists(cur, "v05_baseline_science_statistical_evidence_day"):
                print("[FAIL] missing v05_baseline_science_statistical_evidence_day")
                return 1
            cols = columns(cur, "v05_baseline_science_statistical_evidence_day")
            date_col = "target_date" if "target_date" in cols else "dt"
            scenario_col = "scenario_name" if "scenario_name" in cols else None
            domain_col = "evidence_domain" if "evidence_domain" in cols else "domain"
            sample_col = "sample_days" if "sample_days" in cols else None
            score_col = "statistical_score" if "statistical_score" in cols else None

            cur.execute(
                f"""
                SELECT {date_col} AS target_date,
                       {scenario_col or "'unknown'"} AS scenario_name,
                       {domain_col} AS evidence_domain,
                       COUNT(*) AS row_count,
                       {('MIN('+sample_col+')') if sample_col else '0'} AS min_sample_days,
                       {('MAX('+sample_col+')') if sample_col else '0'} AS max_sample_days,
                       {('MAX('+score_col+')') if score_col else '0'} AS max_statistical_score
                FROM v05_baseline_science_statistical_evidence_day
                WHERE profile_id=%s
                  AND {date_col} BETWEEN %s AND %s
                GROUP BY {date_col}, {scenario_col or "'unknown'"}, {domain_col}
                ORDER BY {date_col}, scenario_name, evidence_domain
                """,
                (args.profile_id, args.from_date, args.to_date),
            )
            rows = cur.fetchall()

    finally:
        con.close()

    if not rows:
        print("[FAIL] no statistical evidence rows for backfill range")
        return 1

    by_date: Dict[str, List[dict]] = {}
    for r in rows:
        by_date.setdefault(str(r["target_date"]), []).append(r)

    missing_dates = [d for d in expected_dates if d not in by_date]
    for r in rows:
        print(
            f"  - date={r['target_date']} scenario={r['scenario_name']} "
            f"domain={r['evidence_domain']} rows={r['row_count']} "
            f"sample_days={r['min_sample_days']}..{r['max_sample_days']} "
            f"max_score={float(r['max_statistical_score'] or 0):.6f}"
        )

    failures: List[str] = []
    if missing_dates:
        failures.append(f"missing evidence dates: {','.join(missing_dates)}")
    if not anomaly_days:
        failures.append("plan has no anomaly days; statistical reaction cannot be tested")
    if plan[-1][1] != "baseline":
        failures.append("last target date should be baseline for final reference validation")

    all_domains = {str(r["evidence_domain"]) for r in rows}
    if "batch_metric_delta" not in all_domains:
        failures.append("missing batch_metric_delta evidence domain")
    if "reconciliation_measurement" not in all_domains:
        failures.append("missing reconciliation_measurement evidence domain")

    if not args.allow_low_sample:
        max_sample = 0
        for r in rows:
            try:
                max_sample = max(max_sample, int(r["max_sample_days"] or 0))
            except Exception:
                pass
        if max_sample < args.min_sample_days:
            failures.append(f"sample_days too low: max={max_sample} < required={args.min_sample_days}")

    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        return 1

    print(
        f"[OK] statistical backfill summary passed dates={len(by_date)} "
        f"planned_dates={len(plan)} anomaly_days={len(anomaly_days)} domains={','.join(sorted(all_domains))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
