#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# ARCHITECTURE LAYER: KNOWLEDGE BASE - PATTERN ACTION CATALOG
#
# Action generation is not a risk engine. It consumes Pattern Classification,
# Authority Risk, Confidence, and reference root-cause context. The primary
# catalog key is risk_pattern, not scenario name or OBS dimension.
# -----------------------------------------------------------------------------
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql

CATALOG_VERSION = "v05_phase4b_step5_pattern_action_catalog_v1"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build v0.5 action recommendations from Pattern-driven Semantic/Action Knowledge Base catalog.")
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--scenario-name", default="baseline")
    p.add_argument("--truncate-target", action="store_true")
    p.add_argument("--action-threshold", type=float, default=0.08)
    p.add_argument("--calibration-config", default="pipelines/commerce/configs/v05_semantic_action_calibration.yaml")
    return p.parse_args()


def conn(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def scope_where(a: argparse.Namespace) -> tuple[str, list[Any]]:
    w = "profile_id=%s AND target_date=%s AND run_id=%s"
    p: list[Any] = [a.profile_id, a.target_date, a.run_id]
    if a.source_gen_run_id is not None:
        w += " AND source_gen_run_id=%s"
        p.append(a.source_gen_run_id)
    return w, p


def f(row: dict[str, Any] | None, key: str, default: float = 0.0) -> float:
    try:
        value = (row or {}).get(key)
        return float(value if value is not None else default)
    except Exception:
        return default


def s(row: dict[str, Any] | None, key: str, default: str = "") -> str:
    value = (row or {}).get(key)
    if value is None:
        return default
    value = str(value)
    return value if value else default


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["n"] or 0) > 0


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS n FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s",
        (table, column),
    )
    return int(cur.fetchone()["n"] or 0) > 0


def ensure_column(cur, table: str, column: str, ddl: str) -> None:
    if table_exists(cur, table) and not column_exists(cur, table, column):
        cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {ddl}")


def fetch_one(cur, table: str, a: argparse.Namespace) -> dict[str, Any] | None:
    w, p = scope_where(a)
    cur.execute(f"SELECT * FROM {table} WHERE {w} ORDER BY created_at DESC LIMIT 1", p)
    return cur.fetchone()


def risk_is_actionable(risk_level: str, risk_score: float, threshold: float) -> bool:
    return risk_level.lower() in {"low", "warning", "high", "critical"} and risk_score >= threshold


