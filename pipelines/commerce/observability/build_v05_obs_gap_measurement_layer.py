#!/usr/bin/env python3
"""CASE-OBS-001 Phase2-B Gap Measurement Layer.

This materializer compares WebServer reality rows with WC collector rows by
app version, SDK version, URL/screen, client metadata, and metric type.

Role boundary:
- Python: direct measurement aggregation and persistence.
- R: later statistical interpretation / risk scoring.
- SQL: table persistence only.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

import pymysql

META = ("app_platform", "app_version", "sdk_version")
METRICS = ("event_count", "pv", "uv", "visit", "conversion")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build CASE-OBS-001 Phase2-B version/client/url/metric gap measurements.")
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
    p.add_argument("--truncate-target", action="store_true")
    p.add_argument("--missing-threshold", type=float, default=0.05)
    p.add_argument("--min-web-events", type=int, default=30)
    p.add_argument("--apply-schema", action="store_true", help="Create measurement tables when they do not exist.")
    return p.parse_args()


def connect(args: argparse.Namespace):
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


def safe_div(num: float, den: float) -> float:
    den = float(den or 0)
    if den <= 0:
        return 0.0
    return max(0.0, min(1.0, float(num or 0) / den))


def norm(v: Any) -> str:
    s = str(v or "").strip()
    return s if s else "unknown"


def norm_key(v: Any, max_len: int = 191) -> str:
    s = norm(v)
    if len(s) <= max_len:
        return s
    return s[:max_len]


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["n"] or 0) > 0


def table_cols(cur, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def apply_schema(cur) -> None:
    # Keep this in Python as a convenience for zip-based patching. The same DDL
    # is also shipped in sql/073_v05_obs_gap_measurement_layer_mariadb.sql.
    ddl_path = "sql/073_v05_obs_gap_measurement_layer_mariadb.sql"
    with open(ddl_path, "r", encoding="utf-8") as f:
        sql = f.read()
    cleaned_lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        cleaned_lines.append(line)
    statements = [s.strip() for s in "\n".join(cleaned_lines).split(";") if s.strip()]
    for stmt in statements:
        cur.execute(stmt)


def require_source_tables(cur) -> None:
    for table in ("stg_webserver_log_hit", "stg_wc_log_hit"):
        if not table_exists(cur, table):
            raise RuntimeError(f"missing required table: {table}")
        cols = table_cols(cur, table)
        missing = [c for c in META if c not in cols]
        if missing:
            raise RuntimeError(f"{table} missing metadata columns: {missing}")


def browser_family(ua: str) -> str:
    ua_l = (ua or "").lower()
    if "edg/" in ua_l or "edge/" in ua_l:
        return "Edge"
    if "chrome/" in ua_l or "crios/" in ua_l:
        return "Chrome"
    if "safari/" in ua_l and "chrome/" not in ua_l and "crios/" not in ua_l:
        return "Safari"
    if "firefox/" in ua_l:
        return "Firefox"
    if not ua_l:
        return "unknown"
    return "Other"


def os_family(ua: str, app_platform: str) -> str:
    p = (app_platform or "").lower()
    ua_l = (ua or "").lower()
    if p == "ios_app" or "iphone" in ua_l or "ipad" in ua_l:
        return "iOS"
    if p == "android_app" or "android" in ua_l:
        return "Android"
    if "windows" in ua_l:
        return "Windows"
    if "mac os" in ua_l or "macintosh" in ua_l:
        return "macOS"
    if "linux" in ua_l:
        return "Linux"
    return "unknown"


def metric_seed() -> Dict[str, int]:
    return {m: 0 for m in METRICS}


def identity_seed() -> Dict[str, int]:
    return {"event_count": 0, "uid_events": 0}


def add_identity_counts(bucket: Dict[str, int], row: Dict[str, Any]) -> None:
    bucket["event_count"] += 1
    uid = norm(row.get("uid"))
    if uid != "unknown":
        bucket["uid_events"] += 1


def add_metrics(bucket: Dict[str, int], row: Dict[str, Any]) -> None:
    bucket["event_count"] += 1
    evt = str(row.get("event_type") or row.get("evt") or "").lower()
    page_type = str(row.get("page_type") or "").lower()
    if evt in ("view", "page_view", "pv") or page_type in ("home", "category", "product", "search", "cart", "checkout", "payment"):
        bucket["pv"] += 1
    if str(row.get("is_conversion") or "0") in ("1", "true", "True"):
        bucket["conversion"] += 1


def add_identity_sets(sets: Dict[str, set], row: Dict[str, Any]) -> None:
    pcid = norm(row.get("pcid"))
    sid = norm(row.get("sid") or row.get("session_id"))
    ip = norm(row.get("ip"))
    visitor = pcid if pcid != "unknown" else ip
    if visitor != "unknown":
        sets["uv"].add(visitor)
    if sid != "unknown":
        sets["visit"].add(sid)


def fetch_rows(cur, table: str, args: argparse.Namespace) -> Iterable[Dict[str, Any]]:
    cols = table_cols(cur, table)
    date_col = "dt" if "dt" in cols else "target_date"
    select_cols = [
        "app_platform", "app_version", "sdk_version", "device_type", "ua", "path",
        "event_type", "evt", "page_type", "is_conversion", "uid", "pcid", "sid", "session_id", "ip",
    ]
    present = [c for c in select_cols if c in cols]
    where = ["profile_id=%s", f"{date_col}=%s"]
    params: List[Any] = [args.profile_id, args.target_date]
    if "source_gen_run_id" in cols:
        where.append("source_gen_run_id=%s")
        params.append(args.source_gen_run_id)
    if table == "stg_webserver_log_hit" and "scenario_name" in cols:
        where.append("scenario_name=%s")
        params.append(args.scenario_name)
    sql = f"SELECT {','.join(present)} FROM {table} WHERE {' AND '.join(where)}"
    cur.execute(sql, tuple(params))
    for r in cur.fetchall():
        yield r


def aggregate_source(cur, table: str, args: argparse.Namespace) -> Dict[str, Any]:
    app = defaultdict(metric_seed)
    app_sets = defaultdict(lambda: {"uv": set(), "visit": set()})
    sdk = defaultdict(metric_seed)
    sdk_sets = defaultdict(lambda: {"uv": set(), "visit": set()})
    url = defaultdict(metric_seed)
    url_sets = defaultdict(lambda: {"uv": set(), "visit": set()})
    client = defaultdict(metric_seed)
    client_sets = defaultdict(lambda: {"uv": set(), "visit": set()})
    dims = defaultdict(metric_seed)
    dim_sets = defaultdict(lambda: {"uv": set(), "visit": set()})
    identity = defaultdict(identity_seed)
    identity_users = defaultdict(lambda: {"uid": set()})

    for row in fetch_rows(cur, table, args):
        platform = norm(row.get("app_platform"))
        app_version = norm(row.get("app_version"))
        sdk_version = norm(row.get("sdk_version"))
        device = norm(row.get("device_type"))
        ua = str(row.get("ua") or "")
        browser = browser_family(ua)
        osf = os_family(ua, platform)
        path = norm_key(row.get("path"), 191)

        app_key = (platform, app_version, sdk_version)
        sdk_key = (platform, sdk_version)
        url_key = (platform, app_version, sdk_version, path)
        client_key = (platform, app_version, sdk_version, device, browser, osf)

        for bucket, sets, key in (
            (app, app_sets, app_key),
            (sdk, sdk_sets, sdk_key),
            (url, url_sets, url_key),
            (client, client_sets, client_key),
        ):
            add_metrics(bucket[key], row)
            add_identity_sets(sets[key], row)

        add_identity_counts(identity[app_key], row)
        uid = norm(row.get("uid"))
        if uid != "unknown":
            identity_users[app_key]["uid"].add(uid)

        dim_keys = [
            ("all", "all"),
            ("app_platform", platform),
            ("app_version", norm_key(f"{platform}|{app_version}", 191)),
            ("sdk_version", norm_key(f"{platform}|{sdk_version}", 191)),
            ("app_sdk", norm_key(f"{platform}|{app_version}|{sdk_version}", 191)),
        ]
        for key in dim_keys:
            add_metrics(dims[key], row)
            add_identity_sets(dim_sets[key], row)

    def finalize_metric_counts(data: Dict[Any, Dict[str, int]], sets: Dict[Any, Dict[str, set]]) -> Dict[Any, Dict[str, int]]:
        out = {}
        for key, metrics in data.items():
            m = dict(metrics)
            m["uv"] = len(sets[key]["uv"])
            m["visit"] = len(sets[key]["visit"])
            out[key] = m
        return out

    identity_out = {}
    for key, counts in identity.items():
        c = dict(counts)
        c["login_users"] = len(identity_users[key]["uid"])
        identity_out[key] = c

    return {
        "app": finalize_metric_counts(app, app_sets),
        "sdk": finalize_metric_counts(sdk, sdk_sets),
        "url": finalize_metric_counts(url, url_sets),
        "client": finalize_metric_counts(client, client_sets),
        "dims": finalize_metric_counts(dims, dim_sets),
        "identity": identity_out,
    }


def count_canonical(cur, table: str, args: argparse.Namespace, group_cols: Tuple[str, ...]) -> Dict[Tuple[str, ...], int]:
    if not table_exists(cur, table):
        return {}
    cols = table_cols(cur, table)
    if not all(c in cols for c in group_cols):
        return {}
    where = ["profile_id=%s", "target_date=%s"]
    params: List[Any] = [args.profile_id, args.target_date]
    if "run_id" in cols:
        where.append("run_id=%s")
        params.append(args.run_id)
    if "source_gen_run_id" in cols:
        where.append("source_gen_run_id=%s")
        params.append(args.source_gen_run_id)
    if "scenario_name" in cols:
        where.append("scenario_name=%s")
        params.append(args.scenario_name)
    select = ",".join(group_cols)
    sql = f"SELECT {select}, COUNT(*) AS c FROM {table} WHERE {' AND '.join(where)} GROUP BY {select}"
    cur.execute(sql, tuple(params))
    out = {}
    for r in cur.fetchall():
        out[tuple(norm(r.get(c)) for c in group_cols)] = int(r.get("c") or 0)
    return out


def gap_row(web: Dict[str, int], wc: Dict[str, int], threshold: float, min_web: int) -> Dict[str, Any]:
    web_events = int(web.get("event_count") or 0)
    wc_events = int(wc.get("event_count") or 0)
    missing = max(0, web_events - wc_events)
    missing_rate = safe_div(missing, web_events)
    return {
        "webserver_events": web_events,
        "wc_events": wc_events,
        "webserver_uv": int(web.get("uv") or 0),
        "wc_uv": int(wc.get("uv") or 0),
        "webserver_visit": int(web.get("visit") or 0),
        "wc_visit": int(wc.get("visit") or 0),
        "webserver_pv": int(web.get("pv") or 0),
        "wc_pv": int(wc.get("pv") or 0),
        "webserver_conversion": int(web.get("conversion") or 0),
        "wc_conversion": int(wc.get("conversion") or 0),
        "missing_count": missing,
        "missing_rate": missing_rate,
        "uv_missing_rate": safe_div(max(0, int(web.get("uv") or 0) - int(wc.get("uv") or 0)), int(web.get("uv") or 0)),
        "visit_missing_rate": safe_div(max(0, int(web.get("visit") or 0) - int(wc.get("visit") or 0)), int(web.get("visit") or 0)),
        "pv_missing_rate": safe_div(max(0, int(web.get("pv") or 0) - int(wc.get("pv") or 0)), int(web.get("pv") or 0)),
        "conversion_missing_rate": safe_div(max(0, int(web.get("conversion") or 0) - int(wc.get("conversion") or 0)), int(web.get("conversion") or 0)),
        "tagging_missing_flag": 1 if web_events >= min_web and missing_rate >= threshold else 0,
    }


def severity(rate: float) -> str:
    if rate >= 0.30:
        return "critical"
    if rate >= 0.15:
        return "high"
    if rate >= 0.05:
        return "warning"
    return "low"


def delete_targets(cur, args: argparse.Namespace) -> None:
    for table in (
        "v05_obs_app_version_measurement_day",
        "v05_obs_sdk_version_measurement_day",
        "v05_obs_url_gap_day",
        "v05_obs_client_gap_day",
        "v05_obs_metric_gap_day",
        "v05_obs_identity_gap_day",
        "v05_obs_url_semantic_gap_day",
        "v05_obs_business_kpi_gap_day",
    ):
        cur.execute(
            f"""
            DELETE FROM {table}
            WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
            """,
            (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.source_gen_run_id),
        )


def insert(cur, table: str, row: Dict[str, Any]) -> None:
    cols = list(row.keys())
    placeholders = ",".join(["%s"] * len(cols))
    assignments = ",".join([f"{c}=VALUES({c})" for c in cols if c not in ("created_at",)])
    cur.execute(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {assignments}",
        tuple(row[c] for c in cols),
    )


def base(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "profile_id": args.profile_id,
        "target_date": args.target_date,
        "scenario_name": args.scenario_name,
        "run_id": args.run_id,
        "source_gen_run_id": args.source_gen_run_id,
    }


def build(cur, args: argparse.Namespace) -> Dict[str, int]:
    require_source_tables(cur)
    if args.apply_schema:
        apply_schema(cur)
    for t in ("v05_obs_app_version_measurement_day", "v05_obs_sdk_version_measurement_day", "v05_obs_metric_gap_day", "v05_obs_identity_gap_day", "v05_obs_url_semantic_gap_day", "v05_obs_business_kpi_gap_day"):
        if not table_exists(cur, t):
            raise RuntimeError(f"missing {t}; apply sql/073_v05_obs_gap_measurement_layer_mariadb.sql or pass --apply-schema")

    web = aggregate_source(cur, "stg_webserver_log_hit", args)
    wc = aggregate_source(cur, "stg_wc_log_hit", args)
    ce_app = count_canonical(cur, "canonical_events", args, ("app_platform", "app_version", "sdk_version"))
    cb_app = count_canonical(cur, "canonical_behavior_events", args, ("app_platform", "app_version", "sdk_version"))

    if args.truncate_target:
        delete_targets(cur, args)

    counts = {"app": 0, "sdk": 0, "url": 0, "client": 0, "metric": 0, "identity": 0, "url_semantic": 0, "business_kpi": 0}
    app_keys = set(web["app"]) | set(wc["app"])
    for key in sorted(app_keys):
        platform, app_version, sdk_version = key
        g = gap_row(web["app"].get(key, {}), wc["app"].get(key, {}), args.missing_threshold, args.min_web_events)
        row = {**base(args), "app_platform": platform, "app_version": app_version, "sdk_version": sdk_version, **g}
        row["canonical_events"] = ce_app.get(key, 0)
        row["canonical_behavior_events"] = cb_app.get(key, 0)
        row["baseline_missing_rate"] = None
        row["gap_delta_from_baseline"] = None
        row["detail_json"] = json.dumps({"web": web["app"].get(key, {}), "wc": wc["app"].get(key, {})}, ensure_ascii=False)
        insert(cur, "v05_obs_app_version_measurement_day", row)
        counts["app"] += 1

        wi = web["identity"].get(key, {})
        ci = wc["identity"].get(key, {})
        web_uid_events = int(wi.get("uid_events") or 0)
        wc_uid_events = int(ci.get("uid_events") or 0)
        web_login_users = int(wi.get("login_users") or 0)
        wc_login_users = int(ci.get("login_users") or 0)
        uid_missing_rate = safe_div(max(0, web_uid_events - wc_uid_events), web_uid_events)
        login_user_gap_rate = safe_div(max(0, web_login_users - wc_login_users), web_login_users)
        identity_row = {
            **base(args),
            "app_platform": platform,
            "app_version": app_version,
            "sdk_version": sdk_version,
            "webserver_events": int(wi.get("event_count") or 0),
            "wc_events": int(ci.get("event_count") or 0),
            "webserver_uid_events": web_uid_events,
            "wc_uid_events": wc_uid_events,
            "uid_missing_count": max(0, web_uid_events - wc_uid_events),
            "uid_missing_rate": uid_missing_rate,
            "webserver_login_users": web_login_users,
            "wc_login_users": wc_login_users,
            "login_user_gap_rate": login_user_gap_rate,
            "identity_integrity_gap": max(uid_missing_rate, login_user_gap_rate),
        }
        insert(cur, "v05_obs_identity_gap_day", identity_row)
        counts["identity"] += 1

    sdk_keys = set(web["sdk"]) | set(wc["sdk"])
    for key in sorted(sdk_keys):
        platform, sdk_version = key
        g = gap_row(web["sdk"].get(key, {}), wc["sdk"].get(key, {}), args.missing_threshold, args.min_web_events)
        affected_versions = len({k[1] for k in app_keys if k[0] == platform and k[2] == sdk_version})
        row = {**base(args), "app_platform": platform, "sdk_version": sdk_version, **g}
        row["affected_app_versions"] = affected_versions
        row["baseline_missing_rate"] = None
        row["gap_delta_from_baseline"] = None
        row["detail_json"] = json.dumps({"web": web["sdk"].get(key, {}), "wc": wc["sdk"].get(key, {})}, ensure_ascii=False)
        insert(cur, "v05_obs_sdk_version_measurement_day", row)
        counts["sdk"] += 1

    for key in sorted(set(web["url"]) | set(wc["url"])):
        platform, app_version, sdk_version, surface_path = key
        g = gap_row(web["url"].get(key, {}), wc["url"].get(key, {}), args.missing_threshold, args.min_web_events)
        row = {**base(args), "app_platform": platform, "app_version": app_version, "sdk_version": sdk_version, "surface_path": surface_path}
        row.update({k: g[k] for k in ("webserver_events", "wc_events", "missing_count", "missing_rate", "webserver_uv", "wc_uv", "uv_missing_rate", "tagging_missing_flag")})
        insert(cur, "v05_obs_url_gap_day", row)
        counts["url"] += 1

        web_events = int(web["url"].get(key, {}).get("event_count") or 0)
        wc_events = int(wc["url"].get(key, {}).get("event_count") or 0)
        under_count = max(0, web_events - wc_events)
        over_count = max(0, wc_events - web_events)
        denom = max(web_events, wc_events, 1)
        distribution_shift_score = min(1.0, abs(web_events - wc_events) / float(denom))
        semantic_row = {
            **base(args),
            "app_platform": platform,
            "app_version": app_version,
            "sdk_version": sdk_version,
            "surface_path": surface_path,
            "webserver_events": web_events,
            "wc_events": wc_events,
            "under_count": under_count,
            "over_count": over_count,
            "under_rate": safe_div(under_count, web_events),
            "over_rate": safe_div(over_count, web_events),
            "distribution_shift_score": distribution_shift_score,
            "url_collapse_flag": 1 if distribution_shift_score >= args.missing_threshold and (under_count > 0 or over_count > 0) else 0,
            "shifted_direction": "under" if under_count > 0 else ("over" if over_count > 0 else "none"),
        }
        insert(cur, "v05_obs_url_semantic_gap_day", semantic_row)
        counts["url_semantic"] += 1

    for key in sorted(set(web["client"]) | set(wc["client"])):
        platform, app_version, sdk_version, device_type, browser, osf = key
        g = gap_row(web["client"].get(key, {}), wc["client"].get(key, {}), args.missing_threshold, args.min_web_events)
        row = {**base(args), "app_platform": platform, "app_version": app_version, "sdk_version": sdk_version, "device_type": device_type, "browser_family": browser, "os_family": osf}
        row.update({k: g[k] for k in ("webserver_events", "wc_events", "missing_count", "missing_rate", "webserver_uv", "wc_uv", "uv_missing_rate", "tagging_missing_flag")})
        insert(cur, "v05_obs_client_gap_day", row)
        counts["client"] += 1

    dim_keys = set(web["dims"]) | set(wc["dims"])
    for dim in sorted(dim_keys):
        w = web["dims"].get(dim, {})
        c = wc["dims"].get(dim, {})
        for metric in METRICS:
            web_value = float(w.get(metric) or 0)
            wc_value = float(c.get(metric) or 0)
            missing = max(0.0, web_value - wc_value)
            rate = safe_div(missing, web_value)
            row = {
                **base(args),
                "dimension_type": dim[0],
                "dimension_value": norm_key(dim[1], 191),
                "metric_name": metric,
                "web_value": web_value,
                "wc_value": wc_value,
                "missing_value": missing,
                "gap_rate": rate,
                "baseline_web_value": None,
                "baseline_wc_value": None,
                "baseline_gap_rate": None,
                "gap_delta_from_baseline": None,
                "severity": severity(rate),
                "tagging_missing_flag": 1 if web_value >= args.min_web_events and rate >= args.missing_threshold else 0,
            }
            insert(cur, "v05_obs_metric_gap_day", row)
            counts["metric"] += 1

    # Business KPI criticality view: one generic all-scope row. This keeps
    # purchase/conversion/revenue-sensitive impact separate from traffic volume.
    all_web = web["dims"].get(("all", "all"), {})
    all_wc = wc["dims"].get(("all", "all"), {})
    pv_gap_rate = safe_div(max(0, float(all_web.get("pv") or 0) - float(all_wc.get("pv") or 0)), float(all_web.get("pv") or 0))
    uv_gap_rate = safe_div(max(0, float(all_web.get("uv") or 0) - float(all_wc.get("uv") or 0)), float(all_web.get("uv") or 0))
    visit_gap_rate = safe_div(max(0, float(all_web.get("visit") or 0) - float(all_wc.get("visit") or 0)), float(all_web.get("visit") or 0))
    conversion_gap_rate = safe_div(max(0, float(all_web.get("conversion") or 0) - float(all_wc.get("conversion") or 0)), float(all_web.get("conversion") or 0))
    traffic_preservation_score = 1.0 if pv_gap_rate <= 0.02 else (max(0.0, min(1.0, 1.0 - (pv_gap_rate / 0.12) * 0.55)) if pv_gap_rate <= 0.12 else 0.0)
    business_kpi_distortion_score = max(0.0, min(1.0, 0.65 * conversion_gap_rate + 0.35 * traffic_preservation_score))
    insert(cur, "v05_obs_business_kpi_gap_day", {
        **base(args),
        "scope_type": "all",
        "scope_value": "all",
        "pv_gap_rate": pv_gap_rate,
        "uv_gap_rate": uv_gap_rate,
        "visit_gap_rate": visit_gap_rate,
        "conversion_gap_rate": conversion_gap_rate,
        "purchase_event_gap_rate": conversion_gap_rate,
        "revenue_proxy_gap_rate": conversion_gap_rate * 0.80,
        "traffic_preservation_score": traffic_preservation_score,
        "business_kpi_distortion_score": business_kpi_distortion_score,
    })
    counts["business_kpi"] += 1
    return counts


def main() -> int:
    args = parse_args()
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            counts = build(cur, args)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(
        "[OK] build_v05_obs_gap_measurement_layer "
        f"scenario={args.scenario_name} run_id={args.run_id} source_gen_run_id={args.source_gen_run_id} "
        f"app_rows={counts['app']} sdk_rows={counts['sdk']} url_rows={counts['url']} "
        f"client_rows={counts['client']} metric_rows={counts['metric']} identity_rows={counts['identity']} url_semantic_rows={counts['url_semantic']} business_kpi_rows={counts['business_kpi']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
