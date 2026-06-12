#!/usr/bin/env python3
import argparse, json, os, time, sys
from decimal import Decimal
import pymysql

# Conservative prices for research logging. Override with env if needed.
# gpt-4.1-mini: set via env to keep future pricing editable without code change.
INPUT_PER_1M = Decimal(os.getenv('LLM_INPUT_COST_PER_1M', '0.40'))
OUTPUT_PER_1M = Decimal(os.getenv('LLM_OUTPUT_COST_PER_1M', '1.60'))


def db(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user,
                           password=args.db_pass, database=args.db_name,
                           charset='utf8mb4', autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)

def fallback(row):
    risk = row.get('dominant_semantic_risk') or 'None'
    level = row.get('final_risk_level') or 'UNKNOWN'
    action = row.get('recommended_action') or 'manual investigation'
    score = row.get('overall_risk_score')
    summary = (f"[{level}] dominant semantic risk is {risk}. "
               f"Rule-based overall risk score is {score}. "
               f"Evidence is based on Phase3 measurement, semantic interpretation, unified risk score, and action recommendation.")
    action_text = f"Recommended action is '{action}', aligned with dominant semantic risk '{risk}'."
    return summary, action_text

def make_prompt(row):
    payload = {
        'profile_id': row.get('profile_id'),
        'dt': str(row.get('dt')),
        'scenario_name': row.get('scenario_name'),
        'dominant_semantic_risk': row.get('dominant_semantic_risk'),
        'final_risk_level': row.get('final_risk_level'),
        'overall_risk_score': float(row.get('overall_risk_score') or 0),
        'recommended_action': row.get('recommended_action'),
        'priority': row.get('priority'),
        'ml_predicted_semantic_risk': row.get('predicted_semantic_risk'),
        'ml_risk_score': float(row.get('ml_risk_score') or 0),
        'score_gap': float(row.get('score_gap') or 0),
    }
    return (
        "You are an evidence-based reliability incident explainer. "
        "Do not invent causes. Use only the JSON evidence. "
        "Return JSON with keys summary_text and action_text. "
        "summary_text must mention the risk level, dominant semantic risk, rule score, and ML reference if present. "
        "action_text must explain the provided recommended_action without creating a new action.\n"
        f"Evidence JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )

def call_openai(prompt, model):
    from openai import OpenAI
    client = OpenAI()
    start = time.time()
    resp = client.responses.create(
        model=model,
        input=prompt,
        temperature=0.1,
        max_output_tokens=350,
    )
    latency_ms = int((time.time() - start) * 1000)
    text = getattr(resp, 'output_text', '') or ''
    usage = getattr(resp, 'usage', None)
    in_tok = int(getattr(usage, 'input_tokens', 0) or 0) if usage else 0
    out_tok = int(getattr(usage, 'output_tokens', 0) or 0) if usage else 0
    total = int(getattr(usage, 'total_tokens', in_tok + out_tok) or (in_tok + out_tok)) if usage else in_tok + out_tok
    return text, in_tok, out_tok, total, latency_ms

def parse_llm_json(text, row):
    try:
        obj = json.loads(text)
        s = str(obj.get('summary_text') or '').strip()
        a = str(obj.get('action_text') or '').strip()
        if s and a:
            return s, a
    except Exception:
        pass
    fs, fa = fallback(row)
    return (text.strip() or fs), fa

def cost_usd(input_tokens, output_tokens):
    return (Decimal(input_tokens) * INPUT_PER_1M / Decimal(1000000)) + (Decimal(output_tokens) * OUTPUT_PER_1M / Decimal(1000000))

def upsert(cur, args, row, provider, model, summary, action, prompt_tokens, completion_tokens, total_tokens, latency_ms, api_status, api_error, fallback_used):
    c = cost_usd(prompt_tokens, completion_tokens)
    base = (row['profile_id'], row['dt'], row.get('run_id'), row.get('scenario_name'), provider, model)
    cur.execute("""
      INSERT INTO ai_llm_execution_log_day_v04
      (profile_id, dt, run_id, scenario_name, provider, model,
       prompt_tokens, completion_tokens, total_tokens, latency_ms,
       api_status, api_error, fallback_used, llm_cost_usd, summary_text, action_text)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON DUPLICATE KEY UPDATE run_id=VALUES(run_id), scenario_name=VALUES(scenario_name),
       prompt_tokens=VALUES(prompt_tokens), completion_tokens=VALUES(completion_tokens), total_tokens=VALUES(total_tokens),
       latency_ms=VALUES(latency_ms), api_status=VALUES(api_status), api_error=VALUES(api_error),
       fallback_used=VALUES(fallback_used), llm_cost_usd=VALUES(llm_cost_usd), summary_text=VALUES(summary_text),
       action_text=VALUES(action_text), created_at=CURRENT_TIMESTAMP
    """, base + (prompt_tokens, completion_tokens, total_tokens, latency_ms, api_status, api_error, int(fallback_used), str(c), summary, action))
    cur.execute("""
      INSERT INTO ai_llm_incident_summary_day_v04
      (profile_id, dt, run_id, scenario_name, provider, model, summary_text, fallback_used, api_status)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON DUPLICATE KEY UPDATE run_id=VALUES(run_id), scenario_name=VALUES(scenario_name), summary_text=VALUES(summary_text),
        fallback_used=VALUES(fallback_used), api_status=VALUES(api_status), created_at=CURRENT_TIMESTAMP
    """, base + (summary, int(fallback_used), api_status))
    cur.execute("""
      INSERT INTO ai_llm_recommended_action_day_v04
      (profile_id, dt, run_id, scenario_name, provider, model, action_text, fallback_used, api_status)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON DUPLICATE KEY UPDATE run_id=VALUES(run_id), scenario_name=VALUES(scenario_name), action_text=VALUES(action_text),
        fallback_used=VALUES(fallback_used), api_status=VALUES(api_status), created_at=CURRENT_TIMESTAMP
    """, base + (action, int(fallback_used), api_status))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db-host', default='127.0.0.1'); p.add_argument('--db-port', type=int, default=3306)
    p.add_argument('--db-user', default='nethru'); p.add_argument('--db-pass', default='nethru1234'); p.add_argument('--db-name', default='weblog')
    p.add_argument('--profile-id', required=True); p.add_argument('--dt-from', required=True); p.add_argument('--dt-to', required=True)
    p.add_argument('--provider', default=os.getenv('AI_PROVIDER', os.getenv('LLM_PROVIDER', 'fallback')))
    p.add_argument('--model', default=os.getenv('AI_MODEL', 'gpt-4.1-mini'))
    p.add_argument('--fail-open', default=os.getenv('LLM_FAIL_OPEN', 'true'))
    p.add_argument('--limit', type=int, default=int(os.getenv('LLM_LIMIT', '0')))
    args = p.parse_args()
    conn = db(args)
    rows_done = 0
    try:
        with conn.cursor() as cur:
            cur.execute("""
              SELECT f.profile_id, f.dt, f.run_id, f.scenario_name,
                     f.dominant_semantic_risk, f.final_risk_level, f.overall_risk_score,
                     f.recommended_action, f.priority,
                     m.predicted_semantic_risk, m.ml_risk_score, m.score_gap
              FROM ml_feature_snapshot_day f
              LEFT JOIN ml_risk_score_day m ON m.profile_id=f.profile_id AND m.dt=f.dt
              WHERE f.profile_id=%s AND f.dt BETWEEN %s AND %s
              ORDER BY f.dt
            """, (args.profile_id, args.dt_from, args.dt_to))
            rows = cur.fetchall()
            if args.limit and args.limit > 0: rows = rows[:args.limit]
            for row in rows:
                summary, action = fallback(row)
                pt = ct = tt = lat = 0
                status = 'FALLBACK'
                err = None
                used_fallback = True
                if args.provider == 'openai':
                    try:
                        text, pt, ct, tt, lat = call_openai(make_prompt(row), args.model)
                        summary, action = parse_llm_json(text, row)
                        status = 'OK'
                        used_fallback = False
                    except Exception as e:
                        err = str(e)[:4000]
                        status = 'ERROR'
                        used_fallback = True
                        if str(args.fail_open).lower() != 'true':
                            raise
                upsert(cur, args, row, args.provider, args.model, summary, action, pt, ct, tt, lat, status, err, used_fallback)
                rows_done += 1
        conn.commit()
        print(f"[OK] llm_optional rows={rows_done} provider={args.provider} model={args.model}")
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
if __name__ == '__main__': main()
