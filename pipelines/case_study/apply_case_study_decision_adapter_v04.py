#!/usr/bin/env python3
"""Apply v0.4 case-study semantic/risk/action interpretation adapter.

This adapter is intentionally placed AFTER Phase3 source->measurement->semantic
materialization and BEFORE Phase4 ML/AI execution.

Why:
- Source alias adapter already injects case-study metadata using existing v0.4
  cookie keys, so raw/canonical pipeline remains intact.
- The base Phase3 semantic rules are generic. Case studies need business-specific
  interpretation such as "offer schema drift + offer delivery missing" should be
  treated as Integrity/Consistency distortion, not just low Completeness.
- This script updates only Phase3 decision outputs from source evidence already
  present in canonical_events. It does not modify source, raw, canonical, or
  measurement lineage rows except optional direct_integrity_delta enrichment.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from typing import Any, Dict, Optional

import pymysql

RULES: Dict[str, Dict[str, Any]] = {
    "CASE-OFFER-001": {
        "scenario_name": "source_offer_schema_drift_realtime_missing",
        "evidence": {
            "scenario_id": "CASE-OFFER-001",
            "schema_flag": "drift",
            "reconciliation_flag": "offer_delivery_missing",
            "funnel_stage": "offer",
            "financial_product": "loan",
        },
        "target": {
            "dominant_semantic_risk": "Integrity",
            "secondary_semantic_risk": "Completeness",
            "final_risk_level": "HIGH",
            "recommended_action": "offer event schema reconciliation",
            "priority": "P1",
            "root_cause_direction": "offer schema drift and realtime delivery missing",
        },
        "scores": {
            "integrity_score_min": 0.65,
            "completeness_score_min": 0.30,
            "timeliness_score_min": 0.10,
            "consistency_score_min": 0.55,
            "availability_score_min": 0.00,
            "semantic_confidence_min": 0.65,
            "base_risk_score": 0.55,
            "amplification_weight": 0.15,
            "distortion_penalty": 0.20,
            "baseline_delta_penalty": 0.10,
        },
    },
    "CASE-REC-002": {
        "scenario_name": "source_recommendation_schema_drift_false_conversion",
        "evidence": {
            "scenario_id": "CASE-REC-002",
            "schema_flag": "drift",
            "reconciliation_flag": "kpi_semantic_mismatch",
            "funnel_stage": "recommendation",
        },
        "target": {
            "dominant_semantic_risk": "Integrity",
            "secondary_semantic_risk": "Consistency",
            "final_risk_level": "HIGH",
            "recommended_action": "recommendation KPI semantic mapping validation",
            "priority": "P1",
            "root_cause_direction": "recommendation schema drift and KPI semantic mismatch",
        },
        "scores": {
            "integrity_score_min": 0.65,
            "completeness_score_min": 0.00,
            "timeliness_score_min": 0.00,
            "consistency_score_min": 0.65,
            "availability_score_min": 0.00,
            "semantic_confidence_min": 0.65,
            "base_risk_score": 0.55,
            "amplification_weight": 0.10,
            "distortion_penalty": 0.25,
            "baseline_delta_penalty": 0.10,
        },
    },
}


def connect(args: argparse.Namespace):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def risk_level(score: float) -> str:
    if score >= 0.8:
        return "CRITICAL"
    if score >= 0.5:
        return "HIGH"
    if score >= 0.2:
        return "WARN"
    return "STABLE"


def table_exists(cur, name: str) -> bool:
    cur.execute("SHOW TABLES LIKE %s", (name,))
    return cur.fetchone() is not None


def get_row(cur, table: str, profile_id: str, dt: str, run_id: str) -> Dict[str, Any]:
    cur.execute(
        f"SELECT * FROM `{table}` WHERE profile_id=%s AND dt=%s AND run_id=%s",
        (profile_id, dt, run_id),
    )
    return cur.fetchone() or {}


def count_evidence(cur, profile_id: str, dt: str, run_id: str, rule: Dict[str, Any]) -> Dict[str, Any]:
    ev = rule["evidence"]
    params = [profile_id, dt, int(run_id) if str(run_id).isdigit() else run_id]
    where = ["profile_id=%s", "target_date=%s", "run_id=%s"]
    for col in ["scenario_id", "schema_flag", "reconciliation_flag", "funnel_stage", "financial_product"]:
        if col in ev:
            where.append(f"COALESCE({col}, '') = %s")
            params.append(ev[col])
    cur.execute(
        "SELECT COUNT(*) AS cnt, "
        "SUM(CASE WHEN schema_flag='drift' THEN 1 ELSE 0 END) AS drift_cnt, "
        "SUM(CASE WHEN reconciliation_flag NOT IN ('', 'none') THEN 1 ELSE 0 END) AS reconciliation_cnt, "
        "COUNT(DISTINCT uid) AS affected_uid_count "
        "FROM canonical_events WHERE " + " AND ".join(where),
        params,
    )
    row = cur.fetchone() or {}
    cur.execute(
        "SELECT COUNT(*) AS total_cnt FROM canonical_events "
        "WHERE profile_id=%s AND target_date=%s AND run_id=%s",
        (profile_id, dt, int(run_id) if str(run_id).isdigit() else run_id),
    )
    total = cur.fetchone() or {}
    total_cnt = int(total.get("total_cnt") or 0)
    cnt = int(row.get("cnt") or 0)
    row["total_cnt"] = total_cnt
    row["case_event_ratio"] = (cnt / total_cnt) if total_cnt else 0.0
    return row


def update_measurement(cur, profile_id: str, dt: str, run_id: str, rule: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    before = get_row(cur, "measurement_realism_day", profile_id, dt, run_id)
    scores = rule["scores"]
    case_ratio = float(evidence.get("case_event_ratio") or 0)
    integrity_delta = max(float(before.get("direct_integrity_delta") or 0), scores["integrity_score_min"], case_ratio)
    timeliness_delta = max(float(before.get("direct_timeliness_delta") or 0), scores.get("timeliness_score_min", 0))
    completeness_delta = max(float(before.get("direct_completeness_delta") or 0), scores.get("completeness_score_min", 0))
    detail = {
        "case_study_adapter": "case_study_decision_adapter_v04",
        "case_id": evidence.get("case_id"),
        "case_event_count": evidence.get("cnt", 0),
        "case_event_ratio": case_ratio,
        "reason": "schema/reconciliation metadata indicates business semantic distortion",
    }
    cur.execute(
        "UPDATE measurement_realism_day "
        "SET direct_integrity_delta=%s, direct_timeliness_delta=%s, direct_completeness_delta=%s, "
        "measurement_realism_status='WARN', realism_reason=CONCAT(COALESCE(realism_reason,''), '; case_study_semantic_distortion_adapter'), "
        "detail_json=%s, updated_at=CURRENT_TIMESTAMP "
        "WHERE profile_id=%s AND dt=%s AND run_id=%s",
        (integrity_delta, timeliness_delta, completeness_delta, json.dumps(detail), profile_id, dt, run_id),
    )
    return before


def apply_decision(cur, profile_id: str, dt: str, run_id: str, case_id: str, rule: Dict[str, Any], evidence: Dict[str, Any], dry_run: bool) -> None:
    evidence = dict(evidence)
    evidence["case_id"] = case_id
    target = rule["target"]
    scores = rule["scores"]
    base = float(scores["base_risk_score"])
    amp = float(scores["amplification_weight"])
    distortion = float(scores["distortion_penalty"])
    baseline_penalty = float(scores["baseline_delta_penalty"])
    overall = clamp(base + amp + distortion + baseline_penalty)
    level = target.get("final_risk_level") or risk_level(overall)
    after = {
        "dominant_semantic_risk": target["dominant_semantic_risk"],
        "secondary_semantic_risk": target["secondary_semantic_risk"],
        "semantic_confidence": scores["semantic_confidence_min"],
        "overall_risk_score": overall,
        "final_risk_level": level,
        "recommended_action": target["recommended_action"],
        "priority": target["priority"],
        "root_cause_direction": target["root_cause_direction"],
    }
    before = {
        "measurement_realism_day": get_row(cur, "measurement_realism_day", profile_id, dt, run_id),
        "semantic_interpretation_day": get_row(cur, "semantic_interpretation_day", profile_id, dt, run_id),
        "unified_reliability_score_day": get_row(cur, "unified_reliability_score_day", profile_id, dt, run_id),
        "action_recommendation_day": get_row(cur, "action_recommendation_day", profile_id, dt, run_id),
    }
    if dry_run:
        print(json.dumps({"dry_run": True, "evidence": evidence, "before": before, "after": after}, default=str, ensure_ascii=False, indent=2))
        return
    update_measurement(cur, profile_id, dt, run_id, rule, evidence)
    reason = (
        f"case_study_adapter={case_id}; canonical evidence cnt={evidence.get('cnt')} ratio={evidence.get('case_event_ratio'):.4f}; "
        "schema_flag/reconciliation_flag converted to Integrity + business distortion risk"
    )
    detail = json.dumps({"case_id": case_id, "evidence": evidence, "dominant": after["dominant_semantic_risk"], "secondary": after["secondary_semantic_risk"]}, default=str)
    cur.execute(
        "UPDATE semantic_interpretation_day SET "
        "dominant_semantic_risk=%s, secondary_semantic_risk=%s, semantic_confidence=%s, "
        "integrity_score=GREATEST(COALESCE(integrity_score,0), %s), "
        "completeness_score=GREATEST(COALESCE(completeness_score,0), %s), "
        "timeliness_score=GREATEST(COALESCE(timeliness_score,0), %s), "
        "consistency_score=GREATEST(COALESCE(consistency_score,0), %s), "
        "availability_score=GREATEST(COALESCE(availability_score,0), %s), "
        "interpretation_reason=%s, detail_json=%s, updated_at=CURRENT_TIMESTAMP "
        "WHERE profile_id=%s AND dt=%s AND run_id=%s",
        (
            after["dominant_semantic_risk"], after["secondary_semantic_risk"], after["semantic_confidence"],
            scores["integrity_score_min"], scores["completeness_score_min"], scores["timeliness_score_min"],
            scores["consistency_score_min"], scores.get("availability_score_min", 0.0), reason, detail,
            profile_id, dt, run_id,
        ),
    )
    cur.execute(
        "UPDATE unified_reliability_score_day SET "
        "overall_risk_score=%s, dominant_semantic_risk=%s, base_risk_score=%s, amplification_weight=%s, "
        "distortion_penalty=%s, baseline_delta_penalty=%s, confidence_weight=1, final_risk_level=%s, "
        "score_reason=%s, detail_json=%s, overall_reliability_risk_score=%s, confidence_score=%s, risk_level=%s, updated_at=CURRENT_TIMESTAMP "
        "WHERE profile_id=%s AND dt=%s AND run_id=%s",
        (
            overall, after["dominant_semantic_risk"], base, amp, distortion, baseline_penalty, level,
            f"case_study_adapter score: base={base:.4f} amplification={amp:.4f} distortion={distortion:.4f} baseline_delta={baseline_penalty:.4f}; {reason}",
            json.dumps({"case_id": case_id, "evidence": evidence, "dominant": after["dominant_semantic_risk"], "level": level}, default=str),
            overall, after["semantic_confidence"], level, profile_id, dt, run_id,
        ),
    )
    cur.execute(
        "UPDATE action_recommendation_day SET dominant_semantic_risk=%s, recommended_action=%s, priority=%s, "
        "root_cause_direction=%s, risk_alignment_score=%s, action_reason=%s, updated_at=CURRENT_TIMESTAMP "
        "WHERE profile_id=%s AND dt=%s AND run_id=%s",
        (
            after["dominant_semantic_risk"], after["recommended_action"], after["priority"],
            after["root_cause_direction"], after["semantic_confidence"],
            f"case_study_adapter action: {after['recommended_action']}; {reason}", profile_id, dt, run_id,
        ),
    )
    if table_exists(cur, "ml_feature_snapshot_day"):
        cur.execute(
            "UPDATE ml_feature_snapshot_day SET dominant_semantic_risk=%s, risk_level=%s, final_risk_level=%s, "
            "recommended_action=%s, overall_risk_score=%s, overall_reliability_risk_score=%s, label_risk_family=%s, "
            "label_action=%s, priority=%s, integrity_score=GREATEST(COALESCE(integrity_score,0), %s), "
            "completeness_score=GREATEST(COALESCE(completeness_score,0), %s), timeliness_score=GREATEST(COALESCE(timeliness_score,0), %s), "
            "consistency_score=GREATEST(COALESCE(consistency_score,0), %s), semantic_confidence=%s, direct_integrity_delta=GREATEST(COALESCE(direct_integrity_delta,0), %s), "
            "updated_at=CURRENT_TIMESTAMP WHERE profile_id=%s AND dt=%s AND run_id=%s",
            (
                after["dominant_semantic_risk"], level, level, after["recommended_action"], overall, overall,
                "integrity_risk", after["recommended_action"], after["priority"], scores["integrity_score_min"],
                scores["completeness_score_min"], scores["timeliness_score_min"], scores["consistency_score_min"],
                after["semantic_confidence"], scores["integrity_score_min"], profile_id, dt, run_id,
            ),
        )
    cur.execute(
        "INSERT INTO case_study_decision_adapter_audit_v04 "
        "(profile_id, dt, run_id, case_id, scenario_name, evidence_json, before_json, after_json, adapter_status, adapter_reason) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'APPLIED',%s)",
        (
            profile_id, dt, run_id, case_id, rule["scenario_name"], json.dumps(evidence, default=str),
            json.dumps(before, default=str), json.dumps(after, default=str), reason,
        ),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", default="nethru")
    ap.add_argument("--db-pass", default="nethru1234")
    ap.add_argument("--db-name", default="weblog")
    ap.add_argument("--profile-id", default="finance_bank")
    ap.add_argument("--dt", required=True)
    ap.add_argument("--run-id", default="1")
    ap.add_argument("--case-id", required=True, choices=sorted(RULES))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rule = RULES[args.case_id]
    conn = connect(args)
    try:
        with conn.cursor() as cur:
            evidence = count_evidence(cur, args.profile_id, args.dt, args.run_id, rule)
            cnt = int(evidence.get("cnt") or 0)
            print(f"[EVIDENCE] case_id={args.case_id} profile={args.profile_id} dt={args.dt} run_id={args.run_id} case_event_count={cnt} ratio={evidence.get('case_event_ratio'):.4f}")
            if cnt <= 0:
                raise RuntimeError(f"No canonical evidence found for case_id={args.case_id}; run source alias adapter first")
            apply_decision(cur, args.profile_id, args.dt, args.run_id, args.case_id, rule, evidence, args.dry_run)
        if args.dry_run:
            conn.rollback()
            print("[DRY_RUN] rollback")
        else:
            conn.commit()
            print(f"[OK] applied case_study_decision_adapter case_id={args.case_id} dt={args.dt}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
