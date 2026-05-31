#!/usr/bin/env python3
import argparse, pymysql
RULES={
 "Completeness":("ingestion validation","source/batch/stream completeness degradation","P2"),
 "Timeliness":("queue/backlog check","stream or operational timeliness degradation","P2"),
 "Integrity":("reconciliation","schema/contract/integrity drift","P1"),
 "Consistency":("mapping validation","cross-layer consistency mismatch","P2"),
 "Availability":("retry/timeout tuning","no-data or availability degradation","P1"),
 "None":("no action","stable baseline","P4"),
 "Unknown":("manual investigation","unknown reliability risk","P3"),
}
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--db-host",default="127.0.0.1"); ap.add_argument("--db-port",type=int,default=3306); ap.add_argument("--db-user",required=True); ap.add_argument("--db-pass",required=True); ap.add_argument("--db-name",required=True)
 ap.add_argument("--profile-id",required=True); ap.add_argument("--dt",required=True); ap.add_argument("--run-id",default=""); ap.add_argument("--scenario-name",default="")
 args=ap.parse_args()
 cn=pymysql.connect(host=args.db_host,port=args.db_port,user=args.db_user,password=args.db_pass,database=args.db_name,charset="utf8mb4",autocommit=False,cursorclass=pymysql.cursors.DictCursor)
 try:
  with cn.cursor() as cur:
   cur.execute("SELECT dominant_semantic_risk,semantic_confidence,delta_source_type FROM semantic_interpretation_day WHERE profile_id=%s AND dt=%s AND run_id=%s LIMIT 1",(args.profile_id,args.dt,args.run_id))
   row=cur.fetchone() or {}
   dom=row.get("dominant_semantic_risk") or "Unknown"; conf=float(row.get("semantic_confidence") or 0); delta=row.get("delta_source_type") or "UNKNOWN"
   action,root,priority=RULES.get(dom,RULES["Unknown"])
   if dom=="None" or conf<=0.0001: action,root,priority=RULES["None"]; align=1.0
   else: align=conf
   reason=f"rule_based_phase3_action dominant={dom}; confidence={conf:.4f}; delta_source_type={delta}"
   cur.execute("DELETE FROM action_recommendation_day WHERE profile_id=%s AND dt=%s AND run_id=%s",(args.profile_id,args.dt,args.run_id))
   cur.execute("""INSERT INTO action_recommendation_day
    (profile_id,dt,run_id,scenario_name,dominant_semantic_risk,recommended_action,priority,root_cause_direction,risk_alignment_score,delta_source_type,action_reason)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(args.profile_id,args.dt,args.run_id,args.scenario_name,dom,action,priority,root,align,delta,reason))
  cn.commit()
 finally:
  cn.close()
 print(f"[ACTION_COMPLETION] scenario={args.scenario_name} dominant={dom} action={action} priority={priority} delta_source_type={delta}")
if __name__=="__main__": main()
