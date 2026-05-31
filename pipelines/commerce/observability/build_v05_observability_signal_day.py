#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from typing import Any
import pymysql

STATIC_RE = r"\\.(css|js|png|jpg|jpeg|gif|ico|map|woff|woff2|ttf|eot|svg|webp|zip|txt|xml|json)$"

def parse_args():
    p=argparse.ArgumentParser(description="Build CASE-OBS-001 WebServer vs WC signal directly from stage tables")
    p.add_argument("--db-host",default="127.0.0.1"); p.add_argument("--db-port",type=int,default=3306)
    p.add_argument("--db-user",required=True); p.add_argument("--db-pass",default=""); p.add_argument("--db-name",required=True)
    p.add_argument("--profile-id",required=True); p.add_argument("--target-date",required=True); p.add_argument("--scenario-name",required=True)
    p.add_argument("--run-id",required=True); p.add_argument("--source-gen-run-id",required=True); p.add_argument("--truncate-target",action="store_true")
    a=p.parse_args()
    for attr in ("run_id","source_gen_run_id"):
        raw=getattr(a,attr)
        if raw is None or str(raw).strip()=="" or str(raw).upper()=="NULL":
            p.error(f"--{attr.replace('_','-')} must be a real integer, not {raw!r}")
        try: setattr(a,attr,int(raw))
        except ValueError: p.error(f"--{attr.replace('_','-')} must be a real integer, not {raw!r}")
    return a

def connect(a):
    return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset="utf8mb4",autocommit=False,cursorclass=pymysql.cursors.DictCursor)

def table_cols(cur,t):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",(t,))
    return {r["column_name"] for r in cur.fetchall()}

