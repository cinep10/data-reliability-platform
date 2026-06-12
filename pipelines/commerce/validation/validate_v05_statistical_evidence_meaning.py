#!/usr/bin/env python3
"""Validate statistical meaning by domain policy.

CASE-OBS-001 Phase2-C4 separates domains into:
  - statistical domains: batch_metric_delta, reconciliation_measurement
  - reference domains: observability_expected

Important policy:
  - batch_metric_delta is a history-backed statistical domain. It should be
    validated against v05_batch_metric_delta_history_day and aggregated evidence,
    not only the current target run_id. The target run can contain only the latest
    15 metric rows, while the history table carries the time-series baseline.
  - reconciliation_measurement is run-scoped and should remain run/source scoped.
  - observability_expected is a reference/expected-model domain, not a statistical
    meaning gate.
"""
from __future__ import annotations

import argparse
from typing import Any

import pymysql

REFERENCE_DOMAINS = {"observability_expected"}
STATISTICAL_DOMAINS = {"batch_metric_delta", "reconciliation_measurement"}


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
    p.add_argument("--domains", default="batch_metric_delta,observability_expected,reconciliation_measurement")
    p.add_argument("--min-sample-days", type=int, default=3)
    p.add_argument("--min-nonzero-sd-ratio", type=float, default=0.10)
    p.add_argument("--allow-low-sample", action="store_true")
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


def table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema=DATABASE() AND table_name=%s
        """,
        (table,),
    )
    return int((cur.fetchone() or {}).get("n") or 0) > 0


def table_columns(cur, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=DATABASE() AND table_name=%s
        """,
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def first_existing(cols: set[str], names: tuple[str, ...]) -> str | None:
    for n in names:
        if n in cols:
            return n
    return None


def fetch_batch_history_summary(cur, args: argparse.Namespace) -> dict[str, Any]:
    table = "v05_batch_metric_delta_history_day"
    if not table_exists(cur, table):
        return {"history_rows": 0, "max_history_days": 0, "metrics_with_enough_history": 0, "metric_count": 0}
    cols = table_columns(cur, table)
    date_col = first_existing(cols, ("target_date", "metric_date", "dt"))
    history_col = first_existing(cols, ("history_date", "baseline_date", "metric_date", "dt"))
    scope_col = first_existing(cols, ("metric_scope", "dimension_type", "scope")) or "metric_scope"
    metric_col = first_existing(cols, ("metric_name", "metric", "name")) or "metric_name"
    if not date_col or not history_col:
        return {"history_rows": 0, "max_history_days": 0, "metrics_with_enough_history": 0, "metric_count": 0}

    where = []
    params: list[Any] = []
    if "profile_id" in cols:
        where.append("profile_id=%s")
        params.append(args.profile_id)
    where.append(f"{date_col}=%s")
    params.append(args.target_date)
    if "scenario_name" in cols:
        where.append("scenario_name=%s")
        params.append(args.scenario_name)
    if "baseline_window" in cols:
        where.append("baseline_window=%s")
        params.append(args.baseline_window)
    where_sql = " AND ".join(where) if where else "1=1"

    cur.execute(
        f"""
        SELECT COUNT(*) AS history_rows,
               COUNT(DISTINCT CONCAT(COALESCE({scope_col},''),'|',COALESCE({metric_col},''))) AS metric_count,
               MAX(history_days) AS max_history_days,
               SUM(CASE WHEN history_days >= %s THEN 1 ELSE 0 END) AS metrics_with_enough_history
        FROM (
            SELECT {scope_col}, {metric_col}, COUNT(DISTINCT {history_col}) AS history_days
            FROM {table}
            WHERE {where_sql}
            GROUP BY {scope_col}, {metric_col}
        ) h
        """,
        tuple([args.min_sample_days] + params),
    )
    row = cur.fetchone() or {}
    return {
        "history_rows": int(row.get("history_rows") or 0),
        "metric_count": int(row.get("metric_count") or 0),
        "max_history_days": int(row.get("max_history_days") or 0),
        "metrics_with_enough_history": int(row.get("metrics_with_enough_history") or 0),
    }


