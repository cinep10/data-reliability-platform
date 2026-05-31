#!/usr/bin/env python3
"""
v0.4 Batch measurement materializer.

Design intent:
- analyzer_b_v5_v04.py remains the aggregation engine.
- This script is the v0.4 Measurement interface for R analysis.
- It reads stg_ds_metric_hh_wide/stg_ds_metric_hh as the canonical wide/hourly interface,
  plus metric_value_day and quality/mapping diagnostics.
- It writes both measurement_batch_day (Phase3 common interface) and
  batch_behavior_measurement_day (batch data-analysis interface for R).
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

import pymysql


def safe_json_value(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    return v


def connect(args):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(cur.fetchone()["c"] or 0) > 0


def columns(cur, table: str) -> set[str]:
    if not table_exists(cur, table):
        return set()
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return {r["column_name"] for r in cur.fetchall()}


def scalar(cur, sql: str, params: Iterable[Any] = (), default: Any = 0) -> Any:
    try:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
        if not row:
            return default
        return next(iter(row.values()))
    except Exception:
        return default


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def inum(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(float(v))
    except Exception:
        return default


def metric_day(cur, profile_id: str, dt: str, metric_name: str) -> float:
    if not table_exists(cur, "metric_value_day"):
        return 0.0
    return fnum(
        scalar(
            cur,
            "SELECT metric_value FROM metric_value_day WHERE profile_id=%s AND dt=%s AND metric_name=%s LIMIT 1",
            (profile_id, dt, metric_name),
            0,
        )
    )


def metric_group_sum(cur, profile_id: str, dt: str, regex: str) -> float:
    if not table_exists(cur, "metric_value_day"):
        return 0.0
    return fnum(
        scalar(
            cur,
            "SELECT COALESCE(SUM(metric_value),0) FROM metric_value_day WHERE profile_id=%s AND dt=%s AND metric_name REGEXP %s",
            (profile_id, dt, regex),
            0,
        )
    )


def wide_sums(cur, profile_id: str, dt: str) -> Dict[str, float]:
    if not table_exists(cur, "stg_ds_metric_hh_wide"):
        return {"visit": 0.0, "uv": 0.0, "pageview": 0.0}
    cur.execute(
        """
        SELECT COALESCE(SUM(visit),0) AS visit,
               COALESCE(SUM(uv),0) AS uv,
               COALESCE(SUM(pageview),0) AS pageview
        FROM stg_ds_metric_hh_wide
        WHERE profile_id=%s AND dt=%s
        """,
        (profile_id, dt),
    )
    row = cur.fetchone() or {}
    return {k: fnum(row.get(k)) for k in ("visit", "uv", "pageview")}


def hh_metric_sum(cur, profile_id: str, dt: str, metric_nm: str) -> float:
    if not table_exists(cur, "stg_ds_metric_hh"):
        return 0.0
    return fnum(
        scalar(
            cur,
            "SELECT COALESCE(SUM(metric_val),0) FROM stg_ds_metric_hh WHERE profile_id=%s AND dt=%s AND metric_nm=%s",
            (profile_id, dt, metric_nm),
            0,
        )
    )


def count_stg_event_batch(cur, profile_id: str, dt: str, run_id: str) -> int:
    if not table_exists(cur, "stg_event_batch"):
        return 0
    cols = columns(cur, "stg_event_batch")
    where = ["dt=%s"]
    params: list[Any] = [dt]
    if "profile_id" in cols:
        where.append("profile_id=%s")
        params.append(profile_id)
    if run_id and "run_id" in cols:
        where.append("run_id=%s")
        params.append(run_id)
    return inum(scalar(cur, f"SELECT COUNT(*) FROM stg_event_batch WHERE {' AND '.join(where)}", params, 0))


def mapping_coverage(cur, profile_id: str, dt: str) -> tuple[float, int]:
    # Prefer mapping_coverage_day if present, but stay schema-tolerant.
    if table_exists(cur, "mapping_coverage_day"):
        cols = columns(cur, "mapping_coverage_day")
        cov_col = "mapping_coverage" if "mapping_coverage" in cols else None
        unmapped_col = "unmapped_events" if "unmapped_events" in cols else ("unmapped_event_count" if "unmapped_event_count" in cols else None)
        date_col = "dt" if "dt" in cols else None
        if cov_col and date_col:
            where = [f"{date_col}=%s"]
            params: list[Any] = [dt]
            if "profile_id" in cols:
                where.append("profile_id=%s")
                params.append(profile_id)
            cov = fnum(scalar(cur, f"SELECT COALESCE(MAX({cov_col}),0) FROM mapping_coverage_day WHERE {' AND '.join(where)}", params, 0))
            un = 0
            if unmapped_col:
                un = inum(scalar(cur, f"SELECT COALESCE(SUM({unmapped_col}),0) FROM mapping_coverage_day WHERE {' AND '.join(where)}", params, 0))
            return cov, un
    # Fallback: derive unmapped from batch_quality_diagnostic_v04 other_path rows.
    un = 0
    if table_exists(cur, "batch_quality_diagnostic_v04"):
        un = inum(scalar(cur, """
            SELECT COALESCE(SUM(row_count),0)
            FROM batch_quality_diagnostic_v04
            WHERE profile_id=%s AND dt=%s AND diagnostic_type IN ('other_path','unmapped_url','mapping_suggestion')
        """, (profile_id, dt), 0))
    event_count = count_stg_event_batch(cur, profile_id, dt, "")
    cov = 1.0 - (un / event_count) if event_count else 0.0
    return max(0.0, min(1.0, cov)), un


def quality_counts(cur, profile_id: str, dt: str) -> tuple[int, int, int, int]:
    validation_fail = 0
    quality_issue = 0
    other_count = 0
    suggestion_count = 0
    if table_exists(cur, "batch_quality_diagnostic_v04"):
        validation_fail = inum(scalar(cur, """
            SELECT COALESCE(SUM(row_count),0)
            FROM batch_quality_diagnostic_v04
            WHERE profile_id=%s AND dt=%s AND diagnostic_type='validation_non_pass'
        """, (profile_id, dt), 0))
        other_count = inum(scalar(cur, """
            SELECT COALESCE(SUM(row_count),0)
            FROM batch_quality_diagnostic_v04
            WHERE profile_id=%s AND dt=%s AND diagnostic_type='other_path'
        """, (profile_id, dt), 0))
        quality_issue = inum(scalar(cur, """
            SELECT COALESCE(SUM(row_count),0)
            FROM batch_quality_diagnostic_v04
            WHERE profile_id=%s AND dt=%s AND diagnostic_type IN ('validation_non_pass','other_path','unmapped_url','metric_review')
        """, (profile_id, dt), 0))
    if table_exists(cur, "event_mapping_suggestion"):
        suggestion_count = inum(scalar(cur, """
            SELECT COUNT(*) FROM event_mapping_suggestion
            WHERE profile_id=%s AND (dt=%s OR dt IS NULL) AND review_status='pending'
        """, (profile_id, dt), 0))
    return validation_fail, quality_issue, other_count, suggestion_count


def upsert_measurement_batch(cur, args, dt: str, vals: Dict[str, Any]) -> None:
    mb_cols = columns(cur, "measurement_batch_day")
    base = {
        "profile_id": args.profile_id,
        "dt": dt,
        "run_id": args.run_id or "",
        "scenario_name": args.scenario_name or "",
        "event_count": vals["event_count"],
        "session_count": vals["session_count"],
        "semantic_event_count": vals["batch_event_count"],
        "semantic_event_coverage": 1.0 if vals["event_count"] else 0.0,
        "schema_version_coverage": 1.0,
        "uid_coverage": 1.0,
        "pcid_coverage": 1.0,
        "funnel_start_count": vals["funnel_start_count"],
        "funnel_submit_count": vals["funnel_submit_count"],
        "conversion_rate": vals["conversion_rate"],
        "uv_count": vals["uv"],
        "pv_count": vals["pv"],
        "visit_count": vals["visit"],
        "pageview_count": vals["pageview"],
        "mapping_coverage": vals["mapping_coverage"],
        "unmapped_event_count": vals["unmapped_event_count"],
        "validation_fail_count": vals["validation_fail_count"],
        "quality_issue_count": vals["quality_issue_count"],
        "estimated_missing_rate": vals["estimated_missing_rate"],
        "collector_capture_rate": vals["collector_capture_rate"],
        "batch_measurement_source": "stg_ds_metric_hh_wide+metric_value_day",
    }
    row = {k: v for k, v in base.items() if k in mb_cols}
    where = "profile_id=%s AND dt=%s"
    params = [args.profile_id, dt]
    if "run_id" in mb_cols:
        where += " AND run_id=%s"
        params.append(args.run_id or "")
    cur.execute(f"DELETE FROM measurement_batch_day WHERE {where}", tuple(params))
    cols = list(row.keys())
    sql = f"INSERT INTO measurement_batch_day ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})"
    cur.execute(sql, tuple(row[c] for c in cols))


def upsert_behavior(cur, args, dt: str, vals: Dict[str, Any]) -> None:
    metric_json = json.dumps({k: safe_json_value(v) for k, v in vals.items() if k not in ("quality_json",)}, ensure_ascii=False)
    quality_json = json.dumps(vals.get("quality_json", {}), ensure_ascii=False, default=str)
    cur.execute("DELETE FROM batch_behavior_measurement_day WHERE profile_id=%s AND dt=%s AND run_id=%s", (args.profile_id, dt, args.run_id or ""))
    cur.execute("""
        INSERT INTO batch_behavior_measurement_day (
          profile_id,dt,run_id,scenario_name,visit,uv,pv,pageview,event_count,batch_event_count,
          raw_event_count,collector_event_count,estimated_missing_rate,avg_session_duration_sec,new_user_ratio,
          session_count,funnel_start_count,funnel_submit_count,conversion_rate,auth_attempt_count,auth_success_count,
          auth_fail_count,auth_success_rate,auth_fail_rate,mapping_coverage,unmapped_event_count,
          mapping_suggestion_count,validation_fail_count,quality_issue_count,other_event_count,pv_per_uv,
          visit_per_uv,pv_per_visit,session_fragmentation_ratio,collector_capture_rate,metric_json,quality_json
        ) VALUES (
          %(profile_id)s,%(dt)s,%(run_id)s,%(scenario_name)s,%(visit)s,%(uv)s,%(pv)s,%(pageview)s,%(event_count)s,%(batch_event_count)s,
          %(raw_event_count)s,%(collector_event_count)s,%(estimated_missing_rate)s,%(avg_session_duration_sec)s,%(new_user_ratio)s,
          %(session_count)s,%(funnel_start_count)s,%(funnel_submit_count)s,%(conversion_rate)s,%(auth_attempt_count)s,%(auth_success_count)s,
          %(auth_fail_count)s,%(auth_success_rate)s,%(auth_fail_rate)s,%(mapping_coverage)s,%(unmapped_event_count)s,
          %(mapping_suggestion_count)s,%(validation_fail_count)s,%(quality_issue_count)s,%(other_event_count)s,%(pv_per_uv)s,
          %(visit_per_uv)s,%(pv_per_visit)s,%(session_fragmentation_ratio)s,%(collector_capture_rate)s,%(metric_json)s,%(quality_json)s
        )
    """, {**vals, "profile_id": args.profile_id, "dt": dt, "run_id": args.run_id or "", "scenario_name": args.scenario_name or "", "metric_json": metric_json, "quality_json": quality_json})


def main() -> None:
    p = argparse.ArgumentParser(description="Build v0.4 batch measurement interfaces from analyzer_b and quality diagnostic assets.")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--dt")
    p.add_argument("--dt-from")
    p.add_argument("--dt-to")
    p.add_argument("--run-id", default="")
    p.add_argument("--scenario-name", default="")
    p.add_argument("--truncate-target", action="store_true")
    args = p.parse_args()
    dt = args.dt or args.dt_from
    if not dt:
        raise SystemExit("--dt or --dt-from required")
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            wide = wide_sums(cur, args.profile_id, dt)
            visit = wide["visit"] or hh_metric_sum(cur, args.profile_id, dt, "visit")
            uv = wide["uv"] or hh_metric_sum(cur, args.profile_id, dt, "uv")
            pageview = wide["pageview"] or hh_metric_sum(cur, args.profile_id, dt, "pageview")
            event_count = count_stg_event_batch(cur, args.profile_id, dt, args.run_id)
            if event_count == 0:
                event_count = inum(metric_day(cur, args.profile_id, dt, "batch_event_count"))
            raw_event_count = inum(metric_day(cur, args.profile_id, dt, "raw_event_count"))
            collector_event_count = inum(metric_day(cur, args.profile_id, dt, "collector_event_count"))
            batch_event_count = inum(metric_day(cur, args.profile_id, dt, "batch_event_count")) or event_count
            estimated_missing_rate = fnum(metric_day(cur, args.profile_id, dt, "estimated_missing_rate"))
            avg_session = fnum(metric_day(cur, args.profile_id, dt, "avg_session_duration_sec"))
            new_user_ratio = fnum(metric_day(cur, args.profile_id, dt, "new_user_ratio"))
            auth_attempt = inum(metric_day(cur, args.profile_id, dt, "auth_attempt_count"))
            auth_success = inum(metric_day(cur, args.profile_id, dt, "auth_success_count"))
            auth_fail = inum(metric_day(cur, args.profile_id, dt, "auth_fail_count"))
            auth_success_rate = fnum(metric_day(cur, args.profile_id, dt, "auth_success_rate"))
            auth_fail_rate = fnum(metric_day(cur, args.profile_id, dt, "auth_fail_rate"))
            # Generic funnel interface: do not hard-code finance columns in storage.
            start = metric_group_sum(cur, args.profile_id, dt, '(_start_count|view_count)$')
            submit = metric_group_sum(cur, args.profile_id, dt, '(_submit_count|success_count|complete_count)$')
            # avoid auth_success dominating generic conversion when explicit start metrics exist
            explicit_start = metric_group_sum(cur, args.profile_id, dt, '_start_count$')
            explicit_submit = metric_group_sum(cur, args.profile_id, dt, '_submit_count$')
            if explicit_start > 0:
                start, submit = explicit_start, explicit_submit
            conversion_rate = (submit / start) if start else 0.0
            map_cov, unmapped_count = mapping_coverage(cur, args.profile_id, dt)
            validation_fail, quality_issue, other_count, suggestion_count = quality_counts(cur, args.profile_id, dt)
            pv = pageview
            session_count = int(visit)
            collector_capture_rate = (batch_event_count / raw_event_count) if raw_event_count else 1.0 if batch_event_count else 0.0
            vals: Dict[str, Any] = {
                "visit": visit,
                "uv": uv,
                "pv": pv,
                "pageview": pageview,
                "event_count": event_count,
                "batch_event_count": batch_event_count,
                "raw_event_count": raw_event_count,
                "collector_event_count": collector_event_count,
                "estimated_missing_rate": estimated_missing_rate,
                "avg_session_duration_sec": avg_session,
                "new_user_ratio": new_user_ratio,
                "session_count": session_count,
                "funnel_start_count": int(start),
                "funnel_submit_count": int(submit),
                "conversion_rate": conversion_rate,
                "auth_attempt_count": auth_attempt,
                "auth_success_count": auth_success,
                "auth_fail_count": auth_fail,
                "auth_success_rate": auth_success_rate,
                "auth_fail_rate": auth_fail_rate,
                "mapping_coverage": map_cov,
                "unmapped_event_count": unmapped_count,
                "mapping_suggestion_count": suggestion_count,
                "validation_fail_count": validation_fail,
                "quality_issue_count": quality_issue,
                "other_event_count": other_count,
                "pv_per_uv": (pv / uv) if uv else 0.0,
                "visit_per_uv": (visit / uv) if uv else 0.0,
                "pv_per_visit": (pv / visit) if visit else 0.0,
                "session_fragmentation_ratio": (visit / uv) if uv else 0.0,
                "collector_capture_rate": collector_capture_rate,
                "quality_json": {
                    "mapping_coverage": map_cov,
                    "unmapped_event_count": unmapped_count,
                    "validation_fail_count": validation_fail,
                    "quality_issue_count": quality_issue,
                    "source_tables": ["stg_ds_metric_hh_wide", "stg_ds_metric_hh", "metric_value_day", "batch_quality_diagnostic_v04"],
                },
            }
            upsert_measurement_batch(cur, args, dt, vals)
            upsert_behavior(cur, args, dt, vals)
        conn.commit()
    finally:
        conn.close()
    print(f"[MEASUREMENT_BATCH_RESTORE] profile_id={args.profile_id} dt={dt} run_id={args.run_id} visit={visit:.0f} uv={uv:.0f} pv={pv:.0f} event_count={event_count} mapping_coverage={map_cov:.6f}")


if __name__ == "__main__":
    main()
