#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

import pymysql


BEHAVIOR_ONLY_SCENARIOS = {"behavior_only_anomaly"}
TRANSACTION_MISSING_SCENARIOS = {"transaction_missing_anomaly"}
STATE_MISSING_SCENARIOS = {"state_missing_anomaly"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate v0.5 commerce authoritative run with scenario-aware source/reconciliation contracts."
    )
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--allow-low-risk-anomaly", action="store_true")

    # Scenario contract thresholds. These are validation gates, not risk scoring.
    p.add_argument("--transaction-missing-match-rate-threshold", type=float, default=0.80)
    p.add_argument("--state-missing-match-rate-threshold", type=float, default=0.80)
    p.add_argument(
       '--calibration-config',
       default='pipelines/commerce/configs/v05_validation_contracts.yaml'
    )
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
        autocommit=True,
    )


def table_exists(c, table: str) -> bool:
    with c.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = DATABASE() AND table_name = %s
            """,
            (table,),
        )
        return int(cur.fetchone()["cnt"]) > 0


def columns(c, table: str) -> set[str]:
    with c.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s
            """,
            (table,),
        )
        return {str(r["column_name"]) for r in cur.fetchall()}


def count_rows(c, table: str, a: argparse.Namespace, date_col: str = "target_date") -> int:
    if not table_exists(c, table):
        return 0
    cols = columns(c, table)
    where = []
    params: list[Any] = []
    if "profile_id" in cols:
        where.append("profile_id=%s")
        params.append(a.profile_id)
    if date_col in cols:
        where.append(f"{date_col}=%s")
        params.append(a.target_date)
    elif "dt" in cols:
        where.append("dt=%s")
        params.append(a.target_date)
    if "run_id" in cols:
        where.append("run_id=%s")
        params.append(a.run_id)
    if "source_gen_run_id" in cols and table.startswith("canonical_"):
        where.append("source_gen_run_id=%s")
        params.append(a.source_gen_run_id)
    sql = f"SELECT COUNT(*) AS cnt FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    with c.cursor() as cur:
        cur.execute(sql, tuple(params))
        return int(cur.fetchone()["cnt"])


def fetch_one(c, table: str, a: argparse.Namespace) -> dict[str, Any] | None:
    if not table_exists(c, table):
        return None
    cols = columns(c, table)
    where = []
    params: list[Any] = []
    if "profile_id" in cols:
        where.append("profile_id=%s")
        params.append(a.profile_id)
    if "target_date" in cols:
        where.append("target_date=%s")
        params.append(a.target_date)
    elif "dt" in cols:
        where.append("dt=%s")
        params.append(a.target_date)
    if "run_id" in cols:
        where.append("run_id=%s")
        params.append(a.run_id)
    if "source_gen_run_id" in cols and table.startswith(("v05_", "reliability_", "semantic_", "unified_", "action_")):
        # Not all tables have source_gen_run_id, but when they do, keep the scope tight.
        where.append("source_gen_run_id=%s")
        params.append(a.source_gen_run_id)

    sql = f"SELECT * FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)

    # Prefer newest row without assuming semantic_confidence exists.
    order_cols = [c for c in ["created_at", "updated_at", "run_id"] if c in cols]
    if order_cols:
        sql += " ORDER BY " + ", ".join(f"{c} DESC" for c in order_cols)
    sql += " LIMIT 1"

    with c.cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchone()


def to_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default


def to_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    try:
        return int(float(v))
    except Exception:
        return default


def fail(failures: list[str], message: str) -> None:
    failures.append(message)


def check_print(label: str, value: Any) -> None:
    print(f"[CHECK] {label}: {value}")


def scenario_contract_note(scenario: str) -> str:
    if scenario == "transaction_missing_anomaly":
        return (
            "transaction_missing_anomaly means partial transaction loss / behavior-transaction reconciliation degradation. "
            "It does NOT require canonical_transaction_events=0."
        )
    if scenario == "state_missing_anomaly":
        return (
            "state_missing_anomaly allows state rows to be zero or reduced when state source is intentionally suppressed."
        )
    if scenario == "behavior_only_anomaly":
        return (
            "behavior_only_anomaly intentionally suppresses transaction/state source outputs."
        )
    return "standard scenario contract"


