#!/usr/bin/env python3
"""CASE-OBS-001 Phase2-C1 Baseline Science Foundation.

Builds an OBS-only baseline layer from Phase2-B Gap Measurement outputs.

Role boundary:
- SQL: persistence only.
- Python: orchestration and feature snapshot materialization only.
- R: statistical baseline profile and compare calculations.
- ML: forecast/expected model extension point, not implemented in C1.
"""
from __future__ import annotations

import argparse
import subprocess
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pymysql

MEASUREMENT_TABLES = (
    "v05_obs_app_version_measurement_day",
    "v05_obs_sdk_version_measurement_day",
    "v05_obs_url_gap_day",
    "v05_obs_client_gap_day",
    "v05_obs_metric_gap_day",
)
FEATURE_TABLE = "v05_obs_baseline_feature_snapshot_day"
STAT_TABLE = "v05_obs_baseline_stat_profile_day"
COMPARE_TABLE = "v05_obs_baseline_compare_day"
REF_TABLE = "v05_obs_baseline_reference_day"

RATE_COLUMNS = (
    ("collection_gap_rate", "missing_rate"),
    ("uv_gap_rate", "uv_missing_rate"),
    ("visit_gap_rate", "visit_missing_rate"),
    ("pv_gap_rate", "pv_missing_rate"),
    ("conversion_gap_rate", "conversion_missing_rate"),
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build CASE-OBS-001 Phase2-C1 OBS baseline foundation.")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", default="")
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--baseline-window", default="30d")
    p.add_argument("--baseline-scenario", default="baseline")
    p.add_argument("--include-target-date", nargs="?", const="true", default="false", help="Allow current target_date baseline run to seed baseline stats. Accepts flag form or explicit true/false.")
    p.add_argument("--min-sample-days", type=int, default=3)
    p.add_argument("--truncate-target", action="store_true")
    p.add_argument("--apply-schema", action="store_true")
    p.add_argument("--rscript-bin", default="Rscript")
    p.add_argument("--skip-r", action="store_true", help="Only materialize feature snapshots; skip R stat/compare steps.")
    a = p.parse_args()
    a.include_target_date = str(a.include_target_date).lower() in ("1", "true", "yes", "y")
    return a


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


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def days_from_window(w: str) -> int:
    return int(w[:-1]) if w.endswith("d") and w[:-1].isdigit() else 30


def norm(v: Any, default: str = "unknown", max_len: int = 191) -> str:
    s = str(v or "").strip()
    if not s:
        s = default
    return s[:max_len]


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["n"] or 0) > 0


def table_cols(cur, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {str(r["column_name"]) for r in cur.fetchall()}


def apply_schema(cur) -> None:
    with open("sql/074_v05_obs_baseline_foundation_mariadb.sql", "r", encoding="utf-8") as f:
        sql = f.read()
    lines: List[str] = []
    for line in sql.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        lines.append(line)
    for stmt in [x.strip() for x in "\n".join(lines).split(";") if x.strip()]:
        cur.execute(stmt)


def require_tables(cur) -> None:
    missing = [t for t in MEASUREMENT_TABLES if not table_exists(cur, t)]
    if missing:
        raise RuntimeError(f"missing Phase2-B measurement tables: {missing}")


def insert(cur, table: str, row: Dict[str, Any]) -> None:
    cols = list(row.keys())
    placeholders = ",".join(["%s"] * len(cols))
    updates = ",".join([f"{c}=VALUES({c})" for c in cols if c not in ("created_at",)])
    cur.execute(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}",
        tuple(row[c] for c in cols),
    )


def metric_value(row: Dict[str, Any], col: str) -> Optional[float]:
    if col not in row or row[col] is None:
        return None
    try:
        return float(row[col])
    except (TypeError, ValueError):
        return None


def add_rate_feature(features: List[Dict[str, Any]], base: Dict[str, Any], dimension_type: str, dimension_key: str, metric_name: str, row: Dict[str, Any], rate_col: str, web_col: Optional[str], wc_col: Optional[str], source_table: str, dim_json: Dict[str, Any]) -> None:
    v = metric_value(row, rate_col)
    if v is None:
        return
    web = metric_value(row, web_col) if web_col else None
    wc = metric_value(row, wc_col) if wc_col else None
    missing = None
    if web is not None and wc is not None:
        missing = max(0.0, web - wc)
    features.append({
        **base,
        "dimension_type": dimension_type,
        "dimension_key": norm(dimension_key),
        "metric_name": metric_name,
        "metric_value": v,
        "webserver_value": web,
        "wc_value": wc,
        "missing_value": missing,
        "missing_rate": v,
        "source_table": source_table,
        "source_dimension_json": json.dumps(dim_json, ensure_ascii=False),
    })


