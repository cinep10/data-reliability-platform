#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common_v04 import add_db_args, connect

def clamp(x):
    try: return max(0.0,min(1.0,float(x)))
    except Exception: return 1.0

def main():
    p=argparse.ArgumentParser(); add_db_args(p); args=p.parse_args()
    conn=connect(args)
    with conn.cursor() as cur:
        cur.execute("""
        SELECT c.profile_id,c.dt,c.run_id,c.scenario_name,c.dominant_semantic_risk,c.final_risk_level,
               iv.validated_output_source,iv.llm_execution_id,iv.provider,iv.model,iv.fallback_used,iv.api_status,
               iv.signal_match_score,iv.semantic_match_score,iv.evidence_match_score,iv.measurement_reference_score,
               av.action_match_score,av.wrong_action_flag,h.hallucination_score,h.hallucination_flag
        FROM ai_incident_context_day_v04 c
        JOIN ai_interpretation_validation_day iv ON iv.profile_id=c.profile_id AND iv.dt=c.dt AND iv.run_id=c.run_id
        JOIN ai_action_validation_day av ON av.profile_id=c.profile_id AND av.dt=c.dt AND av.run_id=c.run_id
        JOIN ai_hallucination_check_day h ON h.profile_id=c.profile_id AND h.dt=c.dt AND h.run_id=c.run_id
        WHERE c.profile_id=%s AND c.dt BETWEEN %s AND %s ORDER BY c.dt,c.run_id
        """, (args.profile_id,args.dt_from,args.dt_to))
        rows=cur.fetchall()
        if not rows: raise RuntimeError('missing AI validation rows')
        cur.execute("DELETE FROM ai_reliability_score_day WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id,args.dt_from,args.dt_to))
        vals=[]
        for r in rows:
            interp_risk=1.0-((clamp(r['signal_match_score'])+clamp(r['semantic_match_score']))/2.0)
            evidence_risk=1.0-((clamp(r['evidence_match_score'])+clamp(r['measurement_reference_score']))/2.0)
            action_risk=1.0-clamp(r['action_match_score'])
            hallucination_risk=clamp(r['hallucination_score'])
            overall=round(0.30*interp_risk+0.30*evidence_risk+0.25*action_risk+0.15*hallucination_risk,6)
            status='PASS' if overall<=0.15 else 'WARN' if overall<=0.35 else 'FAIL'
            reason=f"source={r.get('validated_output_source')}; interpretation_risk={interp_risk:.3f}; evidence_risk={evidence_risk:.3f}; action_risk={action_risk:.3f}; hallucination_risk={hallucination_risk:.3f}"
            vals.append((r['profile_id'],r['dt'],str(r.get('run_id') or '1'),r.get('scenario_name'),r.get('dominant_semantic_risk'),r.get('final_risk_level'),
                         r.get('validated_output_source') or 'FALLBACK',r.get('llm_execution_id'),r.get('provider'),r.get('model'),r.get('fallback_used') if r.get('fallback_used') is not None else 1,r.get('api_status'),
                         interp_risk,evidence_risk,action_risk,hallucination_risk,overall,status,reason))
        cur.executemany("""
        INSERT INTO ai_reliability_score_day
        (profile_id,dt,run_id,scenario_name,dominant_semantic_risk,final_risk_level,validated_output_source,llm_execution_id,provider,model,fallback_used,api_status,
         interpretation_risk,evidence_risk,action_risk,hallucination_risk,overall_ai_risk_score,validation_status,validation_reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          validated_output_source=VALUES(validated_output_source), llm_execution_id=VALUES(llm_execution_id), provider=VALUES(provider), model=VALUES(model), fallback_used=VALUES(fallback_used), api_status=VALUES(api_status),
          interpretation_risk=VALUES(interpretation_risk), evidence_risk=VALUES(evidence_risk), action_risk=VALUES(action_risk), hallucination_risk=VALUES(hallucination_risk),
          overall_ai_risk_score=VALUES(overall_ai_risk_score), validation_status=VALUES(validation_status), validation_reason=VALUES(validation_reason), created_at=CURRENT_TIMESTAMP
        """, vals)
    conn.commit(); conn.close()
    src_counts={}
    for v in vals: src_counts[v[6]]=src_counts.get(v[6],0)+1
    print(f"[OK] built ai_reliability_score_day rows={len(rows)} sources={src_counts}")
if __name__=='__main__': main()
