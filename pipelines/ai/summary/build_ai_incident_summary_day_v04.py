#!/usr/bin/env python3
import argparse, json
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from common_v04 import add_db_args, connect, jdump

def fmt(x):
    if x is None: return '0'
    try: return f"{float(x):.4f}"
    except Exception: return str(x)

def main():
    p=argparse.ArgumentParser(); add_db_args(p); args=p.parse_args()
    conn=connect(args)
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM ai_incident_context_day_v04 WHERE profile_id=%s AND dt BETWEEN %s AND %s ORDER BY dt, run_id", (args.profile_id,args.dt_from,args.dt_to))
        rows=cur.fetchall()
        if not rows: raise RuntimeError('missing ai_incident_context_day_v04 rows')
        cur.execute("DELETE FROM ai_incident_summary_day_v04 WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id,args.dt_from,args.dt_to))
        vals=[]
        for r in rows:
            meas=json.loads(r.get('measurement_evidence_json') or '{}')
            ana=json.loads(r.get('analysis_evidence_json') or '{}')
            dom=r.get('dominant_semantic_risk') or 'None'
            level=r.get('final_risk_level') or 'UNKNOWN'
            action=r.get('recommended_action') or 'no action'
            text=(f"현재 상태는 {level}입니다. dominant semantic risk는 {dom}입니다. "
                  f"측정 근거는 completeness_delta={fmt(meas.get('direct_completeness_delta'))}, timeliness_delta={fmt(meas.get('direct_timeliness_delta'))}, "
                  f"availability_delta={fmt(meas.get('direct_availability_delta'))}, integrity_delta={fmt(meas.get('direct_integrity_delta'))}입니다. "
                  f"분석 근거는 propagation_score={fmt(ana.get('propagation_score'))}, amplification_score={fmt(ana.get('amplification_score'))}, "
                  f"distortion_score={fmt(ana.get('distortion_score'))}, baseline_delta={fmt(ana.get('baseline_delta'))}입니다. "
                  f"권장 action은 Phase3 rule action 기준 '{action}'입니다. ML 예측은 참고용이며 rule/semantic score를 대체하지 않습니다.")
            vals.append((r['profile_id'],r['dt'],r['run_id'],r.get('scenario_name'),dom,level,text,r.get('context_json')))
        cur.executemany("""
        INSERT INTO ai_incident_summary_day_v04
        (profile_id,dt,run_id,scenario_name,dominant_semantic_risk,final_risk_level,summary_text,evidence_reference_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE summary_text=VALUES(summary_text), evidence_reference_json=VALUES(evidence_reference_json), created_at=CURRENT_TIMESTAMP
        """, vals)
    conn.commit(); conn.close(); print(f"[OK] built ai_incident_summary_day_v04 rows={len(rows)}")
if __name__=='__main__': main()
