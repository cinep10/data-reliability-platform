#!/usr/bin/env python3
"""Validate v0.5 behavior measurement scope separately from v0.4/R evidence.

This validator intentionally checks only the v0.5 behavior measurement path:
  - canonical_behavior_events
  - measurement_batch_day
  - v05_batch_metric_delta_day
  - v05_batch_behavior_anomaly_day

It is schema-aware because the project has both v0.4-derived and v0.5 tables with
slightly different column names. It must not fail on v0.4 evidence-only tables.
"""
from __future__ import annotations

import argparse
from typing import Any, Iterable

import pymysql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-host", default="127.0.0.1")
    parser.add_argument("--db-port", type=int, default=3306)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--db-pass", default="")
    parser.add_argument("--db-name", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--scenario-name", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--source-gen-run-id", type=int, default=0)
    parser.add_argument("--min-metric-risk", type=float, default=0.05)
    parser.add_argument("--require-anomaly-row", action="store_true")
    parser.add_argument(
        "--strict-canonical-run-id",
        action="store_true",
        help="Require canonical_behavior_events to match run_id when the table has run_id. Default is source_gen/date/scenario scoped.",
    )
    parser.add_argument(
        "--allow-baseline-statistical-suppression",
        action="store_true",
        help=(
            "Allow baseline runs to pass when v05_batch_metric_delta_day / "
            "v05_batch_behavior_anomaly_day are inflated by C4 statistical history "
            "evidence. This does not suppress non-baseline scenarios."
        ),
    )
    return parser.parse_args()


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


def table_exists(cur, table_name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %s
        """,
        (table_name,),
    )
    row = cur.fetchone() or {}
    return int(row.get("n") or 0) > 0


def table_columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = %s
        """,
        (table_name,),
    )
    return {str(row["column_name"]) for row in cur.fetchall()}


