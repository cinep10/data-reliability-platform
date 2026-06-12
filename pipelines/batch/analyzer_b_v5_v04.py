#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.common.v04_batch_common import connect_mysql, parse_kv, pick_identity, infer_event_name, is_pageview, table_columns

METRIC_META = {
    "daily_active_users": {"group": "user_activity", "source_layer": "batch_event"},
    "page_view_count": {"group": "user_activity", "source_layer": "batch_event"},
    "avg_session_duration_sec": {"group": "user_activity", "source_layer": "batch_event"},
    "new_user_ratio": {"group": "user_activity", "source_layer": "batch_event"},
    "login_success_count": {"group": "auth_security", "source_layer": "batch_event"},
    "auth_attempt_count": {"group": "auth_security", "source_layer": "batch_event"},
    "auth_success_count": {"group": "auth_security", "source_layer": "batch_event"},
    "auth_fail_count": {"group": "auth_security", "source_layer": "batch_event"},
    "auth_success_rate": {"group": "auth_security", "source_layer": "batch_event"},
    "auth_fail_rate": {"group": "auth_security", "source_layer": "batch_event"},
    "otp_request_count": {"group": "auth_security", "source_layer": "batch_event"},
    "risk_login_count": {"group": "auth_security", "source_layer": "batch_event"},
    "loan_view_count": {"group": "financial_service", "source_layer": "batch_event"},
    "loan_apply_start_count": {"group": "financial_service", "source_layer": "batch_event"},
    "loan_apply_submit_count": {"group": "financial_service", "source_layer": "batch_event"},
    "card_apply_start_count": {"group": "financial_service", "source_layer": "batch_event"},
    "card_apply_submit_count": {"group": "financial_service", "source_layer": "batch_event"},
    "card_apply_submit_rate": {"group": "financial_service", "source_layer": "batch_event"},
    "raw_event_count": {"group": "system_operation", "source_layer": "raw_event"},
    "collector_event_count": {"group": "system_operation", "source_layer": "collector"},
    "batch_event_count": {"group": "system_operation", "source_layer": "batch_event"},
    "estimated_missing_rate": {"group": "system_operation", "source_layer": "control"},
    "schema_change_count": {"group": "system_operation", "source_layer": "control"},
    "batch_delay_sec": {"group": "system_operation", "source_layer": "control"},
}

def daterange(start_dt: date, end_dt: date):
    cur = start_dt
    while cur <= end_dt:
        yield cur
        cur += timedelta(days=1)

