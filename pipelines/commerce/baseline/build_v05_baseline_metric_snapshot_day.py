#!/usr/bin/env python3
from __future__ import annotations

import argparse
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build v0.5 baseline metric snapshots from baseline scenario history. Schema-aware version."
    )
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", default="")
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--baseline-window", default="30d")
    p.add_argument("--baseline-scenario", default="baseline")
    p.add_argument("--include-target-date", action="store_true")
    p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()


def conn(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def days_from_window(w: str) -> int:
    return int(w[:-1]) if w.endswith("d") and w[:-1].isdigit() else 30


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(cur.fetchone()["c"] or 0) > 0


def table_cols(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def first_col(cols: set[str], candidates: Sequence[str]) -> Optional[str]:
    for c in candidates:
        if c in cols:
            return c
    return None


def percentile(vals: List[float], p: float) -> Optional[float]:
    if not vals:
        return None
    vals = sorted(vals)
    k = (len(vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    return vals[f] if f == c else vals[f] * (c - k) + vals[c] * (k - f)


def stats(vals: Iterable[Any]) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float], int]:
    out: List[float] = []
    for v in vals:
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        out.append(fv)
    if not out:
        return (None, None, None, None, None, 0)
    return (
        sum(out) / len(out),
        statistics.pstdev(out) if len(out) > 1 else 0.0,
        percentile(out, 0.50),
        percentile(out, 0.95),
        percentile(out, 0.99),
        len(out),
    )


def delete_metric(cur, a: argparse.Namespace, scope: str, name: str, dimension_key: str, dimension_value: str) -> None:
    cur.execute(
        """
        DELETE FROM v05_baseline_metric_snapshot_day
        WHERE profile_id=%s AND target_date=%s AND baseline_window=%s
          AND baseline_type='calendar_baseline'
          AND metric_scope=%s AND metric_name=%s
          AND dimension_key=%s AND dimension_value=%s
        """,
        (a.profile_id, a.target_date, a.baseline_window, scope, name, dimension_key, dimension_value),
    )


def put(
    cur,
    a: argparse.Namespace,
    scope: str,
    name: str,
    values: Iterable[Any],
    dimension_key: str = "all",
    dimension_value: str = "all",
    source_table: Optional[str] = None,
    note: Optional[str] = None,
) -> None:
    avg, std, p50, p95, p99, n = stats(values)
    delete_metric(cur, a, scope, name, dimension_key, dimension_value)
    cur.execute(
        """
        INSERT INTO v05_baseline_metric_snapshot_day
        (profile_id,target_date,baseline_window,baseline_type,metric_scope,metric_name,dimension_key,dimension_value,
         metric_value_avg,metric_value_std,metric_value_p50,metric_value_p95,metric_value_p99,sample_days,source_scenario,source_table,source_note)
        VALUES (%s,%s,%s,'calendar_baseline',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            a.profile_id,
            a.target_date,
            a.baseline_window,
            scope,
            name,
            dimension_key,
            dimension_value,
            avg,
            std,
            p50,
            p95,
            p99,
            n,
            a.baseline_scenario,
            source_table,
            note,
        ),
    )


def date_col(cols: set[str]) -> Optional[str]:
    return first_col(cols, ("dt", "target_date", "event_date", "date"))


def select_rows(
    cur,
    table: str,
    cols_to_select: Sequence[str],
    a: argparse.Namespace,
    start: str,
    end: str,
    scenario_required: bool = True,
) -> List[Dict[str, Any]]:
    cols = table_cols(cur, table)
    dcol = date_col(cols)
    if not dcol:
        return []
    select_cols = [dcol] + [c for c in cols_to_select if c in cols]
    if len(select_cols) <= 1:
        return []
    where = ["profile_id=%s", f"{dcol} BETWEEN %s AND %s"]
    params: List[Any] = [a.profile_id, start, end]
    if scenario_required and "scenario_name" in cols:
        where.append("scenario_name=%s")
        params.append(a.baseline_scenario)
    sql = f"SELECT {','.join(select_cols)} FROM {table} WHERE {' AND '.join(where)}"
    cur.execute(sql, tuple(params))
    return cur.fetchall()


def build_from_measurement_batch(cur, a: argparse.Namespace, start: str, end: str) -> int:
    table = "measurement_batch_day"
    if not table_exists(cur, table):
        return 0
    cols = table_cols(cur, table)
    aliases = {
        "event_count": ("event_count", "semantic_event_count", "batch_event_count", "total_event_count"),
        "pv": ("pv", "pv_count", "pageview_count", "page_view_count", "pageviews"),
        "uv": ("uv", "uv_count", "unique_visitor_count", "visitor_count", "unique_visitors"),
        "visit": ("visit", "visit_count", "session_count", "visits", "sessions"),
        "conversion_rate": ("conversion_rate",),
        "mapping_coverage": ("mapping_coverage",),
        "estimated_missing_rate": ("estimated_missing_rate",),
        "collector_capture_rate": ("collector_capture_rate",),
    }
    selected: Dict[str, str] = {}
    for metric, candidates in aliases.items():
        c = first_col(cols, candidates)
        if c:
            selected[metric] = c
    rows = select_rows(cur, table, list(selected.values()), a, start, end, scenario_required=True)
    for metric, col in selected.items():
        scope = "behavior_volume" if metric in {"event_count", "pv", "uv", "visit"} else "behavior_funnel"
        put(
            cur,
            a,
            scope,
            metric,
            [r.get(col) for r in rows],
            source_table=table,
            note=f"schema-aware column={col}",
        )
    return len(selected)


def build_from_batch_behavior(cur, a: argparse.Namespace, start: str, end: str) -> int:
    table = "batch_behavior_measurement_day"
    if not table_exists(cur, table):
        return 0
    cols = table_cols(cur, table)
    metrics = [
        "conversion_rate",
        "pv_per_uv",
        "pv_per_visit",
        "collector_capture_rate",
        "estimated_missing_rate",
        "visit_per_uv",
    ]
    selected = [m for m in metrics if m in cols]
    rows = select_rows(cur, table, selected, a, start, end, scenario_required=True)
    for metric in selected:
        put(cur, a, "behavior_funnel", metric, [r.get(metric) for r in rows], source_table=table)
    return len(selected)


def build_from_observability(cur, a: argparse.Namespace, start: str, end: str) -> int:
    table = "v05_observability_measurement_day"
    if not table_exists(cur, table):
        return 0
    cols = table_cols(cur, table)
    aliases = {
        "collection_gap_rate": ("collection_gap_rate",),
        "web_to_canonical_gap_rate": ("web_to_canonical_gap_rate", "canonical_gap_rate"),
        "uv_gap_rate": ("uv_gap_rate",),
        "web_hits": ("web_hits",),
        "wc_hits": ("wc_hits",),
        "canonical_behavior_events": ("canonical_behavior_events",),
    }
    selected: Dict[str, str] = {}
    for metric, candidates in aliases.items():
        c = first_col(cols, candidates)
        if c:
            selected[metric] = c
    rows = select_rows(cur, table, list(selected.values()), a, start, end, scenario_required=True)
    for metric, col in selected.items():
        put(
            cur,
            a,
            "observability",
            metric,
            [r.get(col) for r in rows],
            source_table=table,
            note=f"schema-aware column={col}",
        )
    return len(selected)


def build_reference_row(cur, a: argparse.Namespace, snapshot_date: str, available: int, confidence: str, note: str) -> None:
    cur.execute(
        """
        DELETE FROM v05_baseline_reference_run_day
        WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
          AND baseline_mode='temporal_baseline' AND baseline_window=%s
        """,
        (a.profile_id, a.target_date, a.baseline_scenario, a.baseline_window),
    )
    cur.execute(
        """
        INSERT INTO v05_baseline_reference_run_day
        (profile_id,target_date,scenario_name,baseline_mode,baseline_window,baseline_available,baseline_snapshot_date,fallback_policy,analysis_confidence)
        VALUES (%s,%s,%s,'temporal_baseline',%s,%s,%s,%s,%s)
        """,
        (
            a.profile_id,
            a.target_date,
            a.baseline_scenario,
            a.baseline_window,
            available,
            snapshot_date,
            note,
            confidence,
        ),
    )


def main() -> None:
    a = parse_args()
    n = days_from_window(a.baseline_window)
    target = datetime.strptime(a.target_date, "%Y-%m-%d").date()
    start = target - timedelta(days=n)
    end = target if a.include_target_date else target - timedelta(days=1)
    start_s = start.isoformat()
    end_s = end.isoformat()

    with conn(a) as c:
        cur = c.cursor()
        if a.truncate_target:
            cur.execute(
                "DELETE FROM v05_baseline_metric_snapshot_day WHERE profile_id=%s AND target_date=%s AND baseline_window=%s",
                (a.profile_id, a.target_date, a.baseline_window),
            )

        metric_groups = [
            build_from_measurement_batch(cur, a, start_s, end_s),
            build_from_batch_behavior(cur, a, start_s, end_s),
            build_from_observability(cur, a, start_s, end_s),
        ]
        cur.execute(
            """
            SELECT COALESCE(SUM(sample_days),0) AS sample_days, COUNT(*) AS metric_rows
            FROM v05_baseline_metric_snapshot_day
            WHERE profile_id=%s AND target_date=%s AND baseline_window=%s
            """,
            (a.profile_id, a.target_date, a.baseline_window),
        )
        summary = cur.fetchone() or {}
        sample_days = int(summary.get("sample_days") or 0)
        metric_rows = int(summary.get("metric_rows") or 0)
        available = 1 if sample_days > 0 else 0
        confidence = "medium" if available else "low"
        fallback_policy = "no_current_fallback" if available else "baseline_missing_review"
        build_reference_row(cur, a, end_s, available, confidence, fallback_policy)

    print(
        f"[OK] build_v05_baseline_metric_snapshot_day target={a.target_date} window={a.baseline_window} "
        f"range={start_s}..{end_s} metrics={metric_rows} sample_days={sample_days} available={available} "
        f"sources={metric_groups}"
    )


if __name__ == "__main__":
    main()
