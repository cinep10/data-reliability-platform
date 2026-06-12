#!/usr/bin/env python3
"""Validate Phase4-B Step4/5 Pattern Classification and Pattern Action Catalog.

Checks:
- Semantic/Classification is Knowledge Base, not risk engine.
- Classification source is authority_pattern_layer.
- Action catalog is pattern_driven and not risk engine.
- Baseline can be stable/no-action.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql

ALLOWED_PATTERNS = {
    "stable",
    "localized_failure",
    "systemic_failure",
    "silent_distortion",
    "reconciliation_failure",
    "interpretation_failure",
    "emerging_reliability_degradation",
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
    p.add_argument("--require-pattern-classification", action="store_true")
    p.add_argument("--require-pattern-action", action="store_true")
    p.add_argument("--min-pattern-confidence", type=float, default=0.05)
    return p.parse_args()


def connect(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def columns(cur, table: str) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {str(r["column_name"]) for r in cur.fetchall()}


def fetchone(cur, table: str, a: argparse.Namespace) -> dict[str, Any]:
    cur.execute(
        f"""
        SELECT * FROM {table}
        WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
        ORDER BY created_at DESC LIMIT 1
        """,
        (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
    )
    return cur.fetchone() or {}


def fetch_actions(cur, a: argparse.Namespace) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM action_recommendation_day_v05
        WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
        ORDER BY action_rank
        """,
        (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
    )
    return list(cur.fetchall())


def s(row: dict[str, Any], key: str, default: str = "") -> str:
    val = row.get(key)
    return default if val is None else str(val)


def f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        val = row.get(key)
        return float(val if val is not None else default)
    except Exception:
        return default


def parse_payload(text: Any) -> dict[str, Any]:
    if not text:
        return {}
    try:
        val = json.loads(str(text))
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def main() -> int:
    a = parse_args()
    failures: list[str] = []
    baseline_like = a.scenario_name.lower() in {"baseline", "normal", "stable"}

    required_semantic = {
        "classification_layer_version",
        "classification_role",
        "classification_source",
        "risk_pattern",
        "pattern_confidence",
        "pattern_reason",
        "classification_is_risk_engine",
        "pattern_to_classification_rule_id",
        "semantic_is_risk_driver",
        "risk_classification",
        "action_catalog_key",
    }
    required_action = {
        "action_catalog_mode",
        "action_catalog_source",
        "risk_pattern",
        "pattern_confidence",
        "pattern_action_rule_id",
        "pattern_action_reason",
        "action_is_risk_engine",
        "action_catalog_key",
        "risk_classification",
    }

    with connect(a) as con:
        with con.cursor() as cur:
            missing_s = sorted(required_semantic - columns(cur, "semantic_interpretation_day_v05"))
            missing_a = sorted(required_action - columns(cur, "action_recommendation_day_v05"))
            if missing_s:
                failures.append("missing semantic classification columns: " + ",".join(missing_s))
            if missing_a:
                failures.append("missing action catalog columns: " + ",".join(missing_a))
            if failures:
                print("[FAIL] " + "; ".join(failures))
                return 1

            risk = fetchone(cur, "unified_reliability_score_day_v05", a)
            sem = fetchone(cur, "semantic_interpretation_day_v05", a)
            actions = fetch_actions(cur, a)

    if not risk:
        failures.append("missing unified risk row")
    if not sem:
        failures.append("missing semantic classification row")
    if not actions:
        failures.append("missing action recommendation rows")
    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1

    risk_pattern = s(sem, "risk_pattern", s(risk, "risk_pattern", ""))
    pattern_conf = f(sem, "pattern_confidence", f(risk, "pattern_confidence"))
    classification = s(sem, "risk_classification", "")
    catalog = s(sem, "action_catalog_key", "")
    source = s(sem, "classification_source", "")
    sem_payload = parse_payload(sem.get("semantic_payload_json"))

    if risk_pattern not in ALLOWED_PATTERNS:
        failures.append(f"unsupported risk_pattern={risk_pattern}")
    if int(f(sem, "semantic_is_risk_driver", 1)) != 0:
        failures.append("semantic_is_risk_driver must be 0")
    if int(f(sem, "classification_is_risk_engine", 1)) != 0:
        failures.append("classification_is_risk_engine must be 0")
    if source != "authority_pattern_layer":
        failures.append(f"classification_source should be authority_pattern_layer, got {source}")
    if not s(sem, "pattern_to_classification_rule_id"):
        failures.append("missing pattern_to_classification_rule_id")
    if a.require_pattern_classification and not baseline_like:
        if risk_pattern == "stable":
            failures.append("non-baseline scenario should not classify as stable pattern")
        if pattern_conf < a.min_pattern_confidence:
            failures.append(f"pattern_confidence too low {pattern_conf:.6f} < {a.min_pattern_confidence:.6f}")
        if classification in {"", "None", "none"}:
            failures.append("non-baseline scenario should have non-empty risk_classification")
        if catalog in {"", "none"}:
            failures.append("non-baseline scenario should have action_catalog_key")
    if baseline_like and not a.allow_baseline_no_action and classification in {"None", "none"}:
        failures.append("baseline no-action requires --allow-baseline-no-action")
    if sem_payload and sem_payload.get("classification_is_risk_engine") not in {False, 0, None}:
        failures.append("semantic_payload_json classification_is_risk_engine must be false")

    first = actions[0]
    action_pattern = s(first, "risk_pattern", "")
    action_mode = s(first, "action_catalog_mode", "")
    action_source = s(first, "action_catalog_source", "")
    if int(f(first, "action_is_risk_engine", 1)) != 0:
        failures.append("action_is_risk_engine must be 0")
    if a.require_pattern_action and not baseline_like:
        if action_pattern != risk_pattern:
            failures.append(f"action risk_pattern mismatch action={action_pattern} semantic={risk_pattern}")
        if action_mode != "pattern_driven":
            failures.append(f"action_catalog_mode should be pattern_driven, got {action_mode}")
        if action_source != "authority_pattern_layer":
            failures.append(f"action_catalog_source should be authority_pattern_layer, got {action_source}")
        if not s(first, "pattern_action_rule_id"):
            failures.append("missing pattern_action_rule_id")
        if not s(first, "pattern_action_reason"):
            failures.append("missing pattern_action_reason")

    print(
        f"[PATTERN_CLASSIFICATION_ACTION] pattern={risk_pattern} confidence={pattern_conf:.6f} "
        f"classification={classification} catalog={catalog} actions={len(actions)} "
        f"classification_source={source} action_mode={action_mode}"
    )
    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_v05_pattern_classification_action_catalog passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
