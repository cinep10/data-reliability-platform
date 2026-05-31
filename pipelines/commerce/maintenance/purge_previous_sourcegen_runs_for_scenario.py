#!/usr/bin/env python3
from __future__ import annotations
import argparse
from typing import Any
import pymysql

LINEAGE_TABLES = [
    "raw_snapshot_manifest", "source_file_manifest", "source_generation_result_history", "source_generation_result_summary",
    "stg_webserver_log_hit", "stg_wc_log_hit", "event_log_raw", "canonical_events",
    "stg_event_batch", "stg_event_stream", "stream_replay_event",
    "canonical_behavior_events", "canonical_transaction_events", "canonical_state_events",
    "behavior_transaction_mapping", "transaction_state_mapping",
    "v05_runtime_evidence_day", "v05_reconciliation_measurement_day",
    "reliability_analysis_result_day_v05", "semantic_interpretation_day_v05",
    "unified_reliability_score_day_v05", "action_recommendation_day_v05",
    "v05_ml_feature_snapshot_day", "v05_ai_validation_result_day", "v05_ai_reliability_score_day",
]

PATH_COLS = [
    "source_file_path", "file_path", "path", "output_file", "output_path", "output_dir",
    "input_dir", "manifest_path", "source_dir", "source_path",
]

def parse_args():
    p = argparse.ArgumentParser(description="Keep only the active source_gen_run_id for profile/date/scenario.")
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--active-source-gen-run-id", type=int, required=True)
    p.add_argument("--include-ml-ai", action="store_true")
    p.add_argument("--include-baseline-between-runs", action="store_true", help="Also delete baseline run ids between previous and active scenario runs. Use for isolated scenario smoke cleanup.")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()

def connect(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def table_exists(cur, t):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (t,))
    return int(cur.fetchone()["cnt"]) == 1

def columns(cur, t):
    if not table_exists(cur, t):
        return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (t,))
    return {str(r["column_name"]) for r in cur.fetchall()}

def date_filter(cs, a):
    if "target_date" in cs:
        return "target_date=%s", [a.target_date]
    if "dt" in cs:
        return "dt=%s", [a.target_date]
    if "event_date" in cs:
        return "event_date=%s", [a.target_date]
    if "log_date" in cs:
        return "log_date=%s", [a.target_date]
    return "1=1", []

def profile_filter(cs, a):
    if "profile_id" in cs:
        return "profile_id=%s", [a.profile_id]
    return "1=1", []

def scenario_or_path_filter(cs, a, include_baseline=False):
    ors = []
    ps: list[Any] = []
    scenario_values = [a.scenario_name]
    if include_baseline:
        scenario_values.append("baseline")
    for sv in scenario_values:
        if "scenario_name" in cs:
            ors.append("scenario_name=%s"); ps.append(sv)
        if "scenario_id" in cs:
            ors.append("scenario_id=%s"); ps.append(sv)
    for c in PATH_COLS:
        if c in cs:
            ors.append(f"`{c}` LIKE %s"); ps.append(f"%/{a.profile_id}/{a.target_date}/{a.scenario_name}%")
            ors.append(f"`{c}` LIKE %s"); ps.append(f"%\\{a.profile_id}\\{a.target_date}\\{a.scenario_name}%")
    if not ors:
        return None, []
    return "(" + " OR ".join(ors) + ")", ps

def discover_previous_ids(cur, a):
    ids = set()
    # Discover same-scenario previous ids and optionally interleaved baseline ids.
    for t in ["source_file_manifest", "raw_snapshot_manifest", "source_generation_result_history", "source_generation_result_summary", "stg_webserver_log_hit", "stg_wc_log_hit", "event_log_raw", "canonical_events"]:
        if not table_exists(cur, t):
            continue
        cs = columns(cur, t)
        if "source_gen_run_id" not in cs:
            continue
        wh = []; ps: list[Any] = []
        psql, pps = profile_filter(cs, a); dsql, dps = date_filter(cs, a)
        ssql, sps = scenario_or_path_filter(cs, a, include_baseline=a.include_baseline_between_runs)
        if psql != "1=1": wh.append(psql); ps.extend(pps)
        if dsql != "1=1": wh.append(dsql); ps.extend(dps)
        if not ssql: continue
        wh.append(ssql); ps.extend(sps)
        wh.append("source_gen_run_id<>%s"); ps.append(a.active_source_gen_run_id)
        # Never delete future source_gen_run_ids.
        wh.append("source_gen_run_id<%s"); ps.append(a.active_source_gen_run_id)
        sql = f"SELECT DISTINCT source_gen_run_id FROM `{t}` WHERE {' AND '.join(wh)} AND source_gen_run_id IS NOT NULL"
        cur.execute(sql, tuple(ps))
        for r in cur.fetchall():
            if r.get("source_gen_run_id") is not None:
                ids.add(int(r["source_gen_run_id"]))
    return sorted(ids)

def delete_table(cur, t, ids, a):
    if not table_exists(cur, t):
        print(f"[SKIP] missing table {t}")
        return 0
    cs = columns(cur, t)
    if "source_gen_run_id" not in cs:
        print(f"[SKIP] no source_gen_run_id table={t}")
        return 0
    wh = []; ps: list[Any] = []
    psql, pps = profile_filter(cs, a); dsql, dps = date_filter(cs, a)
    if psql != "1=1": wh.append(psql); ps.extend(pps)
    if dsql != "1=1": wh.append(dsql); ps.extend(dps)
    wh.append("source_gen_run_id IN (" + ",".join(["%s"] * len(ids)) + ")"); ps.extend(ids)
    where = " AND ".join(wh)
    if a.dry_run:
        cur.execute(f"SELECT COUNT(*) cnt FROM `{t}` WHERE {where}", tuple(ps))
        cnt = int(cur.fetchone()["cnt"])
        print(f"[DRY_RUN] {t} would_delete={cnt} previous_ids={ids}")
        return cnt
    cur.execute(f"DELETE FROM `{t}` WHERE {where}", tuple(ps))
    affected = int(cur.rowcount or 0)
    print(f"[PURGE_PREVIOUS] {t} affected={affected} previous_ids={ids}")
    return affected

def main():
    a = parse_args()
    con = connect(a)
    try:
        with con.cursor() as cur:
            previous_ids = discover_previous_ids(cur, a)
            print(f"[INFO] scenario={a.scenario_name} active_source_gen_run_id={a.active_source_gen_run_id} previous_source_gen_run_ids={previous_ids}")
            if not previous_ids:
                con.rollback()
                print("[OK] no previous source_gen_run_id to purge")
                return 0
            tables = LINEAGE_TABLES if a.include_ml_ai else [t for t in LINEAGE_TABLES if not (t.startswith("v05_ml_") or t.startswith("v05_ai_"))]
            total = 0
            for t in tables:
                total += delete_table(cur, t, previous_ids, a)
        con.rollback() if a.dry_run else con.commit()
        print(f"[DONE] purge_previous_sourcegen_runs total_affected={total}")
        return 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

if __name__ == "__main__":
    raise SystemExit(main())
