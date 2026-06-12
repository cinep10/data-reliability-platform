from __future__ import annotations
import json, math
from datetime import date, datetime
from decimal import Decimal
from typing import Any
import pymysql

def connect(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass, database=args.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)

def jdefault(v: Any) -> Any:
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, (datetime, date)): return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
    return str(v)

def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=jdefault, sort_keys=True)

def f(row, key, default=0.0):
    try: return float((row or {}).get(key, default) or 0)
    except Exception: return default

def s(row, key, default=""):
    v=(row or {}).get(key, default)
    return default if v is None else str(v)

def clamp01(x):
    try: return max(0.0, min(1.0, float(x)))
    except Exception: return 0.0

def sigmoid(x): return 1.0/(1.0+math.exp(-max(-40.0,min(40.0,x))))

def table_exists(cur, table):
    cur.execute("SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",(table,))
    return int(cur.fetchone()["cnt"])>0

def columns(cur, table):
    if not table_exists(cur, table): return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",(table,))
    return {str(r["column_name"]) for r in cur.fetchall()}

def scope_where(cols, args, include_source=True):
    wh=[]; ps=[]
    if "profile_id" in cols: wh.append("profile_id=%s"); ps.append(args.profile_id)
    if "target_date" in cols: wh.append("target_date=%s"); ps.append(args.target_date)
    elif "dt" in cols: wh.append("dt=%s"); ps.append(args.target_date)
    if "scenario_name" in cols and getattr(args,"scenario_name",None): wh.append("scenario_name=%s"); ps.append(args.scenario_name)
    if "run_id" in cols and getattr(args,"run_id",None) is not None: wh.append("run_id=%s"); ps.append(args.run_id)
    if include_source and "source_gen_run_id" in cols and getattr(args,"source_gen_run_id",None) is not None:
        wh.append("source_gen_run_id=%s"); ps.append(args.source_gen_run_id)
    return (" AND ".join(wh) if wh else "1=1", ps)

def fetch_one(cur, table, args, include_source=True):
    if not table_exists(cur, table): return {}
    cols=columns(cur, table); wh,ps=scope_where(cols,args,include_source)
    order_cols=[c for c in ["updated_at","created_at","run_id","source_gen_run_id","id"] if c in cols]
    order=" ORDER BY "+", ".join(f"{c} DESC" for c in order_cols) if order_cols else ""
    cur.execute(f"SELECT * FROM `{table}` WHERE {wh}{order} LIMIT 1", tuple(ps))
    return cur.fetchone() or {}

def delete_scoped(cur, table, args, include_source=True):
    if not table_exists(cur, table): return
    cols=columns(cur, table); wh,ps=scope_where(cols,args,include_source)
    cur.execute(f"DELETE FROM `{table}` WHERE {wh}", tuple(ps))

def insert_dict(cur, table, row):
    keys=list(row.keys())
    cur.execute(f"INSERT INTO `{table}` ("+",".join(f"`{k}`" for k in keys)+") VALUES ("+",".join(["%s"]*len(keys))+")", tuple(row[k] for k in keys))
