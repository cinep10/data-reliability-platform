#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common_v04 import add_db_args, connect, ACTION_MAP

def main():
    p=argparse.ArgumentParser(); add_db_args(p); args=p.parse_args()
    conn=connect(args)
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM ai_incident_context_day_v04 WHERE profile_id=%s AND dt BETWEEN %s AND %s ORDER BY dt, run_id", (args.profile_id,args.dt_from,args.dt_to))
        rows=cur.fetchall()
        if not rows: raise RuntimeError('missing ai_incident_context_day_v04 rows')
        cur.execute("DELETE FROM ai_recommended_action_day_v04 WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id,args.dt_from,args.dt_to))
        vals=[]
        for r in rows:
            dom=r.get('dominant_semantic_risk')
            rule=r.get('recommended_action') or ACTION_MAP.get(dom,'no action')
            exp=f"{dom or 'None'} risk에 대해 Phase3 rule action '{rule}'을 운영자가 수행하도록 설명합니다. AI는 action을 새로 창작하지 않고 Phase3 action_recommendation_day의 결과를 설명만 합니다."
            status='ALIGNED' if (rule == ACTION_MAP.get(dom, rule) or dom in (None,'None')) else 'CHECK'
            vals.append((r['profile_id'],r['dt'],r['run_id'],r.get('scenario_name'),dom,rule,exp,status))
        cur.executemany("""
        INSERT INTO ai_recommended_action_day_v04
        (profile_id,dt,run_id,scenario_name,dominant_semantic_risk,rule_recommended_action,ai_action_explanation,action_alignment_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE ai_action_explanation=VALUES(ai_action_explanation), action_alignment_status=VALUES(action_alignment_status), created_at=CURRENT_TIMESTAMP
        """, vals)
    conn.commit(); conn.close(); print(f"[OK] built ai_recommended_action_day_v04 rows={len(rows)}")
if __name__=='__main__': main()
