#!/usr/bin/env python3
from __future__ import annotations
import argparse, statistics
from datetime import datetime,timedelta
import pymysql


def parse_args():
    p=argparse.ArgumentParser(description='Build baseline distribution snapshots from batch_behavior_distribution_day history.')
    p.add_argument('--db-host',default='127.0.0.1'); p.add_argument('--db-port',type=int,default=3306)
    p.add_argument('--db-user',required=True); p.add_argument('--db-pass',default=''); p.add_argument('--db-name',required=True)
    p.add_argument('--profile-id',required=True); p.add_argument('--target-date',required=True); p.add_argument('--baseline-window',default='30d')
    p.add_argument('--baseline-scenario',default='baseline'); p.add_argument('--include-target-date',action='store_true'); p.add_argument('--truncate-target',action='store_true')
    return p.parse_args()

def conn(a): return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor,autocommit=False)
def days(w): return int(w[:-1]) if w.endswith('d') and w[:-1].isdigit() else 30
def table_exists(cur,t):
    cur.execute("SELECT COUNT(*) c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",(t,)); return int(cur.fetchone()['c'] or 0)>0
def cols(cur,t):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",(t,)); return {r['column_name'] for r in cur.fetchall()}
def pct(vals,p):
    vals=sorted(vals)
    if not vals: return None
    k=(len(vals)-1)*p; f=int(k); c=min(f+1,len(vals)-1)
    return vals[f] if f==c else vals[f]*(c-k)+vals[c]*(k-f)
def ins_schema_aware(cur, table, ordered, rows):
    if not rows: return 0
    cc=cols(cur,table); actual=[c for c in ordered if c in cc]
    idx=[ordered.index(c) for c in actual]
    vals=[tuple(r[i] for i in idx) for r in rows]
    cur.executemany(f"INSERT INTO {table} ({','.join(actual)}) VALUES ({','.join(['%s']*len(actual))})", vals)
    return len(vals)

def main():
    a=parse_args(); target=datetime.strptime(a.target_date,'%Y-%m-%d').date(); start=target-timedelta(days=days(a.baseline_window)); end=target if a.include_target_date else target-timedelta(days=1)
    c=conn(a)
    try:
        with c.cursor() as cur:
            if not table_exists(cur,'batch_behavior_distribution_day') or not table_exists(cur,'v05_baseline_distribution_snapshot_day'):
                print('[WARN] required tables missing; baseline distribution snapshot skipped'); c.commit(); return
            if a.truncate_target:
                cur.execute("DELETE FROM v05_baseline_distribution_snapshot_day WHERE profile_id=%s AND target_date=%s AND baseline_window=%s",(a.profile_id,a.target_date,a.baseline_window))
            bcols=cols(cur,'batch_behavior_distribution_day')
            count_col='event_count' if 'event_count' in bcols else 'current_count'
            ratio_col='event_ratio' if 'event_ratio' in bcols else ('ratio_value' if 'ratio_value' in bcols else 'current_ratio')
            where=["profile_id=%s","dt BETWEEN %s AND %s"]; params=[a.profile_id,start.isoformat(),end.isoformat()]
            if 'scenario_name' in bcols:
                where.append("COALESCE(scenario_name,'baseline')=%s"); params.append(a.baseline_scenario)
            cur.execute(f"""SELECT dt,dimension_name,dimension_value,{count_col} AS event_count,{ratio_col} AS event_ratio
                           FROM batch_behavior_distribution_day WHERE {' AND '.join(where)}""", tuple(params))
            by={}
            for r in cur.fetchall():
                key=(r['dimension_name'],r['dimension_value'])
                by.setdefault(key,{'cnt':[],'ratios':[],'days':set()})
                by[key]['cnt'].append(float(r['event_count'] or 0)); by[key]['ratios'].append(float(r['event_ratio'] or 0)); by[key]['days'].add(r['dt'])
            rows=[]
            for (dim,val),v in by.items():
                cnt=v['cnt']; ratios=v['ratios']; n=len(v['days'])
                rows.append((a.profile_id,a.target_date,a.baseline_window,'calendar_baseline',a.baseline_scenario,dim,val,
                             sum(cnt)/len(cnt), statistics.pstdev(cnt) if len(cnt)>1 else 0.0,
                             sum(ratios)/len(ratios), statistics.pstdev(ratios) if len(ratios)>1 else 0.0,
                             pct(ratios,.5), pct(ratios,.95), n, 'batch_behavior_distribution_day'))
            ordered=['profile_id','target_date','baseline_window','baseline_type','source_scenario','dimension_name','dimension_value','baseline_count_avg','baseline_count_std','baseline_ratio_avg','baseline_ratio_std','baseline_ratio_p50','baseline_ratio_p95','sample_days','source_table']
            inserted=ins_schema_aware(cur,'v05_baseline_distribution_snapshot_day',ordered,rows)
        c.commit(); print(f"[OK] build_v05_baseline_distribution_snapshot_day target={a.target_date} window={a.baseline_window} rows={inserted} range={start}..{end}")
    except Exception:
        c.rollback(); raise
    finally: c.close()
if __name__=='__main__': main()
