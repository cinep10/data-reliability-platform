#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
from datetime import date
from typing import Any, Dict, Iterable, Optional
import pymysql


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


def has_column(cur, db_name: str, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s AND column_name=%s
        """,
        (db_name, table, column),
    )
    return int(cur.fetchone()["cnt"]) == 1


def table_exists(cur, db_name: str, table: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.tables
        WHERE table_schema=%s AND table_name=%s
        """,
        (db_name, table),
    )
    return int(cur.fetchone()["cnt"]) == 1


def sql_value(row: Optional[Dict[str, Any]], key: str, default: Any = 0) -> Any:
    if not row:
        return default
    value = row.get(key)
    return default if value is None else value


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def first_existing(cur, db_name: str, table: str, candidates: Iterable[str]) -> Optional[str]:
    for c in candidates:
        if has_column(cur, db_name, table, c):
            return c
    return None


def select_one(cur, query: str, params: tuple) -> Optional[Dict[str, Any]]:
    cur.execute(query, params)
    return cur.fetchone()


def latest_run_id(cur, profile_id: str, dt: str) -> str:
    # Prefer the run_id that completed unified score/action for this profile/date.
    for table in ["unified_reliability_score_day", "semantic_interpretation_day", "r_reliability_analysis_result_day"]:
        cur.execute(
            f"SELECT run_id FROM {table} WHERE profile_id=%s AND dt=%s ORDER BY created_at DESC LIMIT 1",
            (profile_id, dt),
        )
        row = cur.fetchone()
        if row and row.get("run_id") is not None:
            return str(row["run_id"])
    return ""


def label_family(dominant: str, final_level: str, score: float) -> str:
    d = (dominant or "").lower()
    f = (final_level or "").lower()
    if score <= 0 or f in {"stable", "low"}:
        return "stable"
    if "complete" in d:
        return "completeness_risk"
    if "time" in d:
        return "timeliness_risk"
    if "integr" in d:
        return "integrity_risk"
    if "consisten" in d:
        return "consistency_risk"
    if "avail" in d:
        return "availability_risk"
    return f"{d or 'unknown'}_risk"