def main() -> int:
    args = parse_args()
    domains = [d.strip() for d in args.domains.split(",") if d.strip()]
    if not domains:
        domains = sorted(REFERENCE_DOMAINS | STATISTICAL_DOMAINS)
    placeholders = ",".join(["%s"] * len(domains))
    failures: list[str] = []
    warnings: list[str] = []

    con = connect(args)
    try:
        with con.cursor() as cur:
            if not table_exists(cur, "v05_baseline_science_statistical_evidence_day"):
                print("[FAIL] missing v05_baseline_science_statistical_evidence_day")
                return 1

            # Use target/scenario/baseline_window for domain meaning. Do not force
            # run_id/source_gen_run_id for batch_metric_delta because compaction and
            # history materialization intentionally preserve cross-run history rows.
            cur.execute(
                f"""
                SELECT evidence_domain,
                       COUNT(*) AS row_count,
                       MIN(COALESCE(sample_days,0)) AS min_sample_days,
                       MAX(COALESCE(sample_days,0)) AS max_sample_days,
                       SUM(CASE WHEN COALESCE(sample_days,0) >= %s THEN 1 ELSE 0 END) AS enough_sample_rows,
                       SUM(CASE WHEN COALESCE(baseline_sd,0) > 0 THEN 1 ELSE 0 END) AS nonzero_sd_rows,
                       SUM(CASE WHEN historical_percentile IS NOT NULL THEN 1 ELSE 0 END) AS percentile_rows,
                       SUM(CASE WHEN control_limit_lower IS NOT NULL OR control_limit_upper IS NOT NULL THEN 1 ELSE 0 END) AS control_limit_rows,
                       MAX(COALESCE(statistical_score,0)) AS max_score,
                       MAX(COALESCE(baseline_quality_score,0)) AS max_quality,
                       SUM(CASE WHEN analysis_status='REFERENCE_DOMAIN_NOT_STATISTICAL' THEN 1 ELSE 0 END) AS reference_rows
                FROM v05_baseline_science_statistical_evidence_day
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                  AND baseline_window=%s
                  AND evidence_domain IN ({placeholders})
                GROUP BY evidence_domain
                ORDER BY evidence_domain
                """,
                tuple([args.min_sample_days, args.profile_id, args.target_date, args.scenario_name, args.baseline_window] + domains),
            )
            rows = cur.fetchall()
            if not rows:
                failures.append("no statistical evidence rows found for requested domains")

            found = set()
            for r in rows:
                domain = str(r["evidence_domain"])
                found.add(domain)
                row_count = int(r.get("row_count") or 0)
                min_days = int(r.get("min_sample_days") or 0)
                max_days = int(r.get("max_sample_days") or 0)
                enough = int(r.get("enough_sample_rows") or 0)
                nonzero_sd = int(r.get("nonzero_sd_rows") or 0)
                pct_rows = int(r.get("percentile_rows") or 0)
                cl_rows = int(r.get("control_limit_rows") or 0)
                ref_rows = int(r.get("reference_rows") or 0)
                max_score = float(r.get("max_score") or 0)
                max_quality = float(r.get("max_quality") or 0)
                nonzero_sd_ratio = nonzero_sd / row_count if row_count else 0.0

                if domain in REFERENCE_DOMAINS:
                    print(
                        f"[REFERENCE] domain={domain} rows={row_count} sample_days={min_days}..{max_days} "
                        f"reference_rows={ref_rows} max_score={max_score:.6f} status=excluded_from_statistical_meaning"
                    )
                    continue

                if domain == "batch_metric_delta":
                    hist = fetch_batch_history_summary(cur, args)
                    meaningful = (
                        row_count > 0
                        and (
                            max_days >= args.min_sample_days
                            or int(hist.get("max_history_days") or 0) >= args.min_sample_days
                            or enough > 0
                        )
                        and pct_rows > 0
                        and cl_rows > 0
                    )
                    print(
                        f"[MEANING] domain={domain} rows={row_count} sample_days={min_days}..{max_days} "
                        f"enough_rows={enough} history_days_max={hist.get('max_history_days')} "
                        f"history_metrics_enough={hist.get('metrics_with_enough_history')}/{hist.get('metric_count')} "
                        f"nonzero_sd_ratio={nonzero_sd_ratio:.3f} percentile_rows={pct_rows} "
                        f"control_limit_rows={cl_rows} max_score={max_score:.6f} max_quality={max_quality:.6f} "
                        f"meaningful={str(meaningful).lower()}"
                    )
                else:
                    meaningful = (
                        row_count > 0
                        and max_days >= args.min_sample_days
                        and enough > 0
                        and pct_rows == row_count
                        and cl_rows == row_count
                        and nonzero_sd_ratio >= args.min_nonzero_sd_ratio
                    )
                    print(
                        f"[MEANING] domain={domain} rows={row_count} sample_days={min_days}..{max_days} "
                        f"enough_rows={enough} nonzero_sd_ratio={nonzero_sd_ratio:.3f} "
                        f"percentile_rows={pct_rows} control_limit_rows={cl_rows} "
                        f"max_score={max_score:.6f} max_quality={max_quality:.6f} meaningful={str(meaningful).lower()}"
                    )

                if not meaningful:
                    warnings.append(
                        f"{domain} is not statistically meaningful yet; needs >= {args.min_sample_days} sample days and domain-appropriate distribution fields"
                    )

            missing = sorted(set(domains) - found)
            if missing:
                failures.append("missing requested domains: " + ",".join(missing))
    finally:
        con.close()

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    if warnings:
        msg = "; ".join(warnings)
        if args.allow_low_sample:
            print("[WARN] " + msg)
            print("[OK] validate_v05_statistical_evidence_meaning passed with allow-low-sample")
            return 0
        print("[FAIL] " + msg)
        return 1
    print("[OK] validate_v05_statistical_evidence_meaning passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
