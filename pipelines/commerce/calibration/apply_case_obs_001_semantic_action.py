#!/usr/bin/env python3
from __future__ import annotations
import argparse
from datetime import datetime
import pymysql

ACTIONS=[
 (1,"wc collector validation","Validate WC collector drop/missing behavior by comparing WebServer source hits against WC collected hits for the same source_gen_run_id."),
 (2,"web-wc reconciliation check","Run WebServer vs WC reconciliation by URL, browser/OS, and journey stage before interpreting KPI decline as business demand drop."),
 (3,"observability KPI annotation","Annotate or suppress KPI decision dashboards for the affected date until collection completeness is recovered or explained."),
]
STATIC_RE = r"\\.(css|js|png|jpg|jpeg|gif|ico|map|woff|woff2|ttf|eot|svg|webp|zip|txt|xml|json)$"

def parse_args():
 p=argparse.ArgumentParser(description="CASE-OBS-001 resilient semantic/action overlay")
 p.add_argument("--db-host",default="127.0.0.1"); p.add_argument("--db-port",type=int,default=3306)
 p.add_argument("--db-user",required=True); p.add_argument("--db-pass",default=""); p.add_argument("--db-name",required=True)
 p.add_argument("--profile-id",required=True); p.add_argument("--target-date",required=True); p.add_argument("--scenario-name",default="source_wc_collection_missing")
 p.add_argument("--run-id",type=int,required=True); p.add_argument("--source-gen-run-id",type=int,required=True); p.add_argument("--min-gap-rate",type=float,default=0.05)
 return p.parse_args()

def connect(a):
 return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset="utf8mb4",autocommit=False,cursorclass=pymysql.cursors.DictCursor)

def cols(cur,t):
 cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",(t,)); return {r['column_name'] for r in cur.fetchall()}