def main():
    ap = argparse.ArgumentParser(description="Build v0.4 Phase4 ML feature snapshot from Phase3 decision tables.")
    ap.add_argument("--db-host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    ap.add_argument("--db-user", default=os.getenv("DB_USER", "nethru"))
    ap.add_argument("--db-pass", default=os.getenv("DB_PASSWORD", "nethru1234"))
    ap.add_argument("--db-name", default=os.getenv("DB_NAME", "weblog"))
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt", required=True)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--scenario-name", default="")
    args = ap.parse_args()

    conn = connect(args)
    try:
        with conn.cursor() as cur:
            for t in [
                "r_reliability_analysis_result_day",
                "semantic_interpretation_day",
                "unified_reliability_score_day",
                "action_recommendation_day",
            ]:
                if not table_exists(cur, args.db_name, t):
                    raise RuntimeError(f"required Phase3 table missing: {t}")

            run_id = args.run_id or latest_run_id(cur, args.profile_id, args.dt)

            analysis = select_one(
                cur,
                """
                SELECT * FROM r_reliability_analysis_result_day
                WHERE profile_id=%s AND dt=%s AND run_id=%s
                LIMIT 1
                """,
                (args.profile_id, args.dt, run_id),
            )
            semantic = select_one(
                cur,
                """
                SELECT * FROM semantic_interpretation_day
                WHERE profile_id=%s AND dt=%s AND run_id=%s
                LIMIT 1
                """,
                (args.profile_id, args.dt, run_id),
            )
            unified = select_one(
                cur,
                """
                SELECT * FROM unified_reliability_score_day
                WHERE profile_id=%s AND dt=%s AND run_id=%s
                LIMIT 1
                """,
                (args.profile_id, args.dt, run_id),
            )
            action = select_one(
                cur,
                """
                SELECT * FROM action_recommendation_day
                WHERE profile_id=%s AND dt=%s AND run_id=%s
                LIMIT 1
                """,
                (args.profile_id, args.dt, run_id),
            )
            if not (analysis and semantic and unified and action):
                raise RuntimeError(f"missing Phase3 decision rows profile_id={args.profile_id} dt={args.dt} run_id={run_id}")

            realism = {}
            if table_exists(cur, args.db_name, "measurement_realism_day"):
                realism = select_one(
                    cur,
                    """
                    SELECT * FROM measurement_realism_day
                    WHERE profile_id=%s AND dt=%s AND run_id=%s
                    LIMIT 1
                    """,
                    (args.profile_id, args.dt, run_id),
                ) or {}

            dominant = str(sql_value(semantic, "dominant_semantic_risk", "Unknown"))
            final_level = str(sql_value(unified, "final_risk_level", "UNKNOWN"))
            overall = to_float(sql_value(unified, "overall_risk_score", 0))
            scenario = args.scenario_name or str(sql_value(unified, "scenario_name", sql_value(analysis, "scenario_name", "")))

            feature = {
                "profile_id": args.profile_id,
                "dt": args.dt,
                "run_id": run_id,
                "scenario_name": scenario,
                "drift_score": to_float(sql_value(analysis, "drift_score", 0)),
                "propagation_score": to_float(sql_value(analysis, "propagation_score", 0)),
                "amplification_score": to_float(sql_value(analysis, "amplification_score", 0)),
                "distortion_score": to_float(sql_value(analysis, "distortion_score", 0)),
                "baseline_delta": to_float(sql_value(analysis, "baseline_delta", 0)),
                "correlation_score": to_float(sql_value(analysis, "correlation_score", 0)),
                "integrity_score": to_float(sql_value(semantic, "integrity_score", 0)),
                "completeness_score": to_float(sql_value(semantic, "completeness_score", 0)),
                "timeliness_score": to_float(sql_value(semantic, "timeliness_score", 0)),
                "consistency_score": to_float(sql_value(semantic, "consistency_score", 0)),
                "availability_score": to_float(sql_value(semantic, "availability_score", 0)),
                "semantic_confidence": to_float(sql_value(semantic, "semantic_confidence", 0)),
                "overall_risk_score": overall,
                "final_risk_level": final_level,
                "dominant_semantic_risk": dominant,
                "recommended_action": str(sql_value(action, "recommended_action", "manual investigation")),
                "priority": str(sql_value(action, "priority", "P3")),
                "delta_source_type": str(sql_value(semantic, "delta_source_type", "UNKNOWN")),
                "fallback_used": int(to_float(sql_value(semantic, "fallback_used", 0))),
                "direct_completeness_delta": to_float(sql_value(realism, "direct_completeness_delta", sql_value(semantic, "direct_completeness_delta", 0))),
                "direct_timeliness_delta": to_float(sql_value(realism, "direct_timeliness_delta", sql_value(semantic, "direct_timeliness_delta", 0))),
                "direct_availability_delta": to_float(sql_value(realism, "direct_availability_delta", sql_value(semantic, "direct_availability_delta", 0))),
                "direct_integrity_delta": to_float(sql_value(realism, "direct_integrity_delta", sql_value(semantic, "direct_integrity_delta", 0))),
            }
            feature["label_risk_family"] = label_family(dominant, final_level, overall)
            feature["label_action"] = feature["recommended_action"]
            feature_json = json.dumps(
                {"analysis": analysis, "semantic": semantic, "unified": unified, "action": action, "realism": realism},
                default=str,
                ensure_ascii=False,
            )

            cur.execute(
                "DELETE FROM ml_feature_snapshot_day WHERE profile_id=%s AND dt=%s AND run_id=%s",
                (args.profile_id, args.dt, run_id),
            )
            cur.execute(
                """
                INSERT INTO ml_feature_snapshot_day (
                  profile_id, dt, run_id, scenario_name,
                  drift_score, propagation_score, amplification_score, distortion_score, baseline_delta, correlation_score,
                  integrity_score, completeness_score, timeliness_score, consistency_score, availability_score, semantic_confidence,
                  overall_risk_score, final_risk_level, dominant_semantic_risk, recommended_action, priority,
                  delta_source_type, fallback_used,
                  direct_completeness_delta, direct_timeliness_delta, direct_availability_delta, direct_integrity_delta,
                  label_risk_family, label_action, feature_json
                ) VALUES (
                  %(profile_id)s, %(dt)s, %(run_id)s, %(scenario_name)s,
                  %(drift_score)s, %(propagation_score)s, %(amplification_score)s, %(distortion_score)s, %(baseline_delta)s, %(correlation_score)s,
                  %(integrity_score)s, %(completeness_score)s, %(timeliness_score)s, %(consistency_score)s, %(availability_score)s, %(semantic_confidence)s,
                  %(overall_risk_score)s, %(final_risk_level)s, %(dominant_semantic_risk)s, %(recommended_action)s, %(priority)s,
                  %(delta_source_type)s, %(fallback_used)s,
                  %(direct_completeness_delta)s, %(direct_timeliness_delta)s, %(direct_availability_delta)s, %(direct_integrity_delta)s,
                  %(label_risk_family)s, %(label_action)s, %(feature_json)s
                )
                """,
                {**feature, "feature_json": feature_json},
            )
        conn.commit()
        print(f"[OK] built ml_feature_snapshot_day profile_id={args.profile_id} dt={args.dt} run_id={run_id} label={feature['label_risk_family']} score={overall}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
