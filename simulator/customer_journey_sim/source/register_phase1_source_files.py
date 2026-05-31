#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import pymysql

ROLE_PATTERNS = [
    ("behavior", "*_behavior.w3c.log"),
    ("transaction", "*_transaction.jsonl"),
    ("state", "*_state.jsonl"),
    ("journey", "*_journey.jsonl"),
    ("manifest", "*_manifest.json"),
    ("source_anomaly_trace", "*_source_anomaly_trace.json"),
    ("exogenous_snapshot", "*_exogenous_snapshot.json"),
]

def parse_args():
    p=argparse.ArgumentParser(description="Register v0.5 Phase1 commerce files into source_generation_run/source_file_manifest.")
    p.add_argument("--db-host", required=True); p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True); p.add_argument("--db-pass", required=True); p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True); p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", default="baseline"); p.add_argument("--scenario-id", default=None)
    p.add_argument("--source-generation-scenario", default="baseline"); p.add_argument("--scenario-family", default="journey_native")
    p.add_argument("--input-dir", required=True); p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--experiment-id", default=None); p.add_argument("--exogenous-snapshot-id", type=int, default=None)
    p.add_argument("--scenario-mode", default="source_injection"); p.add_argument("--source-mode", default="simulator_file_generate")
    p.add_argument("--exogenous-mode", default="timeline_db")
    return p.parse_args()

def conn(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def table_columns(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def line_count(path: Path) -> int:
    if path.suffix == ".json":
        return 1
    with path.open('r', encoding='utf-8', errors='replace') as f:
        return sum(1 for _ in f)

def insert_dynamic(cur, table, values):
    cols = [c for c in values if c in table_columns(cur, table)]
    if not cols:
        return None
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s']*len(cols))})"
    cur.execute(sql, tuple(values[c] for c in cols))
    return cur.lastrowid

def update_dynamic(cur, table, key_col, key_val, values):
    tcols=table_columns(cur, table)
    items=[(k,v) for k,v in values.items() if k in tcols]
    if not items: return
    cur.execute(f"UPDATE {table} SET {','.join([k+'=%s' for k,_ in items])} WHERE {key_col}=%s", tuple(v for _,v in items)+(key_val,))

def main():
    a=parse_args(); d=Path(a.input_dir)
    if not d.exists(): raise SystemExit(f"input-dir not found: {d}")
    files=[]
    for role, pat in ROLE_PATTERNS:
        for p in sorted(d.glob(pat)):
            files.append((role,p))
    # Also pick baseline-named files when logical scenario differs from source generation scenario.
    if not any(role == "behavior" for role,_ in files):
        for p in sorted(d.glob(f"*{a.source_generation_scenario}*behavior*.log")):
            files.append(("behavior", p))
    if not files: raise SystemExit(f"no Phase1 source files found in {d}")
    c=conn(a)
    try:
        with c.cursor() as cur:
            sgrid=a.source_gen_run_id
            scenario_id=a.scenario_id or a.scenario_name
            if not sgrid:
                vals={
                    "profile_id":a.profile_id,"target_date":a.target_date,"scenario_name":a.scenario_name,
                    "scenario_id":scenario_id,"scenario_mode":a.scenario_mode,"source_mode":a.source_mode,
                    "exogenous_mode":a.exogenous_mode,"simulator_version":"v05_commerce_phase1",
                    "generator_config_hash":hashlib.sha256(json.dumps({"scenario":a.scenario_name,"source_generation_scenario":a.source_generation_scenario,"family":a.scenario_family}, sort_keys=True).encode()).hexdigest(),
                    "status":"completed","ended_at":None,"created_by":"v05_commerce","note":f"scenario_family={a.scenario_family}; source_generation_scenario={a.source_generation_scenario}; experiment_id={a.experiment_id or ''}",
                    "experiment_id":a.experiment_id,
                }
                sgrid=insert_dynamic(cur,"source_generation_run",vals)
                if not sgrid:
                    raise RuntimeError("source_generation_run has no compatible columns")
            cur.execute("DELETE FROM source_file_manifest WHERE source_gen_run_id=%s", (sgrid,))
            inserted=0
            for role,p in files:
                vals={
                    "source_gen_run_id":sgrid,"exogenous_snapshot_id":a.exogenous_snapshot_id,
                    "profile_id":a.profile_id,"target_date":a.target_date,"service_domain":role,
                    "file_path":str(p),"file_name":p.name,"file_size_bytes":p.stat().st_size,
                    "checksum":sha(p),"record_count":line_count(p),"scenario_name":a.scenario_name,
                    "scenario_id":scenario_id,"source_generation_scenario":a.source_generation_scenario,
                }
                insert_dynamic(cur,"source_file_manifest",vals); inserted+=1
            update_dynamic(cur,"source_generation_run","source_gen_run_id",sgrid,{"status":"completed"})
        c.commit(); print(f"[register_phase1_source_files] source_gen_run_id={sgrid} files={inserted}"); print(sgrid)
    except Exception:
        c.rollback(); raise
    finally:
        c.close()
if __name__=='__main__': main()