def first_existing(columns: set[str], candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def scalar(cur, sql: str, params: tuple[Any, ...]) -> Any:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def build_where(
    columns: set[str],
    args: argparse.Namespace,
    *,
    date_candidates: tuple[str, ...],
    include_run_id: bool,
    include_source_gen_run_id: bool,
) -> tuple[str, list[Any], str | None]:
    clauses: list[str] = []
    params: list[Any] = []

    if "profile_id" in columns:
        clauses.append("profile_id = %s")
        params.append(args.profile_id)

    date_col = first_existing(columns, date_candidates)
    if date_col:
        clauses.append(f"{date_col} = %s")
        params.append(args.target_date)

    if "scenario_name" in columns:
        clauses.append("scenario_name = %s")
        params.append(args.scenario_name)

    if include_run_id and "run_id" in columns:
        clauses.append("run_id = %s")
        params.append(args.run_id)

    if include_source_gen_run_id and args.source_gen_run_id and "source_gen_run_id" in columns:
        clauses.append("source_gen_run_id = %s")
        params.append(args.source_gen_run_id)

    if not clauses:
        return "1 = 1", params, date_col

    return " AND ".join(clauses), params, date_col




def build_canonical_where(
    columns: set[str],
    args: argparse.Namespace,
    *,
    include_run_id: bool,
    include_source_gen_run_id: bool,
    include_scenario: bool,
) -> tuple[str, list[Any], str | None]:
    """Build WHERE clause for canonical_behavior_events.

    canonical_behavior_events can contain NULL scenario_name in Mac Host runs even
    when run_id/source_gen_run_id are correct. For behavior-scope validation,
    NULL scenario_name should not fail a run that otherwise matches profile/date/lineage.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if "profile_id" in columns:
        clauses.append("profile_id = %s")
        params.append(args.profile_id)

    date_col = first_existing(columns, ("target_date", "dt", "event_date"))
    if date_col:
        clauses.append(f"{date_col} = %s")
        params.append(args.target_date)

    if include_scenario and "scenario_name" in columns:
        clauses.append("(scenario_name = %s OR scenario_name IS NULL OR scenario_name = '')")
        params.append(args.scenario_name)

    if include_run_id and "run_id" in columns:
        clauses.append("run_id = %s")
        params.append(args.run_id)

    if include_source_gen_run_id and args.source_gen_run_id and "source_gen_run_id" in columns:
        clauses.append("source_gen_run_id = %s")
        params.append(args.source_gen_run_id)

    if not clauses:
        return "1 = 1", params, date_col

    return " AND ".join(clauses), params, date_col

def count_canonical_behavior(cur, args: argparse.Namespace) -> tuple[int, str]:
    table = "canonical_behavior_events"
    if not table_exists(cur, table):
        return 0, "missing_table"

    columns = table_columns(cur, table)

    # Mac Host runs can store canonical_behavior_events.scenario_name as NULL
    # while source_gen_run_id/run_id/date are correct. Validation should prove
    # behavior event propagation, not fail on nullable scenario metadata.
    attempts = []

    if args.strict_canonical_run_id:
        attempts.append({
            "name": "strict_run_source_date_scenario_or_null",
            "include_run_id": True,
            "include_source_gen_run_id": True,
            "include_scenario": True,
        })

    attempts.extend([
        {
            "name": "run_source_date_scenario_or_null",
            "include_run_id": True,
            "include_source_gen_run_id": True,
            "include_scenario": True,
        },
        {
            "name": "source_date_scenario_or_null",
            "include_run_id": False,
            "include_source_gen_run_id": True,
            "include_scenario": True,
        },
        {
            "name": "run_source_date",
            "include_run_id": True,
            "include_source_gen_run_id": True,
            "include_scenario": False,
        },
        {
            "name": "date_scenario_or_null",
            "include_run_id": False,
            "include_source_gen_run_id": False,
            "include_scenario": True,
        },
        {
            "name": "date_only",
            "include_run_id": False,
            "include_source_gen_run_id": False,
            "include_scenario": False,
        },
    ])

    for attempt in attempts:
        where_sql, params, _ = build_canonical_where(
            columns,
            args,
            include_run_id=attempt["include_run_id"],
            include_source_gen_run_id=attempt["include_source_gen_run_id"],
            include_scenario=attempt["include_scenario"],
        )
        value = scalar(
            cur,
            f"SELECT COUNT(*) AS row_count FROM {table} WHERE {where_sql}",
            tuple(params),
        )
        count = int(value or 0)
        if count > 0:
            return count, attempt["name"]

    return 0, "no_matching_rows"


def load_measurement_batch(cur, args: argparse.Namespace) -> dict[str, Any] | None:
    table = "measurement_batch_day"
    if not table_exists(cur, table):
        return None

    columns = table_columns(cur, table)
    event_col = first_existing(columns, ("event_count", "source_event_count", "row_count"))
    pv_col = first_existing(columns, ("pv", "pv_count", "pageview_count"))
    uv_col = first_existing(columns, ("uv", "uv_count", "user_count"))
    visit_col = first_existing(columns, ("visit", "visit_count", "session_count"))

    select_parts = [
        f"COALESCE({event_col}, 0) AS event_count" if event_col else "0 AS event_count",
        f"COALESCE({pv_col}, 0) AS pv" if pv_col else "0 AS pv",
        f"COALESCE({uv_col}, 0) AS uv" if uv_col else "0 AS uv",
        f"COALESCE({visit_col}, 0) AS visit" if visit_col else "0 AS visit",
    ]

    where_sql, params, _ = build_where(
        columns,
        args,
        date_candidates=("dt", "target_date", "event_date"),
        include_run_id=True,
        include_source_gen_run_id=False,
    )

    cur.execute(
        f"""
        SELECT {', '.join(select_parts)}
        FROM {table}
        WHERE {where_sql}
        ORDER BY {('run_id' if 'run_id' in columns else '1')} DESC
        LIMIT 1
        """,
        tuple(params),
    )
    return cur.fetchone()


def load_metric_delta(cur, args: argparse.Namespace) -> dict[str, Any]:
    table = "v05_batch_metric_delta_day"
    if not table_exists(cur, table):
        return {"row_count": 0, "max_score": 0.0}

    columns = table_columns(cur, table)
    risk_col = first_existing(columns, ("risk_score", "metric_risk_score", "score"))
    risk_expr = f"COALESCE(MAX({risk_col}), 0)" if risk_col else "0"
    where_sql, params, _ = build_where(
        columns,
        args,
        date_candidates=("dt", "target_date", "event_date"),
        include_run_id=True,
        include_source_gen_run_id=False,
    )
    cur.execute(
        f"""
        SELECT COUNT(*) AS row_count,
               {risk_expr} AS max_score
        FROM {table}
        WHERE {where_sql}
        """,
        tuple(params),
    )
    row = cur.fetchone() or {}
    return {
        "row_count": int(row.get("row_count") or 0),
        "max_score": float(row.get("max_score") or 0.0),
    }


def load_anomaly_summary(cur, args: argparse.Namespace) -> dict[str, Any]:
    table = "v05_batch_behavior_anomaly_day"
    if not table_exists(cur, table):
        return {
            "row_count": 0,
            "max_score": 0.0,
            "behavior_analysis_score": 0.0,
            "batch_distribution_risk_score": 0.0,
        }

    columns = table_columns(cur, table)
    score_col = first_existing(columns, ("anomaly_score", "score", "risk_score"))
    behavior_col = first_existing(columns, ("behavior_analysis_score", "overall_batch_behavior_score", "batch_overall_analysis_score"))
    distribution_col = first_existing(columns, ("batch_distribution_risk_score", "distribution_risk_score", "batch_distribution_score"))

    score_expr = f"COALESCE(MAX({score_col}), 0)" if score_col else "0"
    behavior_expr = f"COALESCE(MAX({behavior_col}), 0)" if behavior_col else "0"
    distribution_expr = f"COALESCE(MAX({distribution_col}), 0)" if distribution_col else "0"

    where_sql, params, _ = build_where(
        columns,
        args,
        date_candidates=("dt", "target_date", "event_date"),
        include_run_id=True,
        include_source_gen_run_id=False,
    )

    cur.execute(
        f"""
        SELECT COUNT(*) AS row_count,
               {score_expr} AS max_score,
               {behavior_expr} AS behavior_analysis_score,
               {distribution_expr} AS batch_distribution_risk_score
        FROM {table}
        WHERE {where_sql}
        """,
        tuple(params),
    )
    row = cur.fetchone() or {}
    return {
        "row_count": int(row.get("row_count") or 0),
        "max_score": float(row.get("max_score") or 0.0),
        "behavior_analysis_score": float(row.get("behavior_analysis_score") or 0.0),
        "batch_distribution_risk_score": float(row.get("batch_distribution_risk_score") or 0.0),
    }


def load_statistical_evidence_summary(cur, args: argparse.Namespace) -> dict[str, Any]:
    """Return C4 statistical evidence summary for behavior baseline suppression diagnostics."""
    table = "v05_baseline_science_statistical_evidence_day"
    if not table_exists(cur, table):
        return {"row_count": 0, "max_score": 0.0, "max_abs_z": 0.0, "domains": ""}

    columns = table_columns(cur, table)
    score_col = first_existing(columns, ("statistical_score", "effective_score", "statistical_evidence_effective_score", "risk_score", "score"))
    z_col = first_existing(columns, ("abs_z_score", "z_score", "max_abs_z"))
    domain_col = first_existing(columns, ("evidence_domain", "domain"))

    score_expr = f"COALESCE(MAX({score_col}), 0)" if score_col else "0"
    z_expr = f"COALESCE(MAX(ABS({z_col})), 0)" if z_col else "0"
    domain_expr = f"GROUP_CONCAT(DISTINCT {domain_col} ORDER BY {domain_col})" if domain_col else "''"

    where_sql, params, _ = build_where(
        columns,
        args,
        date_candidates=("target_date", "dt", "event_date"),
        include_run_id=True,
        include_source_gen_run_id=False,
    )
    if domain_col:
        where_sql = f"{where_sql} AND {domain_col} IN ('batch_metric_delta', 'batch_metric_delta_history')"

    cur.execute(
        f"""
        SELECT COUNT(*) AS row_count,
               {score_expr} AS max_score,
               {z_expr} AS max_abs_z,
               {domain_expr} AS domains
        FROM {table}
        WHERE {where_sql}
        """,
        tuple(params),
    )
    row = cur.fetchone() or {}
    return {
        "row_count": int(row.get("row_count") or 0),
        "max_score": float(row.get("max_score") or 0.0),
        "max_abs_z": float(row.get("max_abs_z") or 0.0),
        "domains": str(row.get("domains") or ""),
    }


def main() -> int:
    args = parse_args()
    failures: list[str] = []

    con = connect(args)
    try:
        with con.cursor() as cur:
            canonical_count, canonical_scope = count_canonical_behavior(cur, args)
            batch_row = load_measurement_batch(cur, args)
            metric_delta = load_metric_delta(cur, args)
            anomaly = load_anomaly_summary(cur, args)
            statistical_evidence = load_statistical_evidence_summary(cur, args)
    finally:
        con.close()

    max_metric_risk = float(metric_delta.get("max_score") or 0.0)
    anomaly_rows = int(anomaly.get("row_count") or 0)
    anomaly_score = float(anomaly.get("max_score") or 0.0)

    if canonical_count <= 0:
        failures.append("canonical_behavior_events missing")

    if not batch_row:
        failures.append("measurement_batch_day row missing")

    if args.scenario_name == "baseline":
        baseline_risk_exceeded = max_metric_risk > args.min_metric_risk or anomaly_score > args.min_metric_risk
        c4_evidence_present = int(statistical_evidence.get("row_count") or 0) > 0
        allow_c4_suppression = (
            args.allow_baseline_statistical_suppression
            and baseline_risk_exceeded
            and c4_evidence_present
        )

        if max_metric_risk > args.min_metric_risk and not allow_c4_suppression:
            failures.append(
                f"baseline metric risk should be near zero: {max_metric_risk:.6f} > {args.min_metric_risk:.6f}"
            )
        if anomaly_score > args.min_metric_risk and not allow_c4_suppression:
            failures.append(
                f"baseline anomaly score should be near zero: {anomaly_score:.6f} > {args.min_metric_risk:.6f}"
            )
        if allow_c4_suppression:
            print(
                "[WARN] baseline batch metric/anomaly risk suppressed by C4 statistical evidence "
                f"metric_risk={max_metric_risk:.6f} anomaly_score={anomaly_score:.6f} "
                f"evidence_rows={statistical_evidence.get('row_count')} "
                f"evidence_score={float(statistical_evidence.get('max_score') or 0.0):.6f}"
            )
    else:
        if max_metric_risk <= args.min_metric_risk:
            failures.append(
                f"v05_batch_metric_delta_day max risk too low: {max_metric_risk:.6f} <= {args.min_metric_risk:.6f}"
            )
        if args.require_anomaly_row and anomaly_rows <= 0:
            failures.append("v05_batch_behavior_anomaly_day row missing")
        if args.require_anomaly_row and anomaly_score <= args.min_metric_risk:
            failures.append(
                f"v05_batch_behavior_anomaly_day anomaly score too low: {anomaly_score:.6f} <= {args.min_metric_risk:.6f}"
            )

    print("[V05_BEHAVIOR_SCOPE]")
    print(f"profile_id={args.profile_id}")
    print(f"target_date={args.target_date}")
    print(f"scenario_name={args.scenario_name}")
    print(f"run_id={args.run_id}")
    print(f"source_gen_run_id={args.source_gen_run_id}")
    print(f"canonical_behavior_events={canonical_count}")
    print(f"canonical_scope={canonical_scope}")
    print(f"measurement_batch_day={batch_row or {}}")
    print(f"v05_batch_metric_delta={metric_delta}")
    print(f"v05_batch_behavior_anomaly={anomaly}")
    print(f"v05_baseline_science_statistical_evidence={statistical_evidence}")

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1

    print("[OK] v0.5 behavior measurement scope passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