def features_from_app(row: Dict[str, Any], base: Dict[str, Any], source_table: str) -> List[Dict[str, Any]]:
    platform = norm(row.get("app_platform"))
    app_version = norm(row.get("app_version"))
    sdk_version = norm(row.get("sdk_version"))
    dims = [
        ("app_platform", platform, {"app_platform": platform}),
        ("app_version", f"{platform}|{app_version}", {"app_platform": platform, "app_version": app_version}),
        ("app_sdk", f"{platform}|{app_version}|{sdk_version}", {"app_platform": platform, "app_version": app_version, "sdk_version": sdk_version}),
    ]
    out: List[Dict[str, Any]] = []
    for dtype, dkey, dj in dims:
        for metric_name, rate_col in RATE_COLUMNS:
            web_col = {"collection_gap_rate": "webserver_events", "uv_gap_rate": "webserver_uv", "visit_gap_rate": "webserver_visit", "pv_gap_rate": "webserver_pv", "conversion_gap_rate": "webserver_conversion"}.get(metric_name)
            wc_col = {"collection_gap_rate": "wc_events", "uv_gap_rate": "wc_uv", "visit_gap_rate": "wc_visit", "pv_gap_rate": "wc_pv", "conversion_gap_rate": "wc_conversion"}.get(metric_name)
            add_rate_feature(out, base, dtype, dkey, metric_name, row, rate_col, web_col, wc_col, source_table, dj)
    return out


def features_from_sdk(row: Dict[str, Any], base: Dict[str, Any], source_table: str) -> List[Dict[str, Any]]:
    platform = norm(row.get("app_platform"))
    sdk_version = norm(row.get("sdk_version"))
    out: List[Dict[str, Any]] = []
    for metric_name, rate_col in RATE_COLUMNS:
        web_col = {"collection_gap_rate": "webserver_events", "uv_gap_rate": "webserver_uv", "visit_gap_rate": "webserver_visit", "pv_gap_rate": "webserver_pv", "conversion_gap_rate": "webserver_conversion"}.get(metric_name)
        wc_col = {"collection_gap_rate": "wc_events", "uv_gap_rate": "wc_uv", "visit_gap_rate": "wc_visit", "pv_gap_rate": "wc_pv", "conversion_gap_rate": "wc_conversion"}.get(metric_name)
        add_rate_feature(out, base, "sdk_version", f"{platform}|{sdk_version}", metric_name, row, rate_col, web_col, wc_col, source_table, {"app_platform": platform, "sdk_version": sdk_version})
    return out


def features_from_url(row: Dict[str, Any], base: Dict[str, Any], source_table: str) -> List[Dict[str, Any]]:
    platform = norm(row.get("app_platform"))
    app_version = norm(row.get("app_version"))
    sdk_version = norm(row.get("sdk_version"))
    surface = norm(row.get("surface_path"))
    out: List[Dict[str, Any]] = []
    for metric_name, rate_col in (("collection_gap_rate", "missing_rate"), ("uv_gap_rate", "uv_missing_rate")):
        add_rate_feature(out, base, "url", f"{platform}|{app_version}|{sdk_version}|{surface}", metric_name, row, rate_col, "webserver_events" if metric_name == "collection_gap_rate" else "webserver_uv", "wc_events" if metric_name == "collection_gap_rate" else "wc_uv", source_table, {"app_platform": platform, "app_version": app_version, "sdk_version": sdk_version, "surface_path": surface})
    return out


def features_from_client(row: Dict[str, Any], base: Dict[str, Any], source_table: str) -> List[Dict[str, Any]]:
    platform = norm(row.get("app_platform"))
    app_version = norm(row.get("app_version"))
    sdk_version = norm(row.get("sdk_version"))
    device = norm(row.get("device_type"))
    browser = norm(row.get("browser_family"))
    osf = norm(row.get("os_family"))
    out: List[Dict[str, Any]] = []
    dkey = f"{platform}|{app_version}|{sdk_version}|{device}|{browser}|{osf}"
    for metric_name, rate_col in (("collection_gap_rate", "missing_rate"), ("uv_gap_rate", "uv_missing_rate")):
        add_rate_feature(out, base, "client", dkey, metric_name, row, rate_col, "webserver_events" if metric_name == "collection_gap_rate" else "webserver_uv", "wc_events" if metric_name == "collection_gap_rate" else "wc_uv", source_table, {"app_platform": platform, "app_version": app_version, "sdk_version": sdk_version, "device_type": device, "browser_family": browser, "os_family": osf})
    return out


def features_from_metric_gap(row: Dict[str, Any], base: Dict[str, Any], source_table: str) -> List[Dict[str, Any]]:
    dtype = norm(row.get("dimension_type"))
    dvalue = norm(row.get("dimension_value"))
    metric = norm(row.get("metric_name"))
    return [{
        **base,
        "dimension_type": dtype,
        "dimension_key": dvalue,
        "metric_name": f"{metric}_gap_rate",
        "metric_value": metric_value(row, "gap_rate"),
        "webserver_value": metric_value(row, "web_value"),
        "wc_value": metric_value(row, "wc_value"),
        "missing_value": metric_value(row, "missing_value"),
        "missing_rate": metric_value(row, "gap_rate"),
        "source_table": source_table,
        "source_dimension_json": json.dumps({"dimension_type": dtype, "dimension_value": dvalue, "metric_name": metric}, ensure_ascii=False),
    }]


