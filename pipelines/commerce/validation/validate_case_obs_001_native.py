#!/usr/bin/env python3
from __future__ import annotations
import argparse,sys,pymysql

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument('--db-host',default='127.0.0.1'); p.add_argument('--db-port',type=int,default=3306); p.add_argument('--db-user',required=True); p.add_argument('--db-pass',default=''); p.add_argument('--db-name',required=True)
    p.add_argument('--profile-id',required=True); p.add_argument('--target-date',required=True); p.add_argument('--scenario-name',default='source_wc_collection_missing')
    p.add_argument('--run-id',type=int); p.add_argument('--source-gen-run-id',type=int); p.add_argument('--min-gap-rate',type=float,default=0.05)
    return p.parse_args()
def conn(a): return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor,autocommit=True)
def table_exists(cur,t): cur.execute('SELECT COUNT(*) c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s',(t,)); return int(cur.fetchone()['c'])>0
def cols(cur,t): cur.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s',(t,)); return {r['column_name'] for r in cur.fetchall()}
def latest_ids(cur,a):
    rid=a.run_id; sid=a.source_gen_run_id
    if sid is None and table_exists(cur,'stg_webserver_log_hit') and 'scenario_name' in cols(cur,'stg_webserver_log_hit'):
        cur.execute('SELECT MAX(source_gen_run_id) sid FROM stg_webserver_log_hit WHERE profile_id=%s AND dt=%s AND scenario_name=%s',(a.profile_id,a.target_date,a.scenario_name)); sid=cur.fetchone()['sid']
    if rid is None:
        cur.execute('SELECT MAX(run_id) rid FROM semantic_interpretation_day_v05 WHERE profile_id=%s AND target_date=%s AND scenario_name=%s',(a.profile_id,a.target_date,a.scenario_name)); rid=cur.fetchone()['rid']
    return rid,sid
def check(name,ok,val=''):
    print(f'{name}: {"PASS" if ok else "FAIL"}' + (f' ({val})' if val!='' else '')); return ok
def main():
    a=parse_args(); fails=[]
    with conn(a) as c:
        cur=c.cursor(); rid,sid=latest_ids(cur,a)
        if not rid: print('[FAIL] no run_id found'); return 1
        print(f'[INFO] validate run_id={rid} source_gen_run_id={sid}')
        cur.execute('SELECT * FROM v05_wc_collection_reconciliation_day WHERE profile_id=%s AND target_date=%s AND run_id=%s AND scenario_name=%s',(a.profile_id,a.target_date,rid,a.scenario_name)); obs=cur.fetchone()
        cur.execute('SELECT dominant_semantic_risk FROM semantic_interpretation_day_v05 WHERE profile_id=%s AND target_date=%s AND run_id=%s AND scenario_name=%s',(a.profile_id,a.target_date,rid,a.scenario_name)); sem=cur.fetchone()
        cur.execute('SELECT COUNT(*) c FROM action_recommendation_day_v05 WHERE profile_id=%s AND target_date=%s AND run_id=%s AND scenario_name=%s AND action_type IN ("wc collector validation","web-wc reconciliation check","observability KPI annotation")',(a.profile_id,a.target_date,rid,a.scenario_name)); ac=cur.fetchone()['c']
        if not obs: print('[FAIL] no observability reconciliation row'); return 1
        fails.append(not check('web_hits_positive', int(obs.get('web_hits') or 0)>0, obs.get('web_hits')))
        fails.append(not check('wc_hits_lower_than_web', int(obs.get('wc_hits') or 0) < int(obs.get('web_hits') or 0), f"web={obs.get('web_hits')} wc={obs.get('wc_hits')}"))
        fails.append(not check('collection_gap_rate_threshold', float(obs.get('collection_gap_rate') or 0)>=a.min_gap_rate, obs.get('collection_gap_rate')))
        fails.append(not check('semantic_observability', sem and sem.get('dominant_semantic_risk') in ('WC Collection Completeness Risk','Operational Observability Distortion','False KPI Degradation Risk'), sem.get('dominant_semantic_risk') if sem else None))
        fails.append(not check('observability_actions', int(ac)>=2, ac))
    if any(fails): print('[FAIL] CASE-OBS-001 native validation failed'); return 1
    print('[OK] CASE-OBS-001 native validation passed'); return 0
if __name__=='__main__': sys.exit(main())
