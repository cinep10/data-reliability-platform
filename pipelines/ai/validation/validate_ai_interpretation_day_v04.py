#!/usr/bin/env python3
import argparse, json, re, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common_v04 import add_db_args, connect

RISK_TERMS = {
    'Completeness': ['completeness', 'missing', '누락', '결측', 'ingestion', 'partial'],
    'Timeliness': ['timeliness', 'latency', 'delay', 'backlog', '지연', '대기열'],
    'Availability': ['availability', 'no data', 'unavailable', '가용성', '무데이터', 'timeout'],
    'Integrity': ['integrity', 'schema', 'reconciliation', '무결성', '스키마', '정합성'],
    'Consistency': ['consistency', 'mapping', 'identity', '일관성', '매핑', '식별자'],
    'None': ['stable', 'normal', 'no action', '정상', '안정']
}
EVIDENCE_TERMS = ['delta', 'score', 'measurement', 'direct_', 'completeness_delta', 'timeliness_delta', 'availability_delta', 'integrity_delta', 'propagation', '측정', '근거', '점수']

def jloads(x):
    try:
        return json.loads(x) if isinstance(x, str) and x else (x or {})
    except Exception:
        return {}

def score_bool(x):
    return 1.0 if x else 0.0

def norm(s):
    return (s or '').strip()

def choose_llm(row, llm_by_key):
    key=(row['profile_id'], str(row['dt']))
    llm=llm_by_key.get(key)
    if llm and int(llm.get('fallback_used') or 0)==0 and (llm.get('api_status') or '').upper()=='OK' and norm(llm.get('summary_text')):
        return {
            'source':'LLM', 'text':llm.get('summary_text'), 'llm_execution_id':llm.get('llm_execution_id'),
            'provider':llm.get('provider'), 'model':llm.get('model'), 'fallback_used':0, 'api_status':llm.get('api_status')
        }
    return {'source':'FALLBACK', 'text':row.get('summary_text'), 'llm_execution_id':None, 'provider':None, 'model':None, 'fallback_used':1, 'api_status':None}

def main():
    p=argparse.ArgumentParser()
    add_db_args(p)
    args=p.parse_args()
    conn=connect(args)
    with conn.cursor() as cur:
        cur.execute("""
        SELECT c.profile_id,c.dt,c.run_id,c.scenario_name,c.dominant_semantic_risk,
               c.measurement_evidence_json,c.analysis_evidence_json,s.summary_text
        FROM ai_incident_context_day_v04 c
        JOIN ai_incident_summary_day_v04 s
          ON s.profile_id=c.profile_id AND s.dt=c.dt AND s.run_id=c.run_id
        WHERE c.profile_id=%s AND c.dt BETWEEN %s AND %s
        ORDER BY c.dt,c.run_id
        """, (args.profile_id,args.dt_from,args.dt_to))
        rows=cur.fetchall()
        if not rows:
            raise RuntimeError('missing context/fallback summary rows')
        cur.execute("""
        SELECT l.profile_id,l.dt,l.provider,l.model,l.summary_text,l.fallback_used,l.api_status,
               e.id AS llm_execution_id
        FROM ai_llm_incident_summary_day_v04 l
        LEFT JOIN ai_llm_execution_log_day_v04 e
          ON e.profile_id=l.profile_id AND e.dt=l.dt AND e.provider=l.provider AND e.model=l.model
        WHERE l.profile_id=%s AND l.dt BETWEEN %s AND %s
        ORDER BY l.dt, CASE WHEN l.api_status='OK' AND l.fallback_used=0 THEN 0 ELSE 1 END, l.created_at DESC
        """, (args.profile_id,args.dt_from,args.dt_to))
        llm_by_key={}
        for l in cur.fetchall():
            llm_by_key.setdefault((l['profile_id'], str(l['dt'])), l)
        cur.execute("DELETE FROM ai_interpretation_validation_day WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id,args.dt_from,args.dt_to))
        vals=[]
        for r in rows:
            chosen=choose_llm(r, llm_by_key)
            text=(chosen['text'] or '').lower()
            dom=(r.get('dominant_semantic_risk') or 'None')
            meas=jloads(r.get('measurement_evidence_json'))
            ana=jloads(r.get('analysis_evidence_json'))
            terms=RISK_TERMS.get(dom, [dom.lower()])
            signal=score_bool(any(t in text for t in ['risk','위험','signal','신호','delta','score','증가','하락']))
            semantic=score_bool(dom == 'None' or any(t.lower() in text for t in terms))
            evidence=score_bool(bool(meas) and bool(ana) and any(t in text for t in EVIDENCE_TERMS))
            measurement=score_bool('measurement' in text or '측정' in text or 'delta' in text or 'direct_' in text)
            avg=(signal+semantic+evidence+measurement)/4.0
            status='PASS' if avg>=0.75 else 'WARN' if avg>=0.5 else 'FAIL'
            reason=f"source={chosen['source']}; signal={signal}; semantic={semantic}; evidence={evidence}; measurement={measurement}; dom={dom}"
            vals.append((r['profile_id'],r['dt'],str(r.get('run_id') or '1'),r.get('scenario_name'),dom,
                         chosen['source'],chosen['llm_execution_id'],chosen['provider'],chosen['model'],chosen['fallback_used'],chosen['api_status'],
                         signal,semantic,evidence,measurement,status,reason))
        cur.executemany("""
        INSERT INTO ai_interpretation_validation_day
        (profile_id,dt,run_id,scenario_name,dominant_semantic_risk,validated_output_source,llm_execution_id,provider,model,fallback_used,api_status,
         signal_match_score,semantic_match_score,evidence_match_score,measurement_reference_score,interpretation_validation_status,validation_reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          validated_output_source=VALUES(validated_output_source), llm_execution_id=VALUES(llm_execution_id), provider=VALUES(provider), model=VALUES(model),
          fallback_used=VALUES(fallback_used), api_status=VALUES(api_status), signal_match_score=VALUES(signal_match_score),
          semantic_match_score=VALUES(semantic_match_score), evidence_match_score=VALUES(evidence_match_score), measurement_reference_score=VALUES(measurement_reference_score),
          interpretation_validation_status=VALUES(interpretation_validation_status), validation_reason=VALUES(validation_reason), created_at=CURRENT_TIMESTAMP
        """, vals)
    conn.commit(); conn.close()
    src_counts={}
    for v in vals: src_counts[v[5]]=src_counts.get(v[5],0)+1
    print(f"[OK] validated ai_interpretation_validation_day rows={len(rows)} sources={src_counts}")
if __name__=='__main__': main()