def main() -> int:
    a = parse_args()
    c = conn(a)
    failures: list[str] = []

    scenario = a.scenario_name
    behavior_only = scenario in BEHAVIOR_ONLY_SCENARIOS
    transaction_missing = scenario in TRANSACTION_MISSING_SCENARIOS
    state_missing = scenario in STATE_MISSING_SCENARIOS

    try:
        counts = {
            "canonical_behavior_events": count_rows(c, "canonical_behavior_events", a),
            "canonical_transaction_events": count_rows(c, "canonical_transaction_events", a),
            "canonical_state_events": count_rows(c, "canonical_state_events", a),
            "v05_reconciliation_measurement_day": count_rows(c, "v05_reconciliation_measurement_day", a),
            "reliability_analysis_result_day_v05": count_rows(c, "reliability_analysis_result_day_v05", a),
            "semantic_interpretation_day_v05": count_rows(c, "semantic_interpretation_day_v05", a),
            "unified_reliability_score_day_v05": count_rows(c, "unified_reliability_score_day_v05", a),
            "action_recommendation_day_v05": count_rows(c, "action_recommendation_day_v05", a),
        }

        for k, v in counts.items():
            check_print(k, v)

        recon = fetch_one(c, "v05_reconciliation_measurement_day", a) or {}
        sem = fetch_one(c, "semantic_interpretation_day_v05", a) or {}
        score = fetch_one(c, "unified_reliability_score_day_v05", a) or {}
        action = fetch_one(c, "action_recommendation_day_v05", a) or {}

        btmr = to_float(recon.get("behavior_transaction_match_rate"), 0.0)
        tsmr = to_float(recon.get("transaction_state_match_rate"), 0.0)
        behavior_only_count = to_int(recon.get("behavior_only_count"), 0)
        transaction_only_count = to_int(recon.get("transaction_only_count"), 0)
        tx_without_state = to_int(recon.get("transaction_without_state_count"), 0)
        orphan_state_count = to_int(recon.get("orphan_state_count"), 0)

        dom = sem.get("dominant_semantic_risk")
        overall = to_float(score.get("overall_risk_score"), -1.0)
        level = score.get("final_risk_level")
        rec = action.get("recommended_action") or action.get("action_type")

        check_print("scenario_contract", scenario_contract_note(scenario))
        check_print("behavior_transaction_match_rate", f"{btmr:.6f}")
        check_print("transaction_state_match_rate", f"{tsmr:.6f}")
        check_print("behavior_only_count", behavior_only_count)
        check_print("transaction_only_count", transaction_only_count)
        check_print("transaction_without_state_count", tx_without_state)
        check_print("orphan_state_count", orphan_state_count)
        check_print("dominant_semantic_risk", dom)
        check_print("overall_risk_score", overall)
        check_print("final_risk_level", level)
        check_print("recommended_action", rec)

        if counts["canonical_behavior_events"] <= 0:
            fail(failures, "missing rows in canonical_behavior_events")

        if behavior_only:
            if counts["canonical_transaction_events"] != 0:
                fail(failures, "behavior_only expected canonical_transaction_events=0")
            if counts["canonical_state_events"] != 0:
                fail(failures, "behavior_only expected canonical_state_events=0")
            print("[CHECK] behavior_only contract: PASS when behavior>0 and tx/state=0")

        elif transaction_missing:
            # Corrected contract:
            # transaction_missing_anomaly is partial missing / reconciliation degradation,
            # not complete transaction removal.
            if counts["canonical_transaction_events"] <= 0:
                fail(failures, "transaction_missing expected partial transaction rows > 0, not zero rows")
            if counts["v05_reconciliation_measurement_day"] <= 0:
                fail(failures, "transaction_missing missing reconciliation measurement")
            if btmr >= a.transaction_missing_match_rate_threshold:
                # If match rate is high, allow explicit missing evidence counts as alternative.
                if behavior_only_count <= 0 and transaction_only_count <= 0:
                    fail(
                        failures,
                        (
                            "transaction_missing expected behavior_transaction_match_rate "
                            f"< {a.transaction_missing_match_rate_threshold:.2f} or positive mismatch counts"
                        ),
                    )
            print(
                "[CHECK] transaction_missing contract: PASS when transaction rows exist "
                "and behavior-transaction reconciliation is degraded"
            )

        elif state_missing:
            if counts["canonical_transaction_events"] <= 0:
                fail(failures, "state_missing expected transaction rows > 0")
            # Current implementations may produce zero or partial state rows.
            # Validate by transaction-state degradation, not strict state=0.
            if counts["v05_reconciliation_measurement_day"] <= 0:
                fail(failures, "state_missing missing reconciliation measurement")
            if counts["canonical_state_events"] > 0 and tsmr >= a.state_missing_match_rate_threshold and tx_without_state <= 0:
                fail(
                    failures,
                    (
                        "state_missing expected transaction_state_match_rate "
                        f"< {a.state_missing_match_rate_threshold:.2f} or positive transaction_without_state_count"
                    ),
                )
            print(
                "[CHECK] state_missing contract: PASS when transaction exists and state linkage is missing/degraded"
            )

        else:
            if counts["canonical_transaction_events"] <= 0:
                fail(failures, "missing rows in canonical_transaction_events")
            if counts["canonical_state_events"] <= 0:
                fail(failures, "missing rows in canonical_state_events")

        for required in [
            "v05_reconciliation_measurement_day",
            "reliability_analysis_result_day_v05",
            "semantic_interpretation_day_v05",
            "unified_reliability_score_day_v05",
            "action_recommendation_day_v05",
        ]:
            if counts[required] <= 0:
                fail(failures, f"missing rows in {required}")

        if overall < 0:
            fail(failures, "overall_risk_score missing or invalid")

        if scenario != "baseline" and not a.allow_low_risk_anomaly:
            if str(level or "").lower() == "low":
                fail(failures, "anomaly scenario produced low risk without --allow-low-risk-anomaly")

        # Tuning-only warning, not a blocker.
        if transaction_missing and str(dom or "").lower() == "coupon attribution distortion":
            print(
                "[WARN] semantic tuning candidate: transaction_missing_anomaly mapped to Coupon Attribution Distortion. "
                "Consider Transaction Consistency Risk / Behavior-Transaction Reconciliation Gap mapping."
            )

        if failures:
            for fmsg in failures:
                print(f"[FAIL] {fmsg}")
            return 1

        print(f"[OK] validate_v05_commerce_run passed scenario={scenario}")
        return 0

    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
