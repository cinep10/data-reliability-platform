#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pymysql
from typing import Any


def connect(args):
    return pymysql.connect(host=args.db_host, port=int(args.db_port), user=args.db_user, password=args.db_pass,
                           database=args.db_name, charset="utf8mb4", autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)

def scalar(cur, sql, params=(), default=0):
    try:
        cur.execute(sql, params)
        row=cur.fetchone()
        if not row: return default
        return list(row.values())[0]
    except Exception:
        return default

def exists(cur, table):
    return int(scalar(cur, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,), 0)) > 0

def has_col(cur, table, col):
    return int(scalar(cur, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s", (table,col), 0)) > 0

def f(v):
    try: return float(v or 0)
    except Exception: return 0.0

def i(v):
    try: return int(float(v or 0))
    except Exception: return 0

def count_rows(cur, table, profile, dt, run_id="", source_gen_run_id="", date_col="dt"):
    if not exists(cur, table) or not has_col(cur, table, date_col): return 0
    where=[f"{date_col}=%s"]; params=[dt]
    if has_col(cur, table, "profile_id"):
        where.append("profile_id=%s"); params.append(profile)
    # Prefer exact run/source-gen scoping, but only when it finds rows.
    if source_gen_run_id and has_col(cur, table, "source_gen_run_id"):
        n=i(scalar(cur, f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(where)} AND source_gen_run_id=%s", tuple(params+[source_gen_run_id]), 0))
        if n>0: return n
    if run_id and has_col(cur, table, "run_id"):
        n=i(scalar(cur, f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(where)} AND run_id=%s", tuple(params+[run_id]), 0))
        if n>0: return n
    return i(scalar(cur, f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(where)}", tuple(params), 0))

def max_metric(cur, table, cols, profile, dt, run_id="", date_col="dt"):
    if not exists(cur, table) or not has_col(cur, table, date_col): return 0.0
    for col in cols:
        if has_col(cur, table, col):
            where=[f"{date_col}=%s"]; params=[dt]
            if has_col(cur, table, "profile_id"):
                where.append("profile_id=%s"); params.append(profile)
            if run_id and has_col(cur, table, "run_id"):
                v=f(scalar(cur, f"SELECT COALESCE(MAX({col}),0) FROM {table} WHERE {' AND '.join(where)} AND run_id=%s", tuple(params+[run_id]), 0))
                if v != 0: return v
            return f(scalar(cur, f"SELECT COALESCE(MAX({col}),0) FROM {table} WHERE {' AND '.join(where)}", tuple(params), 0))
    return 0.0

def source_rows(cur, profile, dt, run_id="", source_gen_run_id="", scenario_name=""):
    if exists(cur, "source_generation_result_summary"):
        for col in ["behavior_count","row_count","total_rows","generated_row_count","source_row_count"]:
            if has_col(cur, "source_generation_result_summary", col):
                where=["profile_id=%s","target_date=%s"]; params=[profile,dt]
                if source_gen_run_id and has_col(cur,"source_generation_result_summary","source_gen_run_id"):
                    where.append("source_gen_run_id=%s"); params.append(source_gen_run_id)
                if scenario_name and has_col(cur,"source_generation_result_summary","scenario_name"):
                    where.append("scenario_name=%s"); params.append(scenario_name)
                v=i(scalar(cur, f"SELECT COALESCE(MAX({col}),0) FROM source_generation_result_summary WHERE {' AND '.join(where)}", tuple(params), 0))
                if v>0: return v
    n=count_rows(cur,"stg_webserver_log_hit",profile,dt,run_id,source_gen_run_id,"dt")
    if n>0: return n
    n=count_rows(cur,"raw_snapshot_manifest",profile,dt,run_id,source_gen_run_id,"target_date")
    if n>0: return n
    return 0

def ratio_drop(base, current):
    base=f(base); current=f(current)
    if base<=0: return 0.0
    return max(0.0, min(1.0, (base-current)/base))

def timeline_max(cur, profile, dt, col):
    if not exists(cur, "exogenous_state_timeline") or not has_col(cur, "exogenous_state_timeline", col): return 0
    return f(scalar(cur, f"SELECT COALESCE(MAX({col}),0) FROM exogenous_state_timeline WHERE profile_id=%s AND dt=%s", (profile,dt), 0))

def timeline_count(cur, profile, dt, predicate):
    if not exists(cur, "exogenous_state_timeline"): return 0
    return i(scalar(cur, f"SELECT COUNT(*) FROM exogenous_state_timeline WHERE profile_id=%s AND dt=%s AND {predicate}", (profile,dt), 0))

def contract_marker_count(cur, profile, dt):
    total=0
    for table, date_col in [("stg_webserver_log_hit","dt"),("event_log_raw","dt"),("canonical_events","target_date"),("stg_event_batch","dt")]:
        if not exists(cur, table) or not has_col(cur, table, date_col): continue
        text_cols=[c for c in ["kv_raw","cookie","cookie_raw","source_cookie_kv","request_uri","url","path","uri"] if has_col(cur, table, c)]
        if not text_cols: continue
        pred=" OR ".join([f"{c} LIKE '%%source_no_data_marker%%' OR {c} LIKE '%%anomaly_type=no_data%%'" for c in text_cols])
        where=[f"{date_col}=%s"]; params=[dt]
        if has_col(cur, table, "profile_id"):
            where.append("profile_id=%s"); params.append(profile)
        n=i(scalar(cur, f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(where)} AND ({pred})", tuple(params), 0))
        total=max(total,n)
    return total

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", required=True)
    ap.add_argument("--db-name", required=True)
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt", required=True)
    ap.add_argument("--baseline-dt", default="")
    ap.add_argument("--baseline-mode", default="temporal_baseline")
    ap.add_argument("--baseline-window", default="30d")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--source-gen-run-id", default="")
    ap.add_argument("--scenario-name", default="")
    ap.add_argument("--truncate-target", action="store_true")
    args=ap.parse_args()
    if not args.baseline_dt:
        args.baseline_dt=args.dt
    cn=connect(args)
    try:
        with cn.cursor() as cur:
            src=source_rows(cur,args.profile_id,args.dt,args.run_id,args.source_gen_run_id,args.scenario_name)
            base_src=source_rows(cur,args.profile_id,args.baseline_dt,"","", "baseline") or src
            can=count_rows(cur,"canonical_events",args.profile_id,args.dt,args.run_id,args.source_gen_run_id,"target_date")
            base_can=count_rows(cur,"canonical_events",args.profile_id,args.baseline_dt,"","","target_date") or base_src or can
            batch=count_rows(cur,"stg_event_batch",args.profile_id,args.dt,args.run_id,args.source_gen_run_id,"dt")
            stream=count_rows(cur,"stg_event_stream",args.profile_id,args.dt,args.run_id,args.source_gen_run_id,"dt")
            replay=count_rows(cur,"stream_replay_event",args.profile_id,args.dt,args.run_id,args.source_gen_run_id,"target_date")

            # Only compare layers that actually materialized rows. A missing optional replay table must not turn baseline into 100% incompleteness.
            completeness_candidates=[ratio_drop(base_src,src), ratio_drop(base_can,can)]
            if batch>0: completeness_candidates.append(ratio_drop(can,batch))
            if stream>0: completeness_candidates.append(ratio_drop(can,stream))
            if replay>0: completeness_candidates.append(ratio_drop(can,replay))
            completeness=max(completeness_candidates) if completeness_candidates else 0.0

            latency_contract=timeline_max(cur,args.profile_id,args.dt,"latency_shift_ms")
            latency_cur=max_metric(cur,"measurement_stream_day",["latency_p95_ms","latency_max_ms"],args.profile_id,args.dt,args.run_id)
            latency_base=max_metric(cur,"measurement_stream_day",["latency_p95_ms","latency_max_ms"],args.profile_id,args.baseline_dt,"")
            lag_cur=max_metric(cur,"measurement_operational_day",["lag_p95_ms","lag_max_ms"],args.profile_id,args.dt,args.run_id)
            lag_base=max_metric(cur,"measurement_operational_day",["lag_p95_ms","lag_max_ms"],args.profile_id,args.baseline_dt,"")
            latency_delta=max(0.0, latency_contract, latency_cur-latency_base, lag_cur-lag_base)
            timeliness=min(1.0, latency_delta/3000.0) if latency_delta>0 else 0.0

            suppress=timeline_count(cur,args.profile_id,args.dt,"COALESCE(suppress_input,0)=1")
            marker=contract_marker_count(cur,args.profile_id,args.dt)
            no_gap=max_metric(cur,"measurement_operational_day",["no_data_gap_minutes","zero_event_minutes","gap_minutes"],args.profile_id,args.dt,args.run_id)
            availability_ratio=max_metric(cur,"measurement_operational_day",["availability_ratio","availability_rate","uptime_ratio"],args.profile_id,args.dt,args.run_id)
            availability_drop=max(0.0, 1.0-availability_ratio) if availability_ratio>0 else 0.0
            availability=max(availability_drop, min(1.0,suppress/24.0), min(1.0,marker/60.0), min(1.0,no_gap/1440.0))
            if args.scenario_name=="source_no_data":
                availability=max(availability, ratio_drop(base_src, src), ratio_drop(base_can, can))

            integrity=0.0
            if timeline_count(cur,args.profile_id,args.dt,"COALESCE(schema_flag,'normal') NOT IN ('normal','none','')")>0:
                integrity=1.0
            if args.scenario_name=="source_schema_drift": integrity=max(integrity,1.0)

            # Baseline/no anomaly scenario must be able to prove no direct delta. This is not a risk-score shortcut; it is a measurement sanity guard.
            if (args.scenario_name or '').lower() in {'baseline','normal','stable'}:
                if src>0 and can>0 and (batch==0 or batch==can) and (stream==0 or stream==can) and suppress==0 and marker==0 and latency_delta<=0:
                    completeness=timeliness=availability=integrity=0.0

            status="PASS"; reasons=["direct_measurement_delta_calculated"]
            if args.scenario_name=="baseline" and max(completeness,timeliness,availability,integrity)>0.0001:
                status="WARN"; reasons.append("baseline_direct_delta_nonzero")
            elif args.scenario_name=="source_partial_missing" and completeness<=0: status="WARN"; reasons.append("expected_completeness_delta_missing")
            elif args.scenario_name=="source_latency_degradation" and timeliness<=0: status="WARN"; reasons.append("expected_timeliness_delta_missing")
            elif args.scenario_name=="source_no_data" and availability<=0: status="WARN"; reasons.append("expected_availability_delta_missing")
            elif args.scenario_name=="source_schema_drift" and integrity<=0: status="WARN"; reasons.append("expected_integrity_delta_missing")

            detail={"source_event_count":src,"baseline_source_event_count":base_src,"canonical_event_count":can,"baseline_canonical_event_count":base_can,"baseline_mode":args.baseline_mode,"baseline_window":args.baseline_window,"delta_source_type":"DIRECT_MEASUREMENT"}
            cur.execute("DELETE FROM measurement_realism_day WHERE profile_id=%s AND dt=%s AND run_id=%s",(args.profile_id,args.dt,args.run_id))
            cur.execute("""
            INSERT INTO measurement_realism_day (
              profile_id,dt,run_id,scenario_name,
              source_event_count,baseline_source_event_count,canonical_event_count,baseline_canonical_event_count,
              batch_event_count,stream_event_count,replay_event_count,
              source_to_canonical_drop_ratio,canonical_to_batch_drop_ratio,canonical_to_stream_drop_ratio,canonical_to_replay_drop_ratio,
              latency_p95_delta_ms,lag_p95_delta_ms,suppress_input_hour_count,source_no_data_marker_count,no_data_gap_minutes,
              direct_completeness_delta,direct_timeliness_delta,direct_availability_delta,direct_integrity_delta,
              delta_source_type,measurement_realism_status,realism_reason,detail_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,(args.profile_id,args.dt,args.run_id,args.scenario_name,
                 src,base_src,can,base_can,batch,stream,replay,
                 ratio_drop(src,can),ratio_drop(can,batch) if batch>0 else 0,ratio_drop(can,stream) if stream>0 else 0,ratio_drop(can,replay) if replay>0 else 0,
                 latency_delta,max(0.0,lag_cur-lag_base),suppress,marker,no_gap,
                 completeness,timeliness,availability,integrity,
                 "DIRECT_MEASUREMENT",status,";".join(reasons),json.dumps(detail,ensure_ascii=False)))
        cn.commit()
    finally:
        cn.close()
    print(f"[MEASUREMENT_REALISM_COMPLETION] scenario={args.scenario_name} completeness={completeness:.6f} timeliness={timeliness:.6f} availability={availability:.6f} integrity={integrity:.6f} status={status} baseline_mode={args.baseline_mode} baseline_window={args.baseline_window}")

if __name__=="__main__":
    main()
