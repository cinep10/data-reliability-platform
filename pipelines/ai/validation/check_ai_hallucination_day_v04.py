#!/usr/bin/env python3
import argparse, json, re, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common_v04 import add_db_args, connect, jdump

CLAIMS = {
    'kafka broker outage': ['kafka broker outage','kafka outage','broker outage','카프카 브로커 장애'],
    'database failure': ['db outage','database outage','database failure','db failure','database corruption','db 장애','데이터베이스 장애'],
    'network issue': ['network outage','network failure','network issue','네트워크 장애','네트워크 문제'],
    'schema corruption': ['schema corruption','schema corrupted','스키마 손상'],
    'collector crash': ['collector crash','collector failure','collector crashed','수집기 장애','collector 장애'],
    'disk failure': ['disk failure','disk full','디스크 장애'],
    'memory leak': ['memory leak','메모리 누수'],
    'third-party api outage': ['third-party api','external api outage','외부 api 장애']
}
SUPPORTED_HINTS = {
    'schema corruption': ['source_schema_drift','integrity','schema drift','direct_integrity_delta'],
}

def norm(s): return (s or '').lower()
def find_claims(text):
    hits=[]
    for label, terms in CLAIMS.items():
        for t in terms:
            if t.lower() in text:
                hits.append(label); break
    return hits

def is_supported(label, scenario, dom, evidence_text):
    # Most operational root-cause claims require explicit evidence. Schema drift is supported, but schema corruption remains too strong unless evidence says corruption.
    if label == 'schema corruption':
        return 'schema corruption' in evidence_text or '스키마 손상' in evidence_text
    return label in evidence_text

def main():
    p=argparse.ArgumentParser(); add_db_args(p); args=p.parse_args()
    conn=connect(args)
    with conn.cursor() as cur:
        cur.execute("""
        SELECT c.profile_id,c.dt,c.run_id,c.scenario_name,c.dominant_semantic_risk,c.context_json,
               s.summary_text,a.ai_action_explanation
        FROM ai_incident_context_day_v04 c
        JOIN ai_incident_summary_day_v04 s ON s.profile_id=c.profile_id AND s.dt=c.dt AND s.run_id=c.run_id
        LEFT JOIN ai_recommended_action_day_v04 a ON a.profile_id=c.profile_id AND a.dt=c.dt AND a.run_id=c.run_id
        WHERE c.profile_id=%s AND c.dt BETWEEN %s AND %s ORDER BY c.dt,c.run_id
        """, (args.profile_id,args.dt_from,args.dt_to))
        rows=cur.fetchall()
        if not rows: raise RuntimeError('missing context/summary/action rows')
        cur.execute("""
        SELECT e.id AS llm_execution_id,e.profile_id,e.dt,e.provider,e.model,e.summary_text,e.action_text,e.fallback_used,e.api_status
        FROM ai_llm_execution_log_day_v04 e
        WHERE e.profile_id=%s AND e.dt BETWEEN %s AND %s
        ORDER BY e.dt, CASE WHEN e.api_status='OK' AND e.fallback_used=0 THEN 0 ELSE 1 END, e.created_at DESC
        """, (args.profile_id,args.dt_from,args.dt_to))
        llm_by_key={}
        for l in cur.fetchall():
            llm_by_key.setdefault((l['profile_id'], str(l['dt'])), l)
        cur.execute("DELETE FROM ai_hallucination_check_day WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id,args.dt_from,args.dt_to))
        vals=[]
        for r in rows:
            key=(r['profile_id'], str(r['dt']))
            llm=llm_by_key.get(key)
            use_llm=bool(llm and int(llm.get('fallback_used') or 0)==0 and (llm.get('api_status') or '').upper()=='OK' and ((llm.get('summary_text') or '') or (llm.get('action_text') or '')))
            source='LLM' if use_llm else 'FALLBACK'
            text=(str(llm.get('summary_text') or '')+' '+str(llm.get('action_text') or '')).lower() if use_llm else (str(r.get('summary_text') or '')+' '+str(r.get('ai_action_explanation') or '')).lower()
            provider=llm.get('provider') if use_llm else None
            model=llm.get('model') if use_llm else None
            exec_id=llm.get('llm_execution_id') if use_llm else None
            fallback_used=0 if use_llm else 1
            api_status=llm.get('api_status') if use_llm else None
            evidence_text=norm(r.get('context_json'))+' '+norm(r.get('scenario_name'))+' '+norm(r.get('dominant_semantic_risk'))
            candidates=find_claims(text)
            unsupported=[c for c in candidates if not is_supported(c, norm(r.get('scenario_name')), norm(r.get('dominant_semantic_risk')), evidence_text)]
            cnt=len(unsupported); score=min(1.0, cnt/3.0); flag=1 if cnt>0 else 0
            vals.append((r['profile_id'],r['dt'],str(r.get('run_id') or '1'),r.get('scenario_name'),
                         source,exec_id,provider,model,fallback_used,api_status,cnt,score,flag,jdump(unsupported)))
        cur.executemany("""
        INSERT INTO ai_hallucination_check_day
        (profile_id,dt,run_id,scenario_name,validated_output_source,llm_execution_id,provider,model,fallback_used,api_status,
         unsupported_claim_count,hallucination_score,hallucination_flag,unsupported_claims_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          validated_output_source=VALUES(validated_output_source), llm_execution_id=VALUES(llm_execution_id), provider=VALUES(provider), model=VALUES(model), fallback_used=VALUES(fallback_used), api_status=VALUES(api_status),
          unsupported_claim_count=VALUES(unsupported_claim_count), hallucination_score=VALUES(hallucination_score), hallucination_flag=VALUES(hallucination_flag), unsupported_claims_json=VALUES(unsupported_claims_json), created_at=CURRENT_TIMESTAMP
        """, vals)
    conn.commit(); conn.close()
    src_counts={}
    for v in vals: src_counts[v[4]]=src_counts.get(v[4],0)+1
    print(f"[OK] checked ai_hallucination_check_day rows={len(rows)} sources={src_counts}")
if __name__=='__main__': main()