def action_set_for_pattern(pattern: str, catalog_key: str, risk_score: float, root_cause: str, failure_mechanism: str = "unknown") -> list[tuple[str, str, str, float]]:
    # tuple: action_type, recommended_action, evidence_metric, evidence_value
    if pattern == "stable" or catalog_key == "none":
        return [("no action", "no action", "overall_risk_score", risk_score)]
    if pattern == "localized_failure" or catalog_key == "localized_reliability":
        if failure_mechanism == "identity_integrity_breakage":
            return [
                ("identity propagation audit", "Validate uid/login_id propagation for the concentrated app-version segment before using login-user or UV KPIs.", "failure_mechanism", 1.0),
                ("app version tagging audit", "Inspect app release tagging initialization and login cookie handling for the affected app version.", "mechanism_source", 1.0),
                ("localized KPI annotation", "Annotate UV/login-based dashboards for the affected segment and avoid extrapolating to total traffic.", "overall_risk_score", risk_score),
            ]
        if failure_mechanism == "semantic_attribution_distortion":
            return [
                ("url mapping validation", "Validate SDK URL/category attribution mapping and confirm whether order URLs collapsed into a single category.", "failure_mechanism", 1.0),
                ("sdk compatibility review", "Review SDK version tagging contract, route mapping, and payload serialization for the concentrated SDK segment.", "mechanism_source", 1.0),
                ("category KPI annotation", "Annotate product/category attribution KPIs until URL semantic distribution is recovered.", "overall_risk_score", risk_score),
            ]
        return [
            ("segment isolation audit", "Identify the concentrated segment and isolate the affected version/client/user cohort before broad operational action.", "risk_pattern", 1.0),
            ("collection completeness audit", "Audit collector delivery, beacon acceptance, retry, and payload contract for the localized root-cause candidate.", "root_cause_candidate", 1.0),
            ("localized KPI annotation", "Annotate dashboards for the affected segment and avoid extrapolating the issue to total business performance.", "overall_risk_score", risk_score),
        ]
    if pattern == "systemic_failure" or catalog_key == "systemic_reliability":
        return [
            ("collector health check", "Validate collector ingest, queue, retry, and beacon delivery health across platforms.", "risk_pattern", 1.0),
            ("pipeline validation", "Run source-to-canonical and Web-to-WC reconciliation checks before using affected KPIs.", "overall_risk_score", risk_score),
            ("decision freeze", "Freeze campaign/product decisions that depend on the affected telemetry until systemic recovery is confirmed.", "authority_risk_level", risk_score),
        ]
    if pattern == "silent_distortion" or catalog_key == "critical_kpi_distortion":
        return [
            ("critical KPI validation", "Validate purchase/conversion/payment events separately from PV/UV volume before business interpretation.", "risk_pattern", 1.0),
            ("dashboard KPI annotation", "Annotate conversion and revenue-proxy dashboards with reliability risk and confidence context.", "overall_risk_score", risk_score),
            ("business decision hold", "Hold marketing or funnel decisions that rely on critical events until event-level collection is recovered.", "authority_risk_level", risk_score),
        ]
    if pattern == "reconciliation_failure" or catalog_key == "reconciliation_reliability":
        return [
            ("cross-domain reconciliation", "Compare Web/WC behavior, transaction, and state records to locate where operational facts diverge.", "risk_pattern", 1.0),
            ("mapping validation", "Validate behavior-to-transaction and transaction-to-state mapping completeness and replay mapping if needed.", "overall_risk_score", risk_score),
            ("orphan/missing audit", "Audit behavior-only, transaction-only, orphan state, and transaction-without-state records.", "root_cause_candidate", 1.0),
        ]
    if pattern == "interpretation_failure" or catalog_key == "interpretation_reliability":
        return [
            ("evidence-bound review", "Review whether the explanation and recommended action are fully supported by measurement evidence.", "risk_pattern", 1.0),
            ("human review required", "Require human validation before operational execution because interpretation confidence is uncertain.", "overall_risk_score", risk_score),
        ]
    return [
        ("reliability investigation", "Collect additional evidence and classify the emerging reliability degradation pattern before taking broad action.", "risk_pattern", 1.0),
        ("monitoring annotation", "Annotate dashboards with emerging reliability degradation and monitor recurrence.", "overall_risk_score", risk_score),
    ]


def obs_reference_actions_for_context(obs_rows: list[dict[str, Any]], evidence_signal: str, root_cause_candidate: str, risk_score: float) -> list[tuple[str, str, str, float, str]]:
    """Return reference-only OBS actions.

    These actions do not drive Authority Risk. They explain where an operator or engineer
    should inspect the observability evidence after Authority Pattern/Risk has already
    selected the primary action catalog.
    tuple: action_type, recommended_action, evidence_metric, evidence_value, reference_reason
    """
    actions: list[tuple[str, str, str, float, str]] = []
    seen: set[str] = set()

    def add(key: str, action_type: str, recommended_action: str, metric: str, value: float, reason: str) -> None:
        if key in seen:
            return
        seen.add(key)
        actions.append((action_type, recommended_action, metric, value, reason))

    # Always useful for collection-gap style OBS evidence, but still reference-only.
    if evidence_signal in {"wc_collection_gap", "ios_app_version_collection_gap", "ios_sdk_version_collection_gap", "ios_purchase_event_collection_gap"}:
        add(
            "wc_collector_validation",
            "OBS reference: WC collector validation",
            "Reference check: validate WC collector delivery, beacon acceptance, retry, and ingestion health. This supports explanation only; Authority Risk is pattern-driven.",
            "evidence_signal",
            risk_score,
            f"OBS reference action selected because evidence_signal={evidence_signal}; authority action remains pattern-driven.",
        )

    for row in obs_rows[:5]:
        dim = str(row.get("root_cause_dimension") or "").lower()
        val = str(row.get("root_cause_value") or root_cause_candidate or "UNKNOWN")
        conf = f(row, "root_cause_confidence", 0.0)
        short_val = val if len(val) <= 96 else val[:93] + "..."
        if "app_version" in dim:
            add(
                "app_version_audit",
                "OBS reference: app version tagging audit",
                f"Reference check: inspect release/tagging initialization for app version segment {short_val}.",
                "root_cause_confidence",
                conf,
                f"OBS top segment dimension={dim}; value={short_val}; confidence={conf:.3f}.",
            )
        elif "sdk_version" in dim or dim == "app_sdk":
            add(
                "sdk_compatibility_review",
                "OBS reference: SDK compatibility review",
                f"Reference check: validate SDK beacon dispatch, initialization, and payload contract for {short_val}.",
                "root_cause_confidence",
                conf,
                f"OBS top segment dimension={dim}; value={short_val}; confidence={conf:.3f}.",
            )
        elif "url" in dim or "surface" in dim or "path" in dim:
            add(
                "url_tagging_audit",
                "OBS reference: URL / journey tagging audit",
                f"Reference check: inspect tagging coverage and event mapping for surface path {short_val}.",
                "root_cause_confidence",
                conf,
                f"OBS top segment dimension={dim}; value={short_val}; confidence={conf:.3f}.",
            )
        elif "client" in dim or "browser" in dim or "os" in dim or "platform" in dim:
            add(
                "client_coverage_review",
                "OBS reference: client/platform coverage review",
                f"Reference check: inspect client, platform, browser, or OS-specific collection coverage for {short_val}.",
                "root_cause_confidence",
                conf,
                f"OBS top segment dimension={dim}; value={short_val}; confidence={conf:.3f}.",
            )

    return actions