def ensure_tables(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS metric_value_hh (
      profile_id VARCHAR(64) NOT NULL, dt DATE NOT NULL, hh TINYINT NOT NULL, metric_name VARCHAR(100) NOT NULL,
      metric_group VARCHAR(50) NOT NULL, source_layer VARCHAR(50) NOT NULL, metric_value DECIMAL(18,6) NOT NULL,
      numerator_value DECIMAL(18,6) NULL, denominator_value DECIMAL(18,6) NULL, run_id VARCHAR(64) NULL, note VARCHAR(255) NULL,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (profile_id, dt, hh, metric_name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cur.execute("""CREATE TABLE IF NOT EXISTS metric_value_day (
      profile_id VARCHAR(64) NOT NULL, dt DATE NOT NULL, metric_name VARCHAR(100) NOT NULL,
      metric_group VARCHAR(50) NOT NULL, source_layer VARCHAR(50) NOT NULL, metric_value DECIMAL(18,6) NOT NULL,
      numerator_value DECIMAL(18,6) NULL, denominator_value DECIMAL(18,6) NULL, run_id VARCHAR(64) NULL, note VARCHAR(255) NULL,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (profile_id, dt, metric_name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cur.execute("""CREATE TABLE IF NOT EXISTS stg_ds_metric_hh (
      profile_id VARCHAR(64) NOT NULL, dt DATE NOT NULL, hh TINYINT NOT NULL, metric_nm VARCHAR(100) NOT NULL,
      metric_val DECIMAL(18,6) NOT NULL, note VARCHAR(255) NULL, PRIMARY KEY (profile_id, dt, hh, metric_nm)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cur.execute("""CREATE TABLE IF NOT EXISTS stg_ds_metric_hh_wide (
      profile_id VARCHAR(64) NOT NULL, dt DATE NOT NULL, hh TINYINT NOT NULL, visit DECIMAL(18,6) NOT NULL DEFAULT 0,
      uv DECIMAL(18,6) NOT NULL DEFAULT 0, pageview DECIMAL(18,6) NOT NULL DEFAULT 0, note VARCHAR(255) NULL,
      PRIMARY KEY (profile_id, dt, hh)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

def upsert_metric_hh(cur, profile_id, dt, hh, metric_name, metric_value, numerator, denominator, run_id, note):
    meta = METRIC_META[metric_name]
    cur.execute("""INSERT INTO metric_value_hh
    (profile_id, dt, hh, metric_name, metric_group, source_layer, metric_value, numerator_value, denominator_value, run_id, note)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE metric_group=VALUES(metric_group), source_layer=VALUES(source_layer), metric_value=VALUES(metric_value),
    numerator_value=VALUES(numerator_value), denominator_value=VALUES(denominator_value), run_id=VALUES(run_id), note=VALUES(note)""",
    (profile_id, dt, hh, metric_name, meta["group"], meta["source_layer"], metric_value, numerator, denominator, run_id, note))

def upsert_metric_day(cur, profile_id, dt, metric_name, metric_value, numerator, denominator, run_id, note):
    meta = METRIC_META[metric_name]
    cur.execute("""INSERT INTO metric_value_day
    (profile_id, dt, metric_name, metric_group, source_layer, metric_value, numerator_value, denominator_value, run_id, note)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE metric_group=VALUES(metric_group), source_layer=VALUES(source_layer), metric_value=VALUES(metric_value),
    numerator_value=VALUES(numerator_value), denominator_value=VALUES(denominator_value), run_id=VALUES(run_id), note=VALUES(note)""",
    (profile_id, dt, metric_name, meta["group"], meta["source_layer"], metric_value, numerator, denominator, run_id, note))

def fetch_rows(cur, profile_id, dt_from, dt_to):
    eb_cols = table_columns(cur, "stg_event_batch")
    er_cols = table_columns(cur, "event_log_raw")
    needed = ["batch_ingest_id","raw_event_id","dt","ts","event_name","semantic_event_name","event_type","service_domain","funnel_stage","is_conversion","uid","pcid","sid","session_id","device_type","page_type","product_type","financial_product","status","status_code","latency_ms","path","query","url_norm","method","ip","kv_raw","evt"]
    eb_select = [f"eb.{c}" for c in needed if c in eb_cols]
    er_fallback = []
    for c in ["ip","method","path","query","url_norm","kv_raw","evt","ua","ref"]:
        if c not in eb_cols and c in er_cols:
            er_fallback.append(f"er.{c}")
    cur.execute(f"""
      SELECT {', '.join(eb_select + er_fallback)}
      FROM stg_event_batch eb
      LEFT JOIN event_log_raw er ON eb.raw_event_id = er.raw_event_id
      WHERE eb.profile_id=%s AND eb.dt >= %s AND eb.dt < %s
        AND COALESCE(eb.load_status, 'success') = 'success'
      ORDER BY eb.dt, eb.ts, eb.batch_ingest_id
    """, (profile_id, dt_from, dt_to))
    return cur.fetchall()

def fetch_hour_counts(cur, table_name, profile_id, dt_from, dt_to, extra_where=""):
    cols = table_columns(cur, table_name)
    date_col = "dt" if "dt" in cols else ("target_date" if "target_date" in cols else None)
    ts_col = "ts" if "ts" in cols else ("event_time" if "event_time" in cols else None)
    if not date_col or not ts_col:
        return defaultdict(int)
    where_profile = "AND profile_id=%s" if "profile_id" in cols else ""
    params = [dt_from, dt_to] if not where_profile else [dt_from, dt_to, profile_id]
    cur.execute(f"""SELECT {date_col} AS dt, HOUR({ts_col}) AS hh, COUNT(*) AS cnt
      FROM {table_name}
      WHERE {date_col} >= %s AND {date_col} < %s {where_profile} {extra_where}
      GROUP BY {date_col}, HOUR({ts_col})""", tuple(params))
    out = defaultdict(int)
    for r in cur.fetchall():
        out[(r["dt"], int(r["hh"]))] = int(r["cnt"])
    return out

def main():
    ap = argparse.ArgumentParser(description="v0.4 analyzer for stg_event_batch")
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", default="")
    ap.add_argument("--db-name", required=True)
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--date")
    ap.add_argument("--dt-from")
    ap.add_argument("--dt-to")
    ap.add_argument("--lookback-days", type=int, default=30)
    ap.add_argument("--identity-mode", choices=["uid_pcid_ip","pcid_ip","ip"], default="uid_pcid_ip")
    ap.add_argument("--session-timeout-sec", type=int, default=1800)
    ap.add_argument("--pv-mode", choices=["view_only","all_hits"], default="view_only")
    ap.add_argument("--truncate-target", action="store_true")
    ap.add_argument("--write-legacy", action="store_true")
    args = ap.parse_args()
    if args.date:
        dt_from = dt_to = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        dt_from = datetime.strptime(args.dt_from, "%Y-%m-%d").date()
        dt_to = datetime.strptime(args.dt_to, "%Y-%m-%d").date()
    query_start_dt = dt_from - timedelta(days=args.lookback_days)
    query_end_dt = dt_to + timedelta(days=1)
    run_id = f"metric_v04_{args.profile_id}_{dt_from:%Y%m%d}_{dt_to:%Y%m%d}"
    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            ensure_tables(cur)
            if args.truncate_target:
                cur.execute("DELETE FROM metric_value_hh WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, dt_from, dt_to))
                cur.execute("DELETE FROM metric_value_day WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, dt_from, dt_to))
                if args.write_legacy:
                    cur.execute("DELETE FROM stg_ds_metric_hh WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, dt_from, dt_to))
                    cur.execute("DELETE FROM stg_ds_metric_hh_wide WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, dt_from, dt_to))
            rows = fetch_rows(cur, args.profile_id, query_start_dt, query_end_dt)
            raw_hour_counts = fetch_hour_counts(cur, "event_log_raw", args.profile_id, query_start_dt, query_end_dt)
            collector_hour_counts = fetch_hour_counts(cur, "stg_wc_log_hit", args.profile_id, query_start_dt, query_end_dt)
            batch_hour_counts = fetch_hour_counts(cur, "stg_event_batch", args.profile_id, query_start_dt, query_end_dt, "AND COALESCE(load_status, 'success')='success'")
        rows_by_dt = defaultdict(list)
        for row in rows:
            rows_by_dt[row["dt"]].append(row)
        total_target_rows = 0
        processed_days = 0
        with conn.cursor() as cur:
            for target_dt in daterange(dt_from, dt_to):
                target_rows = rows_by_dt.get(target_dt, [])
                total_target_rows += len(target_rows)
                historical_users = set()
                for hist_dt in daterange(query_start_dt, target_dt - timedelta(days=1)):
                    for row in rows_by_dt.get(hist_dt, []):
                        historical_users.add(pick_identity(row, parse_kv(row.get("kv_raw")), args.identity_mode))
                dau_users_by_hh = defaultdict(set); session_duration_values = defaultdict(list)
                pv_count = defaultdict(int); visit_count = defaultdict(int)
                auth_attempt = defaultdict(int); auth_success = defaultdict(int); auth_fail = defaultdict(int)
                otp_request = defaultdict(int); risk_login = defaultdict(int); login_success = defaultdict(int)
                loan_view = defaultdict(int); loan_start = defaultdict(int); loan_submit = defaultdict(int)
                card_start = defaultdict(int); card_submit = defaultdict(int)
                last_seen = {}; session_start = {}; session_seq = defaultdict(int); seen_session_hour = set()
                for row in target_rows:
                    kv = parse_kv(row.get("kv_raw"))
                    identity = pick_identity(row, kv, args.identity_mode)
                    ts = row["ts"]; hh = ts.hour
                    event_name = infer_event_name(row, args.pv_mode)
                    if is_pageview(row, kv, args.pv_mode):
                        pv_count[hh] += 1; dau_users_by_hh[hh].add(identity)
                        prev = last_seen.get(identity)
                        if prev is None or (ts - prev) > timedelta(seconds=args.session_timeout_sec):
                            session_start[identity] = ts; session_seq[identity] += 1
                        last_seen[identity] = ts
                        session_duration_values[hh].append(max(int((ts - session_start[identity]).total_seconds()), 0))
                        sk = (hh, identity, session_seq[identity])
                        if sk not in seen_session_hour:
                            seen_session_hour.add(sk); visit_count[hh] += 1
                    if event_name == "login_success": login_success[hh] += 1
                    elif event_name == "auth_attempt": auth_attempt[hh] += 1
                    elif event_name == "auth_success": auth_attempt[hh] += 1; auth_success[hh] += 1; login_success[hh] += 1
                    elif event_name == "auth_fail": auth_attempt[hh] += 1; auth_fail[hh] += 1
                    elif event_name == "otp_request": otp_request[hh] += 1
                    elif event_name == "risk_login": risk_login[hh] += 1
                    elif event_name == "loan_view": loan_view[hh] += 1
                    elif event_name == "loan_apply_start": loan_start[hh] += 1
                    elif event_name == "loan_apply_submit": loan_submit[hh] += 1
                    elif event_name == "card_apply_start": card_start[hh] += 1
                    elif event_name == "card_apply_submit": card_submit[hh] += 1
                target_users = set().union(*dau_users_by_hh.values()) if dau_users_by_hh else set()
                new_users = {u for u in target_users if u not in historical_users}
                hh_list = sorted({hh for (d0, hh) in (set(raw_hour_counts) | set(collector_hour_counts) | set(batch_hour_counts)) if d0 == target_dt} | set(pv_count) | set(auth_attempt) | set(loan_view) | set(card_start))
                note = f"v04; identity={args.identity_mode}; pv_mode={args.pv_mode}; source=stg_event_batch; raw_compare=event_log_raw; collector_compare=stg_wc_log_hit"
                for hh in hh_list:
                    dau = len(dau_users_by_hh.get(hh, set()))
                    attempt = auth_attempt[hh]; success = auth_success[hh]; fail = auth_fail[hh]
                    loan_v = loan_view[hh]; loan_s = loan_start[hh]; loan_sub = loan_submit[hh]
                    card_s = card_start[hh]; card_sub = card_submit[hh]
                    raw_cnt = raw_hour_counts[(target_dt, hh)]; collector_cnt = collector_hour_counts[(target_dt, hh)]; batch_cnt = batch_hour_counts[(target_dt, hh)]
                    avg_sess = round(sum(session_duration_values.get(hh, [0])) / max(len(session_duration_values.get(hh, [])), 1), 6)
                    new_ratio = round(len(new_users) / max(len(target_users), 1), 6) if target_users else 0.0
                    succ_rate = round(success / attempt, 6) if attempt else 0.0
                    fail_rate = round(fail / attempt, 6) if attempt else 0.0
                    card_submit_rate = round(card_sub / card_s, 6) if card_s else 0.0
                    missing_rate = round(max(raw_cnt - batch_cnt, 0) / raw_cnt, 6) if raw_cnt else 0.0
                    metrics = [
                        ("daily_active_users", dau, dau, None), ("page_view_count", pv_count[hh], pv_count[hh], None),
                        ("avg_session_duration_sec", avg_sess, avg_sess, None), ("new_user_ratio", new_ratio, len(new_users), len(target_users)),
                        ("login_success_count", login_success[hh], login_success[hh], None), ("auth_attempt_count", attempt, attempt, None),
                        ("auth_success_count", success, success, None), ("auth_fail_count", fail, fail, None),
                        ("auth_success_rate", succ_rate, success, attempt), ("auth_fail_rate", fail_rate, fail, attempt),
                        ("otp_request_count", otp_request[hh], otp_request[hh], None), ("risk_login_count", risk_login[hh], risk_login[hh], None),
                        ("loan_view_count", loan_v, loan_v, None), ("loan_apply_start_count", loan_s, loan_s, None), ("loan_apply_submit_count", loan_sub, loan_sub, None),
                        ("card_apply_start_count", card_s, card_s, None), ("card_apply_submit_count", card_sub, card_sub, None), ("card_apply_submit_rate", card_submit_rate, card_sub, card_s),
                        ("raw_event_count", raw_cnt, raw_cnt, None), ("collector_event_count", collector_cnt, collector_cnt, None),
                        ("batch_event_count", batch_cnt, batch_cnt, None), ("estimated_missing_rate", missing_rate, max(raw_cnt - batch_cnt, 0), raw_cnt),
                    ]
                    for metric_name, metric_value, numerator, denominator in metrics:
                        upsert_metric_hh(cur, args.profile_id, target_dt, hh, metric_name, metric_value, numerator, denominator, run_id, note)
                    if args.write_legacy:
                        cur.execute("REPLACE INTO stg_ds_metric_hh (profile_id,dt,hh,metric_nm,metric_val,note) VALUES (%s,%s,%s,%s,%s,%s)", (args.profile_id,target_dt,hh,"visit",visit_count[hh],note))
                        cur.execute("REPLACE INTO stg_ds_metric_hh (profile_id,dt,hh,metric_nm,metric_val,note) VALUES (%s,%s,%s,%s,%s,%s)", (args.profile_id,target_dt,hh,"uv",dau,note))
                        cur.execute("REPLACE INTO stg_ds_metric_hh (profile_id,dt,hh,metric_nm,metric_val,note) VALUES (%s,%s,%s,%s,%s,%s)", (args.profile_id,target_dt,hh,"pageview",pv_count[hh],note))
                        cur.execute("REPLACE INTO stg_ds_metric_hh_wide (profile_id,dt,hh,visit,uv,pageview,note) VALUES (%s,%s,%s,%s,%s,%s,%s)", (args.profile_id,target_dt,hh,visit_count[hh],dau,pv_count[hh],note))
                def day_sum(src): return int(sum(src.values()))
                target_user_count = len(target_users); new_user_count = len(new_users)
                attempt_day = day_sum(auth_attempt); success_day = day_sum(auth_success); fail_day = day_sum(auth_fail)
                card_start_day = day_sum(card_start); card_submit_day = day_sum(card_submit)
                raw_day = sum(v for (d0, _), v in raw_hour_counts.items() if d0 == target_dt)
                collector_day = sum(v for (d0, _), v in collector_hour_counts.items() if d0 == target_dt)
                batch_day = sum(v for (d0, _), v in batch_hour_counts.items() if d0 == target_dt)
                missing_day = round(max(raw_day - batch_day, 0) / raw_day, 6) if raw_day else 0.0
                sess_values = [x for vals in session_duration_values.values() for x in vals]
                avg_sess_day = round(sum(sess_values) / max(len(sess_values), 1), 6)
                daily_metrics = [
                    ("daily_active_users", target_user_count, target_user_count, None), ("page_view_count", day_sum(pv_count), day_sum(pv_count), None),
                    ("avg_session_duration_sec", avg_sess_day, avg_sess_day, None), ("new_user_ratio", round(new_user_count / max(target_user_count, 1), 6) if target_user_count else 0.0, new_user_count, target_user_count),
                    ("login_success_count", day_sum(login_success), day_sum(login_success), None), ("auth_attempt_count", attempt_day, attempt_day, None),
                    ("auth_success_count", success_day, success_day, None), ("auth_fail_count", fail_day, fail_day, None),
                    ("auth_success_rate", round(success_day / attempt_day, 6) if attempt_day else 0.0, success_day, attempt_day), ("auth_fail_rate", round(fail_day / attempt_day, 6) if attempt_day else 0.0, fail_day, attempt_day),
                    ("otp_request_count", day_sum(otp_request), day_sum(otp_request), None), ("risk_login_count", day_sum(risk_login), day_sum(risk_login), None),
                    ("loan_view_count", day_sum(loan_view), day_sum(loan_view), None), ("loan_apply_start_count", day_sum(loan_start), day_sum(loan_start), None), ("loan_apply_submit_count", day_sum(loan_submit), day_sum(loan_submit), None),
                    ("card_apply_start_count", card_start_day, card_start_day, None), ("card_apply_submit_count", card_submit_day, card_submit_day, None), ("card_apply_submit_rate", round(card_submit_day / card_start_day, 6) if card_start_day else 0.0, card_submit_day, card_start_day),
                    ("raw_event_count", raw_day, raw_day, None), ("collector_event_count", collector_day, collector_day, None), ("batch_event_count", batch_day, batch_day, None), ("estimated_missing_rate", missing_day, max(raw_day - batch_day, 0), raw_day),
                    ("schema_change_count", 0, 0, None), ("batch_delay_sec", 0, 0, None),
                ]
                for metric_name, metric_value, numerator, denominator in daily_metrics:
                    upsert_metric_day(cur, args.profile_id, target_dt, metric_name, metric_value, numerator, denominator, run_id, note)
                processed_days += 1
        conn.commit()
        print(f"[analyzer_b_v5_v04] source=stg_event_batch profile_id={args.profile_id} dt_from={dt_from} dt_to={dt_to} processed_days={processed_days} rows={total_target_rows}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
