#!/usr/bin/env python3
"""Validate Phase3-C Step5 Semantic/Action Knowledge Base separation.

Step5 checks that:
- Unified Risk is already computed by the Authority Risk Layer.
- Semantic consumes risk and produces classification/narrative only.
- Action consumes classification/risk/confidence/root-cause and performs catalog lookup only.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql

REQUIRED_SEMANTIC_COLUMNS = {
    "semantic_kb_version",
    "semantic_role",
    "semantic_is_risk_driver",
    "risk_classification",
    "narrative_template_id",
    "risk_narrative",
    "likelihood_score",
    "impact_score",
    "authority_risk_score",
    "authority_risk_level",
    "root_cause_candidate",
    "root_cause_confidence",
    "confidence_level",
    "action_catalog_key",
    "evidence_signal",
    "evidence_metric",
    "evidence_value",
    "evidence_threshold",
    "mapping_rule_id",
    "catalog_selection_reason",
    "catalog_selection_payload_json",
}

REQUIRED_ACTION_COLUMNS = {
    "action_catalog_version",
    "action_catalog_key",
    "risk_classification",
    "authority_risk_level",
    "confidence_level",
    "root_cause_candidate",
    "action_is_risk_engine",
    "evidence_signal",
    "mapping_rule_id",
    "catalog_selection_reason",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", default="nethru")
    p.add_argument("--db-pass", default="nethru1234")
    p.add_argument("--db-name", default="weblog")
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--allow-baseline-no-action", action="store_true")
    p.add_argument("--require-classification", action="store_true")
    p.add_argument("--require-action-catalog", action="store_true")
    p.add_argument("--expected-classification", default="")
    p.add_argument("--min-root-cause-confidence", type=float, default=0.20)
    p.add_argument("--require-catalog-explainability", action="store_true")
    p.add_argument("--expected-catalog-key", default="")
    p.add_argument("--expected-evidence-signal", default="")
    p.add_argument("--expected-mapping-rule-id", default="")
    return p.parse_args()


def connect(args: argparse.Namespace):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def fetchone(cur, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    cur.execute(sql, params)
    return cur.fetchone() or {}


def columns(cur, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {str(r["column_name"]) for r in cur.fetchall()}


def f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        val = row.get(key)
        return float(val if val is not None else default)
    except Exception:
        return default


def s(row: dict[str, Any], key: str, default: str = "") -> str:
    val = row.get(key)
    return default if val is None else str(val)


def parse_payload(text: Any) -> dict[str, Any]:
    if not text:
        return {}
    try:
        val = json.loads(str(text))
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    baseline_like = args.scenario_name.lower() in {"baseline", "normal", "stable"}

    with connect(args) as con:
        with con.cursor() as cur:
            semantic_missing = sorted(REQUIRED_SEMANTIC_COLUMNS - columns(cur, "semantic_interpretation_day_v05"))
            action_missing = sorted(REQUIRED_ACTION_COLUMNS - columns(cur, "action_recommendation_day_v05"))
            if semantic_missing:
                failures.append("missing semantic KB columns: " + ",".join(semantic_missing))
            if action_missing:
                failures.append("missing action catalog columns: " + ",".join(action_missing))
            if failures:
                print("[FAIL] " + "; ".join(failures))
                return 1

            params = (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.source_gen_run_id)
            risk = fetchone(
                cur,
                """
                SELECT * FROM unified_reliability_score_day_v05
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
                ORDER BY created_at DESC LIMIT 1
                """,
                params,
            )
            semantic = fetchone(
                cur,
                """
                SELECT * FROM semantic_interpretation_day_v05
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
                ORDER BY created_at DESC LIMIT 1
                """,
                params,
            )
            cur.execute(
                """
                SELECT * FROM action_recommendation_day_v05
                WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
                ORDER BY action_rank
                """,
                params,
            )
            actions = cur.fetchall()

            if not risk:
                failures.append("missing unified risk row")
            if not semantic:
                failures.append("missing semantic KB row")
            if not actions:
                failures.append("missing action catalog rows")
            if failures:
                print("[FAIL] " + "; ".join(failures))
                return 1

            classification = s(semantic, "risk_classification")
            catalog_key = s(semantic, "action_catalog_key")
            narrative = s(semantic, "risk_narrative")
            root_cause = s(semantic, "root_cause_candidate")
            root_conf = f(semantic, "root_cause_confidence")
            evidence_signal = s(semantic, "evidence_signal", "none")
            evidence_metric = s(semantic, "evidence_metric", "none")
            evidence_value = f(semantic, "evidence_value")
            evidence_threshold = f(semantic, "evidence_threshold")
            mapping_rule_id = s(semantic, "mapping_rule_id", "")
            catalog_reason = s(semantic, "catalog_selection_reason", "")
            semantic_driver = int(f(semantic, "semantic_is_risk_driver", 1))
            risk_score = f(risk, "overall_risk_score")
            likelihood = f(risk, "likelihood_score")
            impact = f(risk, "impact_score")
            risk_level = s(risk, "final_risk_level")
            confidence_sep = int(f(risk, "confidence_separate_from_risk"))

            print("[SEMANTIC_ACTION_KB]")
            print(f"scenario_name={args.scenario_name}")
            print(f"risk_score={risk_score:.6f} risk_level={risk_level} likelihood={likelihood:.6f} impact={impact:.6f} confidence_separate_from_risk={confidence_sep}")
            print(f"classification={classification}")
            print(f"catalog_key={catalog_key}")
            print(f"evidence_signal={evidence_signal} evidence_metric={evidence_metric} evidence_value={evidence_value:.6f} threshold={evidence_threshold:.6f}")
            print(f"mapping_rule_id={mapping_rule_id}")
            print(f"catalog_selection_reason={catalog_reason}")
            print(f"root_cause_candidate={root_cause} root_cause_confidence={root_conf:.6f}")
            print(f"semantic_is_risk_driver={semantic_driver}")
            print(f"action_count={len(actions)}")
            for a in actions[:10]:
                print(f"  - rank={a.get('action_rank')} type={a.get('action_type')} action={a.get('recommended_action')}")

            if semantic_driver != 0:
                failures.append("semantic_is_risk_driver must be 0")
            if confidence_sep != 1:
                failures.append("confidence must be separate from risk at unified risk layer")
            if not str(s(semantic, "semantic_kb_version")).startswith("v05_phase3c_step5"):
                failures.append("semantic_kb_version mismatch")
            sem_payload = parse_payload(semantic.get("semantic_payload_json"))
            if sem_payload.get("architecture_layer") != "KNOWLEDGE_BASE":
                failures.append("semantic payload layer must be KNOWLEDGE_BASE")
            risk_source = sem_payload.get("risk_source", {}) if isinstance(sem_payload.get("risk_source"), dict) else {}
            if risk_source.get("table") != "unified_reliability_score_day_v05":
                failures.append("semantic must consume unified risk output")
            if sem_payload.get("semantic_is_risk_driver") is not False:
                failures.append("semantic payload must state semantic_is_risk_driver=false")
            if args.require_catalog_explainability:
                if not evidence_signal or evidence_signal == "none":
                    failures.append("semantic evidence_signal missing")
                if not evidence_metric or evidence_metric == "none":
                    failures.append("semantic evidence_metric missing")
                if evidence_value <= 0:
                    failures.append("semantic evidence_value must be positive for explainability")
                if evidence_threshold <= 0:
                    failures.append("semantic evidence_threshold must be positive for explainability")
                if not mapping_rule_id:
                    failures.append("mapping_rule_id missing")
                if len(catalog_reason) < 40:
                    failures.append("catalog_selection_reason too short")
                if args.expected_catalog_key and catalog_key != args.expected_catalog_key:
                    failures.append(f"expected catalog_key {args.expected_catalog_key}, got {catalog_key}")
                if args.expected_evidence_signal and evidence_signal != args.expected_evidence_signal:
                    failures.append(f"expected evidence_signal {args.expected_evidence_signal}, got {evidence_signal}")
                if args.expected_mapping_rule_id and mapping_rule_id != args.expected_mapping_rule_id:
                    failures.append(f"expected mapping_rule_id {args.expected_mapping_rule_id}, got {mapping_rule_id}")
                if "collection_reliability" == catalog_key and "collection_gap_rate" not in catalog_reason:
                    failures.append("collection catalog reason should include collection_gap_rate")
                if "collection_reliability" == catalog_key and "WC" not in catalog_reason and "wc" not in catalog_reason:
                    failures.append("collection catalog reason should mention WC/wc")
                payload_chain = parse_payload(semantic.get("catalog_selection_payload_json"))
                if payload_chain.get("architecture_layer") != "KNOWLEDGE_BASE_EXPLAINABILITY":
                    failures.append("catalog_selection_payload_json layer mismatch")

            if baseline_like and args.allow_baseline_no_action:
                if classification not in {"None", "none", ""}:
                    failures.append(f"baseline classification should be None, got {classification}")
                if actions[0].get("action_type") != "no action":
                    failures.append("baseline should produce no action")
            else:
                if args.require_classification and classification in {"None", "none", ""}:
                    failures.append("non-baseline must produce risk classification")
                if args.expected_classification and classification != args.expected_classification:
                    failures.append(f"expected classification {args.expected_classification}, got {classification}")
                if not narrative or len(narrative) < 20:
                    failures.append("risk_narrative too short")
                if args.expected_classification == "Operational Observability Reliability":
                    if "Reality" not in narrative or "WC" not in narrative:
                        failures.append("OBS narrative should mention Reality and WC")
                    if root_conf < args.min_root_cause_confidence:
                        failures.append(f"root cause confidence too low: {root_conf:.6f} < {args.min_root_cause_confidence:.6f}")
                if args.require_action_catalog:
                    action_types = {str(a.get("action_type")) for a in actions}
                    if catalog_key == "collection_reliability":
                        expected_actions = {
                            "wc collector validation",
                            "web-wc reconciliation check",
                            "dashboard KPI annotation",
                        }
                        missing_actions = sorted(expected_actions - action_types)
                        if missing_actions:
                            failures.append("missing collection reliability actions: " + ",".join(missing_actions))
                    for row in actions:
                        if int(f(row, "action_is_risk_engine", 1)) != 0:
                            failures.append("action_is_risk_engine must be 0")
                        if str(row.get("action_catalog_version") or "").startswith("v05_phase3c_step5") is False:
                            failures.append("action_catalog_version mismatch")
                            break
                        if args.require_catalog_explainability:
                            if str(row.get("evidence_signal") or "") != evidence_signal:
                                failures.append("action evidence_signal must match semantic evidence_signal")
                                break
                            if str(row.get("mapping_rule_id") or "") != mapping_rule_id:
                                failures.append("action mapping_rule_id must match semantic mapping_rule_id")
                                break
                            if len(str(row.get("catalog_selection_reason") or "")) < 40:
                                failures.append("action catalog_selection_reason too short")
                                break

    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_semantic_action_knowledge_base passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
