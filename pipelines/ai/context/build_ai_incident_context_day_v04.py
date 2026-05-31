#!/usr/bin/env python3
import argparse
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common_v04 import add_db_args, connect, rows_for_context, jdump

def main():
    p=argparse.ArgumentParser()
    add_db_args(p)
    args=p.parse_args()
    conn=connect(args)
    with conn.cursor() as cur:
        rows=rows_for_context(cur,args.profile_id,args.dt_from,args.dt_to)
        if not rows:
            raise RuntimeError('no Phase3 decision rows found')
        cur.execute("DELETE FROM ai_incident_context_day_v04 WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id,args.dt_from,args.dt_to))
        vals=[]
        for r in rows:
            meas={k:r.get(k) for k in ['direct_completeness_delta','direct_timeliness_delta','direct_availability_delta','direct_integrity_delta','delta_source_type','measurement_realism_status']}
            analysis={k:r.get(k) for k in ['drift_score','propagation_score','amplification_score','distortion_score','baseline_delta','correlation_score']}
            action={k:r.get(k) for k in ['recommended_action','priority']}
            ml={k:r.get(k) for k in ['predicted_semantic_risk','ml_risk_score','ml_risk_grade','score_gap']}
            ctx={'measurement':meas,'analysis':analysis,'semantic':{k:r.get(k) for k in ['dominant_semantic_risk','final_risk_level','overall_risk_score','semantic_confidence']},'action':action,'ml':ml}
            vals.append((r['profile_id'],r['dt'],str(r.get('run_id') or '1'),r.get('scenario_name'),r.get('dominant_semantic_risk'),r.get('final_risk_level'),r.get('overall_risk_score') or 0,r.get('recommended_action'),r.get('priority'),r.get('predicted_semantic_risk'),r.get('ml_risk_score'),r.get('score_gap'),jdump(meas),jdump(analysis),jdump(action),jdump(ml),jdump(ctx)))
        cur.executemany("""
        INSERT INTO ai_incident_context_day_v04
        (profile_id,dt,run_id,scenario_name,dominant_semantic_risk,final_risk_level,overall_risk_score,recommended_action,priority,predicted_semantic_risk,ml_risk_score,score_gap,measurement_evidence_json,analysis_evidence_json,action_evidence_json,ml_evidence_json,context_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE final_risk_level=VALUES(final_risk_level), overall_risk_score=VALUES(overall_risk_score), context_json=VALUES(context_json), created_at=CURRENT_TIMESTAMP
        """, vals)
    conn.commit(); conn.close()
    print(f"[OK] built ai_incident_context_day_v04 rows={len(rows)}")
if __name__=='__main__': main()
