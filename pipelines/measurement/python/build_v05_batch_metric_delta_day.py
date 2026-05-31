#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any, Optional

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build scalar batch metric deltas against v0.5 baseline reference.")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", default="")
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--dt", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--scenario-name", default="baseline")
    p.add_argument("--baseline-mode", default="temporal_baseline")
    p.add_argument("--baseline-window", default="30d")
    p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()


def connect(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(cur.fetchone()["cnt"] or 0) > 0


def cols(cur, table: str) -> set[str]:
    if not table_exists(cur, table):
        return set()
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def first_col(available: set[str], candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in available:
            return c
    return None


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def scalar(cur, sql: str, params: tuple[Any, ...], default: Any = 0) -> Any:
    try:
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return default
        return next(iter(row.values()))
    except Exception:
        return default


def count_table(cur, table: str, a: argparse.Namespace, date_col_candidates: list[str]) -> int:
    """Count rows with progressive fallback.

    Some v0.5 tables are populated after observability measurement and do not always
    carry every identity column consistently. For scalar batch delta, the safest
    behavior is:
    1. try strict profile/date/run/source/scenario scope,
    2. relax run/source identity when that returns 0,
    3. relax scenario only as the last resort for same profile/date.
    """
    if not table_exists(cur, table):
        return 0

    c = cols(cur, table)
    date_col = first_col(c, date_col_candidates)
    if not date_col:
        return 0

    def build_query(include_source: bool, include_run: bool, include_scenario: bool):
        where = [f"`{date_col}`=%s"]
        params: list[Any] = [a.dt]

        if "profile_id" in c:
            where.append("profile_id=%s")
            params.append(a.profile_id)

        if include_source and "source_gen_run_id" in c and a.source_gen_run_id is not None:
            where.append("source_gen_run_id=%s")
            params.append(a.source_gen_run_id)

        if include_run and "run_id" in c:
            where.append("run_id=%s")
            params.append(a.run_id)

        if include_scenario and "scenario_name" in c:
            where.append("scenario_name=%s")
            params.append(a.scenario_name)

        return f"SELECT COUNT(*) FROM `{table}` WHERE {' AND '.join(where)}", tuple(params)

    attempts = [
        (True, True, True),
        (True, False, True),
        (False, True, True),
        (False, False, True),
        (True, True, False),
        (False, False, False),
    ]

    for include_source, include_run, include_scenario in attempts:
        sql, params = build_query(include_source, include_run, include_scenario)
        value = int(fnum(scalar(cur, sql, params, 0)))
        if value > 0:
            return value

    return 0

def read_measurement_batch(cur, a: argparse.Namespace) -> dict[str, float]:
    if not table_exists(cur, "measurement_batch_day"):
        return {}
    c = cols(cur, "measurement_batch_day")
    where = ["profile_id=%s", "dt=%s"]
    params: list[Any] = [a.profile_id, a.dt]
    if "run_id" in c:
        where.append("run_id=%s")
        params.append(a.run_id)
    if "scenario_name" in c:
        where.append("scenario_name=%s")
        params.append(a.scenario_name)
    cur.execute(f"SELECT * FROM measurement_batch_day WHERE {' AND '.join(where)} ORDER BY run_id DESC LIMIT 1", tuple(params))
    row = cur.fetchone() or {}
    return {
        "event_count": fnum(row.get("event_count")),
        "pv": fnum(row.get("pv_count") or row.get("pv") or row.get("pageview_count")),
        "uv": fnum(row.get("uv_count") or row.get("uv")),
        "visit": fnum(row.get("visit_count") or row.get("visit") or row.get("session_count")),
        "conversion_rate": fnum(row.get("conversion_rate")),
        "mapping_coverage": fnum(row.get("mapping_coverage")),
        "collector_capture_rate": fnum(row.get("collector_capture_rate")),
        "estimated_missing_rate": fnum(row.get("estimated_missing_rate")),
    }


def read_observability(cur, a: argparse.Namespace) -> dict[str, float]:
    obs: dict[str, float] = {}
    if table_exists(cur, "v05_observability_measurement_day"):
        c = cols(cur, "v05_observability_measurement_day")
        where = ["profile_id=%s", "target_date=%s"]
        params: list[Any] = [a.profile_id, a.dt]
        if "run_id" in c:
            where.append("run_id=%s")
            params.append(a.run_id)
        if "source_gen_run_id" in c and a.source_gen_run_id is not None:
            where.append("source_gen_run_id=%s")
            params.append(a.source_gen_run_id)
        if "scenario_name" in c:
            where.append("scenario_name=%s")
            params.append(a.scenario_name)
        cur.execute(f"SELECT * FROM v05_observability_measurement_day WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT 1", tuple(params))
        row = cur.fetchone() or {}
        obs.update({
            "web_hits": fnum(row.get("web_hits")),
            "wc_hits": fnum(row.get("wc_hits")),
            "canonical_behavior_events": fnum(row.get("canonical_behavior_events")),
            "collection_gap_rate": fnum(row.get("collection_gap_rate")),
            "canonical_gap_rate": fnum(row.get("canonical_gap_rate") or row.get("web_to_canonical_gap_rate")),
            "checkout_missing_rate": fnum(row.get("checkout_missing_rate")),
            "product_missing_rate": fnum(row.get("product_missing_rate")),
            "uv_gap_rate": fnum(row.get("uv_gap_rate")),
        })
    if obs.get("web_hits", 0) <= 0:
        obs["web_hits"] = float(count_table(cur, "stg_webserver_log_hit", a, ["target_date", "dt"]))
    if obs.get("wc_hits", 0) <= 0:
        obs["wc_hits"] = float(count_table(cur, "stg_wc_log_hit", a, ["target_date", "dt"]))
    if obs.get("canonical_behavior_events", 0) <= 0:
        obs["canonical_behavior_events"] = float(count_table(cur, "canonical_behavior_events", a, ["target_date", "dt"]))

    web = obs.get("web_hits", 0.0)
    wc = obs.get("wc_hits", 0.0)
    can = obs.get("canonical_behavior_events", 0.0)

    if web > 0:
        # Always recompute these derived rates after fallback counts.
        # The observability row can be written before canonical_behavior_events exists.
        obs["collection_gap_rate"] = max(0.0, (web - wc) / web)
        obs["canonical_gap_rate"] = max(0.0, (web - can) / web)

    return obs


def baseline_metric(cur, a: argparse.Namespace, metric_scope: str, metric_name: str) -> tuple[Optional[float], Optional[float], str]:
    if not table_exists(cur, "v05_baseline_metric_snapshot_day"):
        return None, None, "BASELINE_MISSING_REVIEW"
    cur.execute(
        """
        SELECT metric_value_avg, metric_value_std, sample_days
        FROM v05_baseline_metric_snapshot_day
        WHERE profile_id=%s AND target_date=%s AND baseline_window=%s
          AND metric_scope=%s AND metric_name=%s
          AND dimension_key='all' AND dimension_value='all'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (a.profile_id, a.dt, a.baseline_window, metric_scope, metric_name),
    )
    row = cur.fetchone()
    if not row or row.get("metric_value_avg") is None:
        if a.scenario_name == "baseline":
            return None, None, "BASELINE_SELF_REFERENCE"
        return None, None, "BASELINE_MISSING_REVIEW"
    return fnum(row.get("metric_value_avg")), fnum(row.get("metric_value_std")), "baseline_available"


def score_delta(current: float, base: Optional[float], std: Optional[float], scenario_name: str) -> tuple[Optional[float], Optional[float], Optional[float], float, str]:
    if base is None:
        if scenario_name == "baseline":
            return 0.0, 0.0, 0.0, 0.0, "BASELINE_SELF_REFERENCE"
        return None, None, None, 0.0, "BASELINE_MISSING_REVIEW"
    abs_delta = current - base
    rate = abs(abs_delta) / max(abs(base), 1.0)
    z = abs(abs_delta) / max(float(std or 0.0), 1e-9) if std and std > 0 else 0.0
    score = max(min(rate / 0.20, 1.0), min(z / 5.0, 1.0))
    return abs_delta, rate, z, score, "baseline_available"


def risk_status(score: float, baseline_status: str) -> str:
    if baseline_status == "BASELINE_MISSING_REVIEW":
        return "BASELINE_MISSING_REVIEW"
    if score >= 0.60:
        return "FAIL"
    if score >= 0.20:
        return "WARN"
    return "PASS"


def insert_rows(cur, a: argparse.Namespace, rows: list[dict[str, Any]]) -> None:
    cur.execute(
        "DELETE FROM v05_batch_metric_delta_day WHERE profile_id=%s AND dt=%s AND run_id=%s AND scenario_name=%s",
        (a.profile_id, a.dt, a.run_id, a.scenario_name),
    )
    if not rows:
        return
    columns = [
        "profile_id", "dt", "run_id", "source_gen_run_id", "scenario_name", "baseline_mode", "baseline_window",
        "metric_scope", "metric_name", "current_value", "baseline_value_avg", "baseline_value_std", "absolute_delta",
        "delta_rate", "z_score", "risk_score", "risk_status", "baseline_status", "source_table", "analysis_reason",
    ]
    sql = "INSERT INTO v05_batch_metric_delta_day (" + ",".join(columns) + ") VALUES (" + ",".join(["%s"] * len(columns)) + ")"
    cur.executemany(sql, [tuple(r.get(c) for c in columns) for r in rows])


def main() -> int:
    a = parse_args()
    con = connect(a)
    try:
        with con.cursor() as cur:
            if not table_exists(cur, "v05_batch_metric_delta_day"):
                raise RuntimeError("missing table v05_batch_metric_delta_day. Apply sql/070_v05_batch_metric_delta_schema_mariadb.sql first.")
            mb = read_measurement_batch(cur, a)
            obs = read_observability(cur, a)
            metrics = [
                ("behavior_volume", "event_count", mb.get("event_count", 0.0), "measurement_batch_day"),
                ("behavior_volume", "pv", mb.get("pv", 0.0), "measurement_batch_day"),
                ("behavior_volume", "uv", mb.get("uv", 0.0), "measurement_batch_day"),
                ("behavior_volume", "visit", mb.get("visit", 0.0), "measurement_batch_day"),
                ("behavior_funnel", "conversion_rate", mb.get("conversion_rate", 0.0), "measurement_batch_day"),
                ("behavior_funnel", "collector_capture_rate", mb.get("collector_capture_rate", 0.0), "measurement_batch_day"),
                ("behavior_funnel", "estimated_missing_rate", mb.get("estimated_missing_rate", 0.0), "measurement_batch_day"),
                ("observability", "web_hits", obs.get("web_hits", 0.0), "v05_observability_measurement_day/stage"),
                ("observability", "wc_hits", obs.get("wc_hits", 0.0), "v05_observability_measurement_day/stage"),
                ("observability", "canonical_behavior_events", obs.get("canonical_behavior_events", 0.0), "canonical_behavior_events"),
                ("observability", "collection_gap_rate", obs.get("collection_gap_rate", 0.0), "v05_observability_measurement_day"),
                ("observability", "canonical_gap_rate", obs.get("canonical_gap_rate", 0.0), "v05_observability_measurement_day"),
                ("observability", "checkout_missing_rate", obs.get("checkout_missing_rate", 0.0), "v05_observability_measurement_day"),
                ("observability", "product_missing_rate", obs.get("product_missing_rate", 0.0), "v05_observability_measurement_day"),
                ("observability", "uv_gap_rate", obs.get("uv_gap_rate", 0.0), "v05_observability_measurement_day"),
            ]
            rows: list[dict[str, Any]] = []
            for scope, name, current, source_table in metrics:
                base, std, bstatus = baseline_metric(cur, a, scope, name)
                if name.endswith("gap_rate") or name.endswith("missing_rate"):
                    # A rate that should be near zero is risky by its absolute value when current is high.
                    if base is None and a.scenario_name != "baseline":
                        base, std, bstatus = 0.0, 0.0, "baseline_available_zero_expected"
                    abs_delta, delta_rate, z, score, derived_status = score_delta(current, base, std, a.scenario_name)
                    score = max(score, min(abs(current) / 0.20, 1.0)) if bstatus.startswith("baseline_available") else score
                else:
                    # Observability count metrics often do not have historical baseline rows.
                    # For WC/canonical counts, the same-run WebServer hit count is the expected
                    # reality baseline because WC should capture the WebServer source volume.
                    if scope == "observability" and name in {"wc_hits", "canonical_behavior_events"} and base is None and obs.get("web_hits", 0.0) > 0:
                        base = obs.get("web_hits", 0.0)
                        std = 0.0
                        bstatus = "same_run_webserver_expected"
                    elif scope == "observability" and name == "web_hits" and base is None:
                        base = current
                        std = 0.0
                        bstatus = "same_run_source_reference"
                    abs_delta, delta_rate, z, score, derived_status = score_delta(current, base, std, a.scenario_name)
                status = risk_status(score, bstatus if bstatus not in {"baseline_available_zero_expected", "same_run_webserver_expected", "same_run_source_reference"} else "baseline_available")
                rows.append({
                    "profile_id": a.profile_id,
                    "dt": a.dt,
                    "run_id": a.run_id,
                    "source_gen_run_id": a.source_gen_run_id,
                    "scenario_name": a.scenario_name,
                    "baseline_mode": a.baseline_mode,
                    "baseline_window": a.baseline_window,
                    "metric_scope": scope,
                    "metric_name": name,
                    "current_value": current,
                    "baseline_value_avg": base,
                    "baseline_value_std": std,
                    "absolute_delta": abs_delta,
                    "delta_rate": delta_rate,
                    "z_score": z,
                    "risk_score": score,
                    "risk_status": status,
                    "baseline_status": bstatus,
                    "source_table": source_table,
                    "analysis_reason": f"scope={scope};metric={name};current={current};baseline={base};status={status}",
                })
            insert_rows(cur, a, rows)
        con.commit()
        max_score = max([float(r.get("risk_score") or 0) for r in rows], default=0.0)
        print(f"[OK] build_v05_batch_metric_delta_day scenario={a.scenario_name} rows={len(rows)} max_score={max_score:.6f}")
        return 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
