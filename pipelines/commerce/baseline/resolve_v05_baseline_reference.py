#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pymysql

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument('--db-host',default='127.0.0.1'); p.add_argument('--db-port',type=int,default=3306)
    p.add_argument('--db-user',required=True); p.add_argument('--db-pass',default=''); p.add_argument('--db-name',required=True)
    p.add_argument('--profile-id',required=True); p.add_argument('--target-date',required=True); p.add_argument('--scenario-name',required=True)
    p.add_argument('--baseline-mode',default='temporal_baseline'); p.add_argument('--baseline-window',default='30d')
    p.add_argument('--format',choices=['json','shell'],default='json')
    return p.parse_args()

def main():
    a=parse_args()
    con=pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor,autocommit=True)
    with con:
        cur=con.cursor()
        cur.execute("""SELECT COUNT(*) c FROM v05_baseline_metric_snapshot_day
                       WHERE profile_id=%s AND target_date=%s AND baseline_window=%s""",(a.profile_id,a.target_date,a.baseline_window))
        available=int(cur.fetchone()['c'])>0
        policy='same_run_evidence_baseline' if a.scenario_name=='source_wc_collection_missing' else ('use_baseline_snapshot' if available else 'BASELINE_MISSING_REVIEW')
        cur.execute("""REPLACE INTO v05_baseline_reference_run_day
          (profile_id,target_date,scenario_name,baseline_mode,baseline_window,baseline_available,baseline_snapshot_date,fallback_policy,analysis_confidence)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(a.profile_id,a.target_date,a.scenario_name,a.baseline_mode,a.baseline_window,1 if available else 0,a.target_date if available else None,policy,'high' if available or policy=='same_run_evidence_baseline' else 'low'))
    d={'baseline_mode':a.baseline_mode,'baseline_window':a.baseline_window,'baseline_available':available,'fallback_policy':policy}
    if a.format=='shell':
        for k,v in d.items(): print(f"{k.upper()}='{str(v).lower() if isinstance(v,bool) else v}'")
    else: print(json.dumps(d,ensure_ascii=False))
if __name__=='__main__': main()