def main() -> int:
    a = parse_args()
    c = conn(a)
    try:
        with c.cursor() as cur:
            for col, ddl in {
                "action_catalog_version": "VARCHAR(80) NULL",
                "action_catalog_key": "VARCHAR(128) NULL",
                "risk_classification": "VARCHAR(128) NULL",
                "authority_risk_level": "VARCHAR(64) NULL",
                "confidence_level": "VARCHAR(64) NULL",
                "root_cause_candidate": "VARCHAR(128) NULL",
                "failure_mechanism": "VARCHAR(128) NULL",
                "mechanism_source": "VARCHAR(128) NULL",
                "mechanism_confidence": "DOUBLE NULL",
                "action_is_risk_engine": "TINYINT NULL",
                "evidence_signal": "VARCHAR(128) NULL",
                "mapping_rule_id": "VARCHAR(128) NULL",
                "catalog_selection_reason": "TEXT NULL",
                "action_catalog_mode": "VARCHAR(80) NULL",
                "action_catalog_source": "VARCHAR(80) NULL",
                "risk_pattern": "VARCHAR(80) NULL",
                "pattern_confidence": "DOUBLE NULL",
                "pattern_action_rule_id": "VARCHAR(128) NULL",
                "pattern_action_reason": "TEXT NULL",
                "action_layer": "VARCHAR(80) NULL",
                "reference_action_source": "VARCHAR(80) NULL",
                "reference_action_reason": "TEXT NULL",
                "authority_action_rank": "INT NULL",
                "reference_action_rank": "INT NULL",
            }.items():
                ensure_column(cur, "action_recommendation_day_v05", col, ddl)

            w, p = scope_where(a)
            if a.truncate_target:
                cur.execute(f"DELETE FROM action_recommendation_day_v05 WHERE {w}", p)

            risk = fetch_one(cur, "unified_reliability_score_day_v05", a)
            semantic = fetch_one(cur, "semantic_interpretation_day_v05", a)
            obs_rows: list[dict[str, Any]] = []
            if table_exists(cur, "r_v05_observability_interpretation_day"):
                cur.execute(
                    """
                    SELECT root_cause_rank, root_cause_dimension, root_cause_value, root_cause_confidence, affected_metrics, analysis_summary
                    FROM r_v05_observability_interpretation_day
                    WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
                    ORDER BY root_cause_rank ASC LIMIT 10
                    """,
                    (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
                )
                obs_rows = list(cur.fetchall())
            if not risk or not semantic:
                raise RuntimeError("missing unified risk or semantic classification row; Step5 action must run after risk and semantic builders")

            risk_score = f(risk, "overall_risk_score")
            risk_level = s(risk, "final_risk_level", "stable").lower()
            classification = s(semantic, "risk_classification", s(semantic, "dominant_semantic_risk", "None"))
            catalog_key = s(semantic, "action_catalog_key", "none")
            confidence_level = s(semantic, "confidence_level", s(risk, "confidence_level", "unknown"))
            root_cause_candidate = s(semantic, "root_cause_candidate", "UNKNOWN_ROOT_CAUSE")
            narrative = s(semantic, "risk_narrative", "")
            evidence_signal = s(semantic, "evidence_signal", "none")
            evidence_metric = s(semantic, "evidence_metric", "none")
            evidence_value = f(semantic, "evidence_value", risk_score)
            mapping_rule_id = s(semantic, "mapping_rule_id", "UNKNOWN_MAPPING_RULE")
            catalog_selection_reason = s(semantic, "catalog_selection_reason", "Catalog selected from pattern classification knowledge base.")
            risk_pattern = s(semantic, "risk_pattern", s(risk, "risk_pattern", "stable"))
            pattern_confidence = f(semantic, "pattern_confidence", f(risk, "pattern_confidence"))
            failure_mechanism = s(semantic, "failure_mechanism", s(risk, "failure_mechanism", "none" if risk_pattern == "stable" else "unknown"))
            mechanism_source = s(semantic, "mechanism_source", s(risk, "mechanism_source", "none" if risk_pattern == "stable" else "unknown"))
            mechanism_confidence = f(semantic, "mechanism_confidence", f(risk, "mechanism_confidence", 0.0))
            pattern_action_rule_id = f"PATTERN_{risk_pattern.upper()}_TO_ACTION_CATALOG_V1"
            pattern_action_reason = (
                f"action catalog selected from risk_pattern={risk_pattern}; "
                f"failure_mechanism={failure_mechanism}; mechanism_source={mechanism_source}; "
                f"catalog_key={catalog_key}; classification={classification}; "
                "action_is_risk_engine=false; OBS/root-cause is reference explanation only."
            )
            is_baseline = (a.scenario_name or "").lower() in {"baseline", "normal", "stable"}

            if is_baseline or classification in {"None", "", "none"} or not risk_is_actionable(risk_level, risk_score, a.action_threshold):
                risk_pattern = "stable"
                catalog_key = "none"
                classification = "None"
                actions = [("no action", "no action", "overall_risk_score", risk_score)]
            else:
                actions = action_set_for_pattern(risk_pattern, catalog_key, risk_score, root_cause_candidate, failure_mechanism)
            reference_actions = [] if risk_pattern == "stable" else obs_reference_actions_for_context(obs_rows, evidence_signal, root_cause_candidate, risk_score)

            payload_base = {
                "architecture_layer": "KNOWLEDGE_BASE_ACTION_CATALOG",
                "principle": "Pattern-driven Action Catalog maps risk_pattern + classification + risk level + confidence to actions; it does not compute risk.",
                "action_catalog_version": CATALOG_VERSION,
                "action_catalog_mode": "pattern_driven",
                "action_catalog_source": "authority_pattern_layer",
                "risk_source": {
                    "table": "unified_reliability_score_day_v05",
                    "risk_model_version": s(risk, "risk_model_version", "unknown"),
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "risk_pattern": risk_pattern,
                    "pattern_confidence": pattern_confidence,
                    "failure_mechanism": failure_mechanism,
                    "mechanism_source": mechanism_source,
                    "mechanism_confidence": mechanism_confidence,
                    "confidence_separate_from_risk": int(f(risk, "confidence_separate_from_risk")) == 1,
                },
                "classification": classification,
                "catalog_key": catalog_key,
                "confidence_level": confidence_level,
                "root_cause_candidate": root_cause_candidate,
                "failure_mechanism": failure_mechanism,
                "mechanism_source": mechanism_source,
                "mechanism_confidence": mechanism_confidence,
                "narrative": narrative,
                "pattern_action_rule_id": pattern_action_rule_id,
                "pattern_action_reason": pattern_action_reason,
                "catalog_selection_explainability": {
                    "evidence_signal": evidence_signal,
                    "evidence_metric": evidence_metric,
                    "evidence_value": evidence_value,
                    "mapping_rule_id": mapping_rule_id,
                    "catalog_selection_reason": catalog_selection_reason,
                },
                "reference_explanation": {
                    "obs_reference_only": True,
                    "obs_rows_used": len(obs_rows),
                    "reference_actions_count": len(reference_actions),
                },
            }

            rows: list[tuple[Any, ...]] = []

            for idx, (action_type, recommended_action, action_metric, action_value) in enumerate(actions, start=1):
                payload = json.dumps({**payload_base, "action_type": action_type, "action_layer": "authority_action"}, ensure_ascii=False)
                rows.append(
                    (
                        a.run_id,
                        a.profile_id,
                        a.source_gen_run_id,
                        a.target_date,
                        a.scenario_name,
                        idx,
                        action_type,
                        recommended_action,
                        pattern_action_reason,
                        "semantic_interpretation_day_v05",
                        action_metric,
                        action_value,
                        payload,
                        CATALOG_VERSION,
                        catalog_key,
                        classification,
                        risk_level,
                        confidence_level,
                        root_cause_candidate,
                        failure_mechanism,
                        mechanism_source,
                        mechanism_confidence,
                        0,
                        evidence_signal,
                        mapping_rule_id,
                        catalog_selection_reason,
                        "pattern_driven",
                        "authority_pattern_layer",
                        risk_pattern,
                        pattern_confidence,
                        pattern_action_rule_id,
                        pattern_action_reason,
                        "authority_action",
                        "authority_pattern_layer",
                        pattern_action_reason,
                        idx,
                        None,
                    )
                )

            reference_start_rank = len(actions) + 1
            for ref_idx, (action_type, recommended_action, action_metric, action_value, reference_reason) in enumerate(reference_actions, start=1):
                payload = json.dumps({**payload_base, "action_type": action_type, "action_layer": "reference_obs_action", "reference_action_reason": reference_reason}, ensure_ascii=False)
                rows.append(
                    (
                        a.run_id,
                        a.profile_id,
                        a.source_gen_run_id,
                        a.target_date,
                        a.scenario_name,
                        reference_start_rank + ref_idx - 1,
                        action_type,
                        recommended_action,
                        reference_reason,
                        "r_v05_observability_interpretation_day",
                        action_metric,
                        action_value,
                        payload,
                        CATALOG_VERSION,
                        catalog_key,
                        classification,
                        risk_level,
                        confidence_level,
                        root_cause_candidate,
                        failure_mechanism,
                        mechanism_source,
                        mechanism_confidence,
                        0,
                        evidence_signal,
                        mapping_rule_id,
                        catalog_selection_reason,
                        "reference_explanation",
                        "obs_reference_layer",
                        risk_pattern,
                        pattern_confidence,
                        "OBS_REFERENCE_TO_SUPPORTING_ACTION_V1",
                        reference_reason,
                        "reference_obs_action",
                        "obs_reference_layer",
                        reference_reason,
                        None,
                        ref_idx,
                    )
                )

            cur.executemany(
                """
                INSERT INTO action_recommendation_day_v05(
                  run_id,profile_id,source_gen_run_id,target_date,scenario_name,
                  action_rank,action_type,recommended_action,evidence_summary,evidence_table,evidence_metric,evidence_value,action_payload_json,
                  action_catalog_version,action_catalog_key,risk_classification,authority_risk_level,confidence_level,root_cause_candidate,failure_mechanism,mechanism_source,mechanism_confidence,action_is_risk_engine,
                  evidence_signal,mapping_rule_id,catalog_selection_reason,
                  action_catalog_mode,action_catalog_source,risk_pattern,pattern_confidence,pattern_action_rule_id,pattern_action_reason,
                  action_layer,reference_action_source,reference_action_reason,authority_action_rank,reference_action_rank
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                rows,
            )
        c.commit()
        first_action = rows[0][7] if rows else "none"
        print(
            f"[PATTERN_ACTION_CATALOG] version={CATALOG_VERSION} mode=pattern_driven source=authority_pattern_layer "
            f"pattern={risk_pattern} pattern_confidence={pattern_confidence:.6f} catalog={catalog_key} classification={classification} "
            f"risk_level={risk_level} authority_actions={len(actions)} reference_obs_actions={len(reference_actions)} "
            f"action_count={len(rows)} first_action={first_action} action_is_risk_engine=0"
        )
        return 0
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