def ensure_signal_table(cur):
 cur.execute("""CREATE TABLE IF NOT EXISTS v05_observability_signal_day (
  profile_id VARCHAR(64) NOT NULL,target_date DATE NOT NULL,scenario_name VARCHAR(128) NOT NULL,run_id BIGINT NULL,source_gen_run_id BIGINT NOT NULL,source_generation_scenario VARCHAR(128) NULL,web_hits BIGINT NOT NULL DEFAULT 0,wc_hits BIGINT NOT NULL DEFAULT 0,collection_gap_count BIGINT NOT NULL DEFAULT 0,collection_gap_rate DECIMAL(12,6) NOT NULL DEFAULT 0.000000,web_uv_ip BIGINT NOT NULL DEFAULT 0,wc_uv_pcid BIGINT NOT NULL DEFAULT 0,uv_gap_rate DECIMAL(12,6) NOT NULL DEFAULT 0.000000,checkout_web_hits BIGINT NOT NULL DEFAULT 0,checkout_wc_hits BIGINT NOT NULL DEFAULT 0,checkout_missing_rate DECIMAL(12,6) NOT NULL DEFAULT 0.000000,product_web_hits BIGINT NOT NULL DEFAULT 0,product_wc_hits BIGINT NOT NULL DEFAULT 0,product_missing_rate DECIMAL(12,6) NOT NULL DEFAULT 0.000000,observability_signal_score DECIMAL(12,6) NOT NULL DEFAULT 0.000000,observability_risk_level VARCHAR(32) NOT NULL DEFAULT 'low',dominant_observability_signal VARCHAR(128) NULL,recommended_semantic_risk VARCHAR(128) NULL,recommended_action_family VARCHAR(128) NULL,created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,PRIMARY KEY(profile_id,target_date,scenario_name,source_gen_run_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

def page_filter():
 return f"COALESCE(path, '') NOT REGEXP '{STATIC_RE}' AND (LOWER(COALESCE(evt,''))='view' OR COALESCE(page_type,'')<>'')"

def aggregate(cur,table,a,kind):
 tc=cols(cur,table)
 if not tc: return None
 where=["profile_id=%s","dt=%s"]; params=[a.profile_id,a.target_date]
 if 'source_gen_run_id' in tc: where.append("source_gen_run_id=%s"); params.append(a.source_gen_run_id)
 if kind=='web' and 'scenario_name' in tc: where.append("scenario_name=%s"); params.append(a.scenario_name)
 uv="COUNT(DISTINCT NULLIF(ip,''))" if kind=='web' else "COUNT(DISTINCT COALESCE(NULLIF(pcid,''),NULLIF(uid,''),NULLIF(ip,'')))"
 sql=f"SELECT COUNT(*) hits,{uv} uv,SUM(CASE WHEN LOWER(COALESCE(path,'')) LIKE '%checkout%' OR LOWER(COALESCE(path,'')) LIKE '%payment%' OR LOWER(COALESCE(path,'')) LIKE '%order%' THEN 1 ELSE 0 END) checkout_hits,SUM(CASE WHEN LOWER(COALESCE(path,'')) LIKE '%product%' THEN 1 ELSE 0 END) product_hits FROM {table} WHERE {' AND '.join(where)} AND {page_filter()}"
 cur.execute(sql,params); return cur.fetchone() or {}

def rg(a,b):
 a=int(a or 0); b=int(b or 0); return round(max(a-b,0)/float(a),6) if a>0 else 0.0

def level(s): return 'high' if s>=0.20 else 'warning' if s>=0.10 else 'review' if s>0 else 'low'

def build_signal_inline(cur,a):
 ensure_signal_table(cur)
 web=aggregate(cur,'stg_webserver_log_hit',a,'web'); wc=aggregate(cur,'stg_wc_log_hit',a,'wc')
 if not web or int(web.get('hits') or 0)<=0: return None
 wh,ch=int(web.get('hits') or 0), int((wc or {}).get('hits') or 0)
 wuv,cuv=int(web.get('uv') or 0), int((wc or {}).get('uv') or 0)
 wco,cco=int(web.get('checkout_hits') or 0), int((wc or {}).get('checkout_hits') or 0)
 wp,cp=int(web.get('product_hits') or 0), int((wc or {}).get('product_hits') or 0)
 g,ug,cg,pg=rg(wh,ch),rg(wuv,cuv),rg(wco,cco),rg(wp,cp); score=max(g,ug,cg,pg)
 risk='WC Collection Completeness Risk' if score>0 else 'None'
 row=dict(profile_id=a.profile_id,target_date=a.target_date,scenario_name=a.scenario_name,run_id=a.run_id,source_gen_run_id=a.source_gen_run_id,source_generation_scenario='baseline',web_hits=wh,wc_hits=ch,collection_gap_count=max(wh-ch,0),collection_gap_rate=g,web_uv_ip=wuv,wc_uv_pcid=cuv,uv_gap_rate=ug,checkout_web_hits=wco,checkout_wc_hits=cco,checkout_missing_rate=cg,product_web_hits=wp,product_wc_hits=cp,product_missing_rate=pg,observability_signal_score=score,observability_risk_level=level(score),dominant_observability_signal=risk,recommended_semantic_risk=risk,recommended_action_family='wc collector validation / web-wc reconciliation check / observability KPI annotation' if score>0 else 'no action')
 cur.execute("DELETE FROM v05_observability_signal_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND source_gen_run_id=%s",(a.profile_id,a.target_date,a.scenario_name,a.source_gen_run_id))
 cs=cols(cur,'v05_observability_signal_day'); ins=[k for k in row if k in cs]
 cur.execute(f"INSERT INTO v05_observability_signal_day ({','.join(ins)}) VALUES ({','.join(['%s']*len(ins))})",[row[k] for k in ins])
 return row

def fetch_signal(cur,a):
 ensure_signal_table(cur)
 # strict current run/source first
 cur.execute("SELECT * FROM v05_observability_signal_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND source_gen_run_id=%s ORDER BY CASE WHEN run_id=%s THEN 0 ELSE 1 END, COALESCE(run_id,0) DESC LIMIT 1",(a.profile_id,a.target_date,a.scenario_name,a.source_gen_run_id,a.run_id))
 sig=cur.fetchone()
 if sig: return sig
 # fallback latest same date/scenario
 cur.execute("SELECT * FROM v05_observability_signal_day WHERE profile_id=%s AND target_date=%s AND scenario_name=%s ORDER BY COALESCE(run_id,0) DESC, source_gen_run_id DESC LIMIT 1",(a.profile_id,a.target_date,a.scenario_name))
 sig=cur.fetchone()
 if sig: return sig
 return build_signal_inline(cur,a)

def update_semantic(cur,a,sig):
 cs=cols(cur,'semantic_interpretation_day_v05')
 if not cs: return 0
 upd={}
 if 'dominant_semantic_risk' in cs: upd['dominant_semantic_risk']='WC Collection Completeness Risk'
 if 'semantic_risk_family' in cs: upd['semantic_risk_family']='operational_observability_completeness'
 if 'completeness_score' in cs: upd['completeness_score']=max(float(sig.get('observability_signal_score') or 0),0.55)
 if 'consistency_score' in cs: upd['consistency_score']=max(float(sig.get('observability_signal_score') or 0)*0.7,0.35)
 if 'confidence_score' in cs: upd['confidence_score']=1.0
 if 'interpretation_confidence' in cs: upd['interpretation_confidence']=1.0
 if 'updated_at' in cs: upd['updated_at']=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
 if not upd: return 0
 where=['profile_id=%s','target_date=%s']; params=[a.profile_id,a.target_date]
 if 'run_id' in cs: where.append('run_id=%s'); params.append(a.run_id)
 if 'source_gen_run_id' in cs: where.append('source_gen_run_id=%s'); params.append(a.source_gen_run_id)
 if 'scenario_name' in cs: where.append('scenario_name=%s'); params.append(a.scenario_name)
 cur.execute(f"UPDATE semantic_interpretation_day_v05 SET {', '.join(k+'=%s' for k in upd)} WHERE {' AND '.join(where)}",list(upd.values())+params)
 return cur.rowcount

def rebuild_actions(cur,a):
 cs=cols(cur,'action_recommendation_day_v05')
 if not cs: return 0
 where=['profile_id=%s','target_date=%s']; params=[a.profile_id,a.target_date]
 if 'run_id' in cs: where.append('run_id=%s'); params.append(a.run_id)
 if 'source_gen_run_id' in cs: where.append('source_gen_run_id=%s'); params.append(a.source_gen_run_id)
 if 'scenario_name' in cs: where.append('scenario_name=%s'); params.append(a.scenario_name)
 cur.execute(f"DELETE FROM action_recommendation_day_v05 WHERE {' AND '.join(where)}",params)
 preferred=['profile_id','target_date','scenario_name','run_id','source_gen_run_id','action_rank','action_type','recommended_action','action_priority','action_reason','created_at']
 ins=[c for c in preferred if c in cs]; n=0
 for rank,typ,act in ACTIONS:
  row=dict(profile_id=a.profile_id,target_date=a.target_date,scenario_name=a.scenario_name,run_id=a.run_id,source_gen_run_id=a.source_gen_run_id,action_rank=rank,action_type=typ,recommended_action=act,action_priority='high' if rank==1 else 'medium',action_reason='CASE-OBS-001 collection_gap_rate exceeded threshold; do not interpret KPI drop as business decline before collection reconciliation.',created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
  cur.execute(f"INSERT INTO action_recommendation_day_v05 ({','.join(ins)}) VALUES ({','.join(['%s']*len(ins))})",[row[c] for c in ins]); n+=1
 return n

def main():
 a=parse_args(); conn=connect(a)
 try:
  with conn.cursor() as cur:
   sig=fetch_signal(cur,a)
   if not sig: raise RuntimeError('No observability signal could be built from stg_webserver_log_hit/stg_wc_log_hit')
   gap=float(sig.get('collection_gap_rate') or 0)
   if gap<a.min_gap_rate:
    print(f"[SKIP] collection_gap_rate={gap:.6f} below threshold={a.min_gap_rate:.6f}"); conn.commit(); return
   sr=update_semantic(cur,a,sig); ar=rebuild_actions(cur,a)
  conn.commit(); print(f"[OK] apply_case_obs_001_semantic_action gap={gap:.6f} semantic_rows={sr} action_rows={ar} semantic=WC Collection Completeness Risk")
 except Exception:
  conn.rollback(); raise
 finally: conn.close()
if __name__=='__main__': main()
