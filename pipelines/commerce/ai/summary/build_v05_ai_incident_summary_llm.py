from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Any, Dict

import pymysql


def parse_args():
    p = argparse.ArgumentParser(
        description="Build v0.5 AI incident summary using an optional LLM with strict evidence grounding. Falls back deterministically."
    )
    for k in ["db-host", "db-user", "db-pass", "db-name", "profile-id", "target-date"]:
        p.add_argument("--" + k, required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--scenario-name", default="baseline")
    p.add_argument("--truncate-target", action="store_true")
    p.add_argument("--llm-provider", default=os.getenv("V05_LLM_PROVIDER", "none"), choices=["none", "openai_compatible"])
    p.add_argument("--llm-endpoint", default=os.getenv("V05_LLM_ENDPOINT", "https://api.openai.com/v1/chat/completions"))
    p.add_argument("--llm-model", default=os.getenv("V05_LLM_MODEL", "gpt-4o-mini"))
    p.add_argument("--llm-api-key", default=os.getenv("OPENAI_API_KEY", ""))
    p.add_argument("--timeout-sec", type=int, default=int(os.getenv("V05_LLM_TIMEOUT_SEC", "30")))
    return p.parse_args()


def conn(a):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def scope_where(a):
    where = "profile_id=%s AND target_date=%s AND run_id=%s"
    params = [a.profile_id, a.target_date, a.run_id]
    if a.source_gen_run_id is not None:
        where += " AND source_gen_run_id=%s"
        params.append(a.source_gen_run_id)
    return where, params


def deterministic_summary(a, context_payload: Dict[str, Any], source="deterministic_fallback"):
    m = context_payload.get("measurement") or {}
    u = context_payload.get("unified_score") or {}
    sem = context_payload.get("semantic") or {}
    ml = context_payload.get("ml_calibration") or {}
    actions = context_payload.get("actions") or []
    level = u.get("final_risk_level") or "unknown"
    score = float(u.get("overall_risk_score") or 0.0)
    dom = sem.get("dominant_semantic_risk") or "None"
    explanation = (
        f"For {a.profile_id} {a.target_date} scenario={a.scenario_name}, the governed v0.5 reliability chain reports "
        f"final_risk_level={level}, overall_risk_score={score:.6f}, dominant_semantic_risk={dom}. "
        f"Evidence includes behavior_transaction_match_rate={m.get('behavior_transaction_match_rate')} and "
        f"transaction_state_match_rate={m.get('transaction_state_match_rate')}."
    )
    if dom in (None, "", "None"):
        root = "Residual reconciliation evidence exists but did not pass semantic/action promotion gates. This is treated as non-promoted baseline or low-risk variation."
    else:
        root = f"Primary promoted semantic evidence is {dom}, based on measurement-derived reconciliation deltas and not direct business-rule hardcoding."
    action = actions[0].get("recommended_action") if actions else "no action"
    action_summary = (
        f"Recommended action from the governed action layer: {action}. "
        f"ML is supplemental only: predicted_risk_class={ml.get('predicted_risk_class','unknown')}, "
        f"predicted_severity_score={ml.get('predicted_severity_score','unknown')}."
    )
    return explanation, root, action_summary, source


def build_prompt(a, evidence: Dict[str, Any]) -> str:
    compact = {
        "profile_id": a.profile_id,
        "target_date": a.target_date,
        "scenario_name": a.scenario_name,
        "measurement": evidence.get("measurement"),
        "semantic": evidence.get("semantic"),
        "unified_score": evidence.get("unified_score"),
        "actions": evidence.get("actions"),
        "ml_calibration": evidence.get("ml_calibration"),
        "rules": {
            "rule_semantic_is_source_of_truth": True,
            "ml_is_supplemental_only": True,
            "ai_is_explanation_only": True,
            "do_not_create_new_actions": True,
            "do_not_claim_evidence_not_present": True,
        },
    }
    return (
        "You are generating a concise reliability incident explanation. Use ONLY the JSON evidence. "
        "Do not invent metrics, root causes, or actions. Do not override final_risk_level or recommended_action. "
        "Return JSON with keys incident_explanation, root_cause_summary, recommended_action_summary.\n\n"
        + json.dumps(compact, ensure_ascii=False, default=str)
    )


def call_openai_compatible(a, prompt: str):
    if not a.llm_api_key:
        raise RuntimeError("missing LLM API key")
    body = {
        "model": a.llm_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "You are an evidence-constrained reliability summarizer."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        a.llm_endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {a.llm_api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=a.timeout_sec) as r:
        payload = json.loads(r.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return (
        str(parsed.get("incident_explanation") or ""),
        str(parsed.get("root_cause_summary") or ""),
        str(parsed.get("recommended_action_summary") or ""),
        "llm_openai_compatible",
    )


def main():
    a = parse_args()
    c = conn(a)
    try:
        with c.cursor() as cur:
            where, params = scope_where(a)
            cur.execute("SELECT * FROM v05_ai_incident_context_day WHERE " + where, params)
            ctx = cur.fetchone()
            if not ctx:
                raise RuntimeError("missing v05_ai_incident_context_day")
            evidence = json.loads(ctx.get("context_payload_json") or "{}")
            if int(ctx.get("evidence_missing_flag") or 0) == 1 or int(ctx.get("evidence_count") or 0) <= 0:
                explanation, root, action_summary, output_source = deterministic_summary(a, evidence, "deterministic_fallback_missing_evidence")
            elif a.llm_provider == "openai_compatible":
                try:
                    explanation, root, action_summary, output_source = call_openai_compatible(a, build_prompt(a, evidence))
                except Exception as e:
                    print(f"[WARN] LLM call failed; fallback used: {e}", file=sys.stderr)
                    explanation, root, action_summary, output_source = deterministic_summary(a, evidence, "deterministic_fallback_after_llm_error")
            else:
                explanation, root, action_summary, output_source = deterministic_summary(a, evidence, "deterministic_fallback")

            payload = {
                "summary_source": output_source,
                "evidence_tables_used": [
                    "v05_ai_incident_context_day",
                    "v05_reconciliation_measurement_day",
                    "semantic_interpretation_day_v05",
                    "unified_reliability_score_day_v05",
                    "action_recommendation_day_v05",
                    "v05_ml_calibration_result_day",
                ],
                "ai_is_explanation_layer": True,
                "ml_is_supplemental_only": True,
                "rule_semantic_is_source_of_truth": True,
                "no_unsupported_claims_required": True,
            }
            if a.truncate_target:
                cur.execute("DELETE FROM v05_ai_incident_summary_day WHERE " + where, params)
            cur.execute(
                """
                INSERT INTO v05_ai_incident_summary_day(
                  run_id, profile_id, source_gen_run_id, target_date, scenario_name,
                  incident_explanation, root_cause_summary, recommended_action_summary,
                  output_source, summary_payload_json
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    a.run_id,
                    a.profile_id,
                    a.source_gen_run_id,
                    a.target_date,
                    a.scenario_name,
                    explanation,
                    root,
                    action_summary,
                    output_source,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        c.commit()
        print(f"[build_v05_ai_incident_summary_llm] OK source={output_source}")
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


if __name__ == "__main__":
    main()