def date_col(cols: set[str]) -> str:
    return "target_date" if "target_date" in cols else "dt"


def source_run_col(cols: set[str]) -> Optional[str]:
    return "source_gen_run_id" if "source_gen_run_id" in cols else None


def fetch_measurement_rows(cur, table: str, a: argparse.Namespace, start: date, end: date, include_current_scenario: bool) -> List[Dict[str, Any]]:
    cols = table_cols(cur, table)
    dcol = date_col(cols)
    where = ["profile_id=%s", f"{dcol} BETWEEN %s AND %s"]
    params: List[Any] = [a.profile_id, start.isoformat(), end.isoformat()]
    if "scenario_name" in cols:
        where.append("scenario_name IN (%s,%s)" if include_current_scenario else "scenario_name=%s")
        if include_current_scenario:
            params.extend([a.baseline_scenario, a.scenario_name])
        else:
            params.append(a.baseline_scenario)
    sql = f"SELECT * FROM {table} WHERE {' AND '.join(where)}"
    cur.execute(sql, tuple(params))
    return cur.fetchall()


def materialize_features(cur, a: argparse.Namespace, start: date, end: date) -> int:
    features: List[Dict[str, Any]] = []
    include_current = True
    for table in MEASUREMENT_TABLES:
        if not table_exists(cur, table):
            continue
        for row in fetch_measurement_rows(cur, table, a, start, end, include_current):
            base = {
                "profile_id": a.profile_id,
                "target_date": row.get("target_date") or row.get("dt"),
                "scenario_name": row.get("scenario_name") or a.baseline_scenario,
                "run_id": int(row.get("run_id") or 0),
                "source_gen_run_id": int(row.get("source_gen_run_id") or 0),
            }
            if table == "v05_obs_app_version_measurement_day":
                features.extend(features_from_app(row, base, table))
            elif table == "v05_obs_sdk_version_measurement_day":
                features.extend(features_from_sdk(row, base, table))
            elif table == "v05_obs_url_gap_day":
                features.extend(features_from_url(row, base, table))
            elif table == "v05_obs_client_gap_day":
                features.extend(features_from_client(row, base, table))
            elif table == "v05_obs_metric_gap_day":
                features.extend(features_from_metric_gap(row, base, table))
    for f in features:
        if f["metric_value"] is None:
            continue
        insert(cur, FEATURE_TABLE, f)
    return len(features)



def run_r_step(a: argparse.Namespace, script_path: str) -> None:
    cmd = [
        a.rscript_bin,
        script_path,
        "--db-host", a.db_host,
        "--db-port", str(a.db_port),
        "--db-user", a.db_user,
        "--db-pass", a.db_pass,
        "--db-name", a.db_name,
        "--profile-id", a.profile_id,
        "--target-date", a.target_date,
        "--scenario-name", a.scenario_name,
        "--run-id", str(a.run_id),
        "--source-gen-run-id", str(a.source_gen_run_id),
        "--baseline-window", a.baseline_window,
        "--baseline-scenario", a.baseline_scenario,
        "--min-sample-days", str(a.min_sample_days),
    ]
    if a.include_target_date:
        # R helper parser expects key/value pairs, so pass an explicit value.
        cmd.extend(["--include-target-date", "true"])
    print("[RUN_R] " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def truncate_outputs(cur, a: argparse.Namespace) -> None:
    # Reference/stat/compare are target-date baseline outputs. They can be rebuilt safely.
    for table in (REF_TABLE, STAT_TABLE, COMPARE_TABLE):
        cur.execute(
            f"DELETE FROM {table} WHERE profile_id=%s AND target_date=%s AND baseline_window=%s",
            (a.profile_id, a.target_date, a.baseline_window),
        )
    # Feature history is intentionally preserved except the current run. This lets
    # multi-day backfills accumulate baseline samples while keeping reruns idempotent.
    cur.execute(
        f"DELETE FROM {FEATURE_TABLE} WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s",
        (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
    )


def main() -> int:
    a = parse_args()
    target = parse_date(a.target_date)
    days = days_from_window(a.baseline_window)
    start = target - timedelta(days=days)
    # Materialize features through the target date so the current run is available for compare.
    # R stat scripts decide whether target-date baseline samples are included.
    con = connect(a)
    try:
        with con.cursor() as cur:
            if a.apply_schema:
                apply_schema(cur)
            require_tables(cur)
            if a.truncate_target:
                truncate_outputs(cur, a)
            feature_count = materialize_features(cur, a, start, target)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    if not a.skip_r:
        stat_script = "pipelines/commerce/analytics/build_v05_obs_baseline_stat_profile.R"
        compare_script = "pipelines/commerce/analytics/build_v05_obs_baseline_compare.R"
        run_r_step(a, stat_script)
        run_r_step(a, compare_script)

    print(
        "[OK] build_v05_obs_baseline_foundation "
        f"scenario={a.scenario_name} target={a.target_date} window={a.baseline_window} "
        f"features={feature_count} r_stats={'skipped' if a.skip_r else 'done'} r_compare={'skipped' if a.skip_r else 'done'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