def ensure_table(cur):
    cur.execute("""
CREATE TABLE IF NOT EXISTS v05_observability_signal_day (
  profile_id VARCHAR(64) NOT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  run_id BIGINT NULL,
  source_gen_run_id BIGINT NOT NULL,
  source_generation_scenario VARCHAR(128) NULL,
  web_hits BIGINT NOT NULL DEFAULT 0,
  wc_hits BIGINT NOT NULL DEFAULT 0,
  collection_gap_count BIGINT NOT NULL DEFAULT 0,
  collection_gap_rate DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
  web_uv_ip BIGINT NOT NULL DEFAULT 0,
  wc_uv_pcid BIGINT NOT NULL DEFAULT 0,
  uv_gap_rate DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
  checkout_web_hits BIGINT NOT NULL DEFAULT 0,
  checkout_wc_hits BIGINT NOT NULL DEFAULT 0,
  checkout_missing_rate DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
  product_web_hits BIGINT NOT NULL DEFAULT 0,
  product_wc_hits BIGINT NOT NULL DEFAULT 0,
  product_missing_rate DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
  observability_signal_score DECIMAL(12,6) NOT NULL DEFAULT 0.000000,
  observability_risk_level VARCHAR(32) NOT NULL DEFAULT 'low',
  dominant_observability_signal VARCHAR(128) NULL,
  recommended_semantic_risk VARCHAR(128) NULL,
  recommended_action_family VARCHAR(128) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY(profile_id, target_date, scenario_name, source_gen_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

def page_filter():
    return f"COALESCE(path, '') NOT REGEXP '{STATIC_RE}' AND (LOWER(COALESCE(evt, ''))='view' OR COALESCE(page_type, '') <> '')"

def aggregate(cur, table, a, kind):
    cols=table_cols(cur,table)
    if not cols: raise RuntimeError(f"table not found: {table}")
    where=["profile_id=%s", "dt=%s"]
    params=[a.profile_id,a.target_date]
    if "source_gen_run_id" in cols:
        where.append("source_gen_run_id=%s"); params.append(a.source_gen_run_id)
    if kind=="web" and "scenario_name" in cols:
        where.append("scenario_name=%s"); params.append(a.scenario_name)
    uv="COUNT(DISTINCT NULLIF(ip,''))" if kind=="web" else "COUNT(DISTINCT COALESCE(NULLIF(pcid,''),NULLIF(uid,''),NULLIF(ip,'')))"
    sql=f"""
SELECT COUNT(*) hits, {uv} uv,
  SUM(CASE WHEN LOWER(COALESCE(path,'')) LIKE '%%checkout%%' OR LOWER(COALESCE(path,'')) LIKE '%%payment%%' OR LOWER(COALESCE(path,'')) LIKE '%%order%%' THEN 1 ELSE 0 END) checkout_hits,
  SUM(CASE WHEN LOWER(COALESCE(path,'')) LIKE '%%product%%' THEN 1 ELSE 0 END) product_hits
FROM {table}
WHERE {' AND '.join(where)} AND {page_filter()}
"""
    cur.execute(sql,params)
    return cur.fetchone() or {}

def gap(a,b):
    a=int(a or 0); b=int(b or 0)
    return round(max(a-b,0)/float(a),6) if a>0 else 0.0

def lvl(score):
    return "high" if score>=0.20 else "warning" if score>=0.10 else "review" if score>0 else "low"

def build_signal(cur,a):
    ensure_table(cur)
    if a.truncate_target:
        cur.execute("DELETE FROM v05_observability_signal_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND source_gen_run_id=%s",(a.profile_id,a.target_date,a.scenario_name,a.source_gen_run_id))
    web=aggregate(cur,"stg_webserver_log_hit",a,"web"); wc=aggregate(cur,"stg_wc_log_hit",a,"wc")
    wh, ch = int(web.get("hits") or 0), int(wc.get("hits") or 0)
    if wh<=0: raise RuntimeError(f"no WebServer source rows found for profile={a.profile_id} dt={a.target_date} scenario={a.scenario_name} source_gen_run_id={a.source_gen_run_id}")
    wuv,cuv=int(web.get("uv") or 0), int(wc.get("uv") or 0)
    wco,cco=int(web.get("checkout_hits") or 0), int(wc.get("checkout_hits") or 0)
    wp,cp=int(web.get("product_hits") or 0), int(wc.get("product_hits") or 0)
    g,ug,cg,pg=gap(wh,ch),gap(wuv,cuv),gap(wco,cco),gap(wp,cp)
    score=max(g,ug,cg,pg)
    risk="WC Collection Completeness Risk" if score>0 else "None"
    action="wc collector validation / web-wc reconciliation check / observability KPI annotation" if score>0 else "no action"
    row=dict(profile_id=a.profile_id,target_date=a.target_date,scenario_name=a.scenario_name,run_id=a.run_id,source_gen_run_id=a.source_gen_run_id,source_generation_scenario="baseline",web_hits=wh,wc_hits=ch,collection_gap_count=max(wh-ch,0),collection_gap_rate=g,web_uv_ip=wuv,wc_uv_pcid=cuv,uv_gap_rate=ug,checkout_web_hits=wco,checkout_wc_hits=cco,checkout_missing_rate=cg,product_web_hits=wp,product_wc_hits=cp,product_missing_rate=pg,observability_signal_score=score,observability_risk_level=lvl(score),dominant_observability_signal=risk,recommended_semantic_risk=risk,recommended_action_family=action)
    cols=table_cols(cur,"v05_observability_signal_day")
    ins=[k for k in row if k in cols]
    cur.execute(f"INSERT INTO v05_observability_signal_day ({','.join(ins)}) VALUES ({','.join(['%s']*len(ins))})",[row[k] for k in ins])
    return row

def main():
    a=parse_args(); conn=connect(a)
    try:
        with conn.cursor() as cur:
            row=build_signal(cur,a)
        conn.commit()
        print(f"[OK] build_v05_observability_signal_day scenario={a.scenario_name} run_id={a.run_id} source_gen_run_id={a.source_gen_run_id} web_hits={row['web_hits']} wc_hits={row['wc_hits']} gap={row['collection_gap_rate']:.6f} score={row['observability_signal_score']:.6f} level={row['observability_risk_level']}")
    except Exception as e:
        conn.rollback(); print(f"[ERROR] build_v05_observability_signal_day failed: {e}",file=sys.stderr); raise
    finally:
        conn.close()
if __name__=='__main__': main()
