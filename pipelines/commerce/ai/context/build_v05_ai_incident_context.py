#!/usr/bin/env python3
"""
v0.5 AI incident context builder with batch reliability context.

Hotfix:
- Avoid json.dumps circular reference failure by creating a JSON-safe deep copy.
- Keep AI context evidence-constrained.
- Do not infer new authoritative risk/action. v0.5 semantic/risk/action remains authoritative.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

import pymysql


def to_json_safe(value: Any, seen: set[int] | None = None) -> Any:
    """Return a JSON-serializable deep copy.

    This avoids:
    - Circular reference detected
    - Decimal/date/datetime serialization errors
    - bytes serialization errors
    - driver-specific row/object surprises
    """
    if seen is None:
        seen = set()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    obj_id = id(value)
    if isinstance(value, (dict, list, tuple, set)):
        if obj_id in seen:
            return "[CircularReference]"
        seen.add(obj_id)
        try:
            if isinstance(value, dict):
                return {str(k): to_json_safe(v, seen) for k, v in value.items()}
            if isinstance(value, (list, tuple, set)):
                return [to_json_safe(v, seen) for v in value]
        finally:
            seen.discard(obj_id)

    # Last resort: stable string representation.
    return str(value)


def json_dumps_safe(value: Any) -> str:
    return json.dumps(to_json_safe(value), ensure_ascii=False, sort_keys=True)


def connect(args):
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


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS c FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(cur.fetchone()["c"]) > 0


def columns(cur, table: str) -> List[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s ORDER BY ordinal_position",
        (table,),
    )
    return [r["column_name"] for r in cur.fetchall()]


def one(cur, sql: str, params: tuple) -> Dict[str, Any]:
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return dict(row)


def all_rows(cur, sql: str, params: tuple) -> List[Dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def fetch_if_exists(cur, table: str, sql: str, params: tuple, default):
    if not table_exists(cur, table):
        return default
    return one(cur, sql, params) if isinstance(default, dict) else all_rows(cur, sql, params)


def get_context(cur, profile_id: str, target_date: str, run_id: int, source_gen_run_id: int, scenario_name: str) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "profile_id": profile_id,
        "target_date": target_date,
        "run_id": run_id,
        "source_gen_run_id": source_gen_run_id,
        "scenario_name": scenario_name,
    }

    if table_exists(cur, "v05_ml_feature_snapshot_day"):
        ctx["ml_feature_snapshot"] = one(cur, """
            SELECT * FROM v05_ml_feature_snapshot_day
            WHERE profile_id=%s AND target_date=%s AND run_id=%s AND scenario_name=%s
            LIMIT 1
        """, (profile_id, target_date, run_id, scenario_name))

    if table_exists(cur, "v05_reconciliation_measurement_day"):
        ctx["reconciliation"] = one(cur, """
            SELECT * FROM v05_reconciliation_measurement_day
            WHERE profile_id=%s AND target_date=%s AND run_id=%s AND scenario_name=%s
            LIMIT 1
        """, (profile_id, target_date, run_id, scenario_name))

    if table_exists(cur, "semantic_interpretation_day_v05"):
        ctx["semantic"] = one(cur, """
            SELECT * FROM semantic_interpretation_day_v05
            WHERE profile_id=%s AND target_date=%s AND run_id=%s AND scenario_name=%s
            LIMIT 1
        """, (profile_id, target_date, run_id, scenario_name))

    if table_exists(cur, "unified_reliability_score_day_v05"):
        ctx["unified_score"] = one(cur, """
            SELECT * FROM unified_reliability_score_day_v05
            WHERE profile_id=%s AND target_date=%s AND run_id=%s AND scenario_name=%s
            LIMIT 1
        """, (profile_id, target_date, run_id, scenario_name))

    if table_exists(cur, "action_recommendation_day_v05"):
        cols = set(columns(cur, "action_recommendation_day_v05"))
        order_by = "action_rank" if "action_rank" in cols else ("priority" if "priority" in cols else "1")
        ctx["action"] = one(cur, f"""
            SELECT * FROM action_recommendation_day_v05
            WHERE profile_id=%s AND target_date=%s AND run_id=%s AND scenario_name=%s
            ORDER BY {order_by} LIMIT 1
        """, (profile_id, target_date, run_id, scenario_name))

    if table_exists(cur, "r_batch_distribution_analysis_day"):
        ctx["batch_distribution"] = all_rows(cur, """
            SELECT *
            FROM r_batch_distribution_analysis_day
            WHERE profile_id=%s AND dt=%s AND run_id=%s AND scenario_name=%s
            LIMIT 50
        """, (profile_id, target_date, run_id, scenario_name))
    else:
        ctx["batch_distribution"] = []

    batch_anomaly = {}
    for table in ("batch_behavior_anomaly_day", "v05_batch_behavior_anomaly_day"):
        if table_exists(cur, table):
            cols = set(columns(cur, table))
            dc = "dt" if "dt" in cols else "target_date"
            signal = "anomaly_signal" if "anomaly_signal" in cols else ("dominant_batch_signal" if "dominant_batch_signal" in cols else None)
            score = "anomaly_score" if "anomaly_score" in cols else ("batch_anomaly_score" if "batch_anomaly_score" in cols else None)
            select_cols = ["*"]
            order = f"ORDER BY {score} DESC" if score else ""
            batch_anomaly = one(cur, f"""
                SELECT {', '.join(select_cols)}
                FROM {table}
                WHERE profile_id=%s AND {dc}=%s AND run_id=%s AND scenario_name=%s
                {order} LIMIT 1
            """, (profile_id, target_date, run_id, scenario_name))
            break
    ctx["batch_anomaly"] = batch_anomaly

    return to_json_safe(ctx)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--truncate-target", action="store_true")
    args = p.parse_args()

    conn = connect(args)
    try:
        with conn.cursor() as cur:
            if not table_exists(cur, "v05_ai_incident_context_day"):
                raise RuntimeError("missing table v05_ai_incident_context_day")

            table_cols = set(columns(cur, "v05_ai_incident_context_day"))
            ctx = get_context(cur, args.profile_id, args.target_date, args.run_id, args.source_gen_run_id, args.scenario_name)
            feature = ctx.get("ml_feature_snapshot") or {}
            batch_anomaly = ctx.get("batch_anomaly") or {}

            payload_obj = {
                "context_source": "evidence_constrained_v05_ai_context_with_batch_features",
                "authority_policy": {
                    "v05_commerce_semantic_risk_action": "authoritative",
                    "v04_measurement_r_analytics": "evidence_only",
                    "ai_context": "supplementary_evidence_pack",
                },
                "evidence_tables_used": [
                    "v05_ml_feature_snapshot_day",
                    "v05_reconciliation_measurement_day",
                    "semantic_interpretation_day_v05",
                    "unified_reliability_score_day_v05",
                    "action_recommendation_day_v05",
                    "r_batch_distribution_analysis_day",
                    "batch_behavior_anomaly_day",
                    "v05_batch_behavior_anomaly_day",
                ],
                "context": ctx,
            }
            payload = json_dumps_safe(payload_obj)
            batch_payload = json_dumps_safe({
                "batch_distribution": ctx.get("batch_distribution", []),
                "batch_anomaly": batch_anomaly,
            })

            if args.truncate_target:
                delete_where = ["profile_id=%s"]
                delete_params: List[Any] = [args.profile_id]
                if "target_date" in table_cols:
                    delete_where.append("target_date=%s")
                    delete_params.append(args.target_date)
                elif "dt" in table_cols:
                    delete_where.append("dt=%s")
                    delete_params.append(args.target_date)
                if "run_id" in table_cols:
                    delete_where.append("run_id=%s")
                    delete_params.append(args.run_id)
                if "source_gen_run_id" in table_cols:
                    delete_where.append("source_gen_run_id=%s")
                    delete_params.append(args.source_gen_run_id)
                if "scenario_name" in table_cols:
                    delete_where.append("scenario_name=%s")
                    delete_params.append(args.scenario_name)
                cur.execute(
                    f"DELETE FROM v05_ai_incident_context_day WHERE {' AND '.join(delete_where)}",
                    tuple(delete_params),
                )

            values: Dict[str, Any] = {
                "profile_id": args.profile_id,
                "target_date": args.target_date,
                "dt": args.target_date,
                "run_id": args.run_id,
                "source_gen_run_id": args.source_gen_run_id,
                "scenario_name": args.scenario_name,
                "dominant_semantic_risk": feature.get("dominant_semantic_risk") or "None",
                "overall_risk_score": feature.get("overall_risk_score") or 0,
                "final_risk_level": feature.get("final_risk_level") or "UNKNOWN",
                "recommended_action": feature.get("recommended_action") or "no action",
                "context_payload_json": payload,
                "incident_context_json": payload,
                "batch_context_json": batch_payload,
                "batch_anomaly_signal": batch_anomaly.get("anomaly_signal") or batch_anomaly.get("dominant_batch_signal") or feature.get("batch_anomaly_signal") or "none",
                "batch_anomaly_score": batch_anomaly.get("anomaly_score") or batch_anomaly.get("batch_anomaly_score") or feature.get("batch_anomaly_score") or 0,
                "batch_distribution_risk_score": feature.get("batch_distribution_risk_score") or 0,
            }

            insert_cols = [c for c in values if c in table_cols]
            if not insert_cols:
                raise RuntimeError("v05_ai_incident_context_day has no compatible columns")

            cur.execute(
                f"INSERT INTO v05_ai_incident_context_day ({', '.join(insert_cols)}) "
                f"VALUES ({', '.join(['%s'] * len(insert_cols))})",
                tuple(values[c] for c in insert_cols),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(
        "[OK] build_v05_ai_incident_context json-safe "
        f"profile_id={args.profile_id} target_date={args.target_date} "
        f"run_id={args.run_id} scenario={args.scenario_name}"
    )


if __name__ == "__main__":
    main()
