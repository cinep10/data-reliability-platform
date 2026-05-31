#!/usr/bin/env python3
from __future__ import annotations
import argparse, pymysql, sys

def parse_args():
    p=argparse.ArgumentParser(description='Validate baseline stays stable/no-action after native baseline refactor.')
    p.add_argument('--db-host',required=True); p.add_argument('--db-port',type=int,required=True); p.add_argument('--db-user',required=True); p.add_argument('--db-pass',required=True); p.add_argument('--db-name',required=True)
    p.add_argument('--profile-id',required=True); p.add_argument('--target-date',required=True); p.add_argument('--run-id',type=int,required=True); p.add_argument('--source-gen-run-id',type=int,default=None)
    p.add_argument('--max-score',type=float,default=0.08)
    return p.parse_args()

def conn(a): return pymysql.connect(host=a.db_host,port=a.db_port,user=a.db_user,password=a.db_pass,database=a.db_name,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor)

def one(cur,sql,p): cur.execute(sql,p); return cur.fetchone() or {}

def main():
    a=parse_args(); c=conn(a)
    try:
        with c.cursor() as cur:
            u=one(cur,"SELECT overall_risk_score,final_risk_level FROM unified_reliability_score_day_v05 WHERE profile_id=%s AND target_date=%s AND run_id=%s",(a.profile_id,a.target_date,a.run_id))
            s=one(cur,"SELECT dominant_semantic_risk FROM semantic_interpretation_day_v05 WHERE profile_id=%s AND target_date=%s AND run_id=%s",(a.profile_id,a.target_date,a.run_id))
            act=one(cur,"SELECT COUNT(*) cnt, GROUP_CONCAT(recommended_action ORDER BY action_rank SEPARATOR '; ') actions FROM action_recommendation_day_v05 WHERE profile_id=%s AND target_date=%s AND run_id=%s AND recommended_action <> 'no action'",(a.profile_id,a.target_date,a.run_id))
            score=float(u.get('overall_risk_score') or 0); level=str(u.get('final_risk_level') or ''); dom=str(s.get('dominant_semantic_risk') or 'None'); ac=int(act.get('cnt') or 0)
            ok=score<=a.max_score and level in {'stable','low'} and dom in {'None','none','','NULL'} and ac==0
            print(f"[BASELINE_NO_FALSE_POSITIVE] score={score:.6f} level={level} dominant={dom} false_actions={ac} status={'PASS' if ok else 'FAIL'}")
            if not ok:
                print(f"[DETAIL] actions={act.get('actions')}")
                return 1
            return 0
    finally:
        c.close()
if __name__=='__main__': sys.exit(main())
