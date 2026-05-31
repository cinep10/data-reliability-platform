#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common_v04 import add_db_args, connect, ACTION_MAP

ACTION_KEYWORDS = {
    'ingestion validation': ['ingestion validation','ingestion','누락','수집','검증'],
    'queue/backlog check': ['queue','backlog','latency','delay','지연','대기열'],
    'retry/timeout tuning': ['retry','timeout','availability','가용성','재시도','타임아웃'],
    'reconciliation': ['reconciliation','integrity','schema','정합','무결성','스키마'],
    'mapping validation': ['mapping','identity','consistency','매핑','식별자','일관성'],
    'no action': ['no action','monitor','stable','정상','모니터링']
}

def norm(s): return (s or '').strip()
def ok_action(rule, text):
    r=norm(rule).lower(); t=(text or '').lower()
    if not r: return False
    if r in t: return True
    return any(k in t for k in ACTION_KEYWORDS.get(r, []))

def main():
    p=argparse.ArgumentParser(); add_db_args(p); args=p.parse_args()
    conn=connect(args)
    with conn.cursor() as cur:
        cur.execute("""
        SELECT a.profile_id,a.dt,a.run_id,a.scenario_name,a.dominant_semantic_risk,a.rule_recommended_action,a.ai_action_explanation
        FROM ai_recommended_action_day_v04 a
        WHERE a.profile_id=%s AND a.dt BETWEEN %s AND %s ORDER BY a.dt,a.run_id
        """, (args.profile_id,args.dt_from,args.dt_to))
        rows=cur.fetchall()
        if not rows: raise RuntimeError('missing fallback ai_recommended_action_day_v04 rows')
        cur.execute("""
        SELECT l.profile_id,l.dt,l.provider,l.model,l.action_text,l.fallback_used,l.api_status,e.id AS llm_execution_id
        FROM ai_llm_recommended_action_day_v04 l
        LEFT JOIN ai_llm_execution_log_day_v04 e
          ON e.profile_id=l.profile_id AND e.dt=l.dt AND e.provider=l.provider AND e.model=l.model
        WHERE l.profile_id=%s AND l.dt BETWEEN %s AND %s
        ORDER BY l.dt, CASE WHEN l.api_status='OK' AND l.fallback_used=0 THEN 0 ELSE 1 END, l.created_at DESC
        """, (args.profile_id,args.dt_from,args.dt_to))
        llm_by_key={}
        for l in cur.fetchall():
            llm_by_key.setdefault((l['profile_id'], str(l['dt'])), l)
        cur.execute("DELETE FROM ai_action_validation_day WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id,args.dt_from,args.dt_to))
        vals=[]
        for r in rows:
            key=(r['profile_id'], str(r['dt']))
            llm=llm_by_key.get(key)
            use_llm=bool(llm and int(llm.get('fallback_used') or 0)==0 and (llm.get('api_status') or '').upper()=='OK' and norm(llm.get('action_text')))
            source='LLM' if use_llm else 'FALLBACK'
            text=llm.get('action_text') if use_llm else r.get('ai_action_explanation')
            provider=llm.get('provider') if use_llm else None
            model=llm.get('model') if use_llm else None
            exec_id=llm.get('llm_execution_id') if use_llm else None
            fallback_used=0 if use_llm else 1
            api_status=llm.get('api_status') if use_llm else None
            dom=r.get('dominant_semantic_risk')
            expected=ACTION_MAP.get(dom, r.get('rule_recommended_action') or 'no action')
            rule=norm(r.get('rule_recommended_action') or expected)
            ok=ok_action(rule, text)
            score=1.0 if ok else 0.0
            status='ALIGNED' if ok else 'MISMATCH'
            wrong=0 if ok else 1
            reason=f"source={source}; expected={expected}; rule={rule}; status={status}"
            vals.append((r['profile_id'],r['dt'],str(r.get('run_id') or '1'),r.get('scenario_name'),dom,
                         source,exec_id,provider,model,fallback_used,api_status,rule,text,score,status,wrong,reason))
        cur.executemany("""
        INSERT INTO ai_action_validation_day
        (profile_id,dt,run_id,scenario_name,dominant_semantic_risk,validated_output_source,llm_execution_id,provider,model,fallback_used,api_status,
         rule_recommended_action,ai_action_text,action_match_score,action_alignment_status,wrong_action_flag,validation_reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          validated_output_source=VALUES(validated_output_source), llm_execution_id=VALUES(llm_execution_id), provider=VALUES(provider), model=VALUES(model), fallback_used=VALUES(fallback_used), api_status=VALUES(api_status),
          rule_recommended_action=VALUES(rule_recommended_action), ai_action_text=VALUES(ai_action_text), action_match_score=VALUES(action_match_score),
          action_alignment_status=VALUES(action_alignment_status), wrong_action_flag=VALUES(wrong_action_flag), validation_reason=VALUES(validation_reason), created_at=CURRENT_TIMESTAMP
        """, vals)
    conn.commit(); conn.close()
    src_counts={}
    for v in vals: src_counts[v[5]]=src_counts.get(v[5],0)+1
    print(f"[OK] validated ai_action_validation_day rows={len(rows)} sources={src_counts}")
if __name__=='__main__': main()
