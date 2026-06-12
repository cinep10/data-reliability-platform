#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import pymysql


def jdefault(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    return v


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build v0.5 ML feature snapshot with schema-aware rich fallback."
    )
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
    return p.parse_args()


def connect(a: argparse.Namespace):
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


def table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table,),
    )
    return int(cur.fetchone()["cnt"]) == 1


def table_meta(cur, table: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, DATA_TYPE
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = %s
        ORDER BY ORDINAL_POSITION
        """,
        (table,),
    )
    return list(cur.fetchall())


def colset(cur, table: str) -> set[str]:
    return {str(r["COLUMN_NAME"]) for r in table_meta(cur, table)}


def date_col(cols: set[str]) -> str | None:
    if "target_date" in cols:
        return "target_date"
    if "dt" in cols:
        return "dt"
    return None


def scope_where(cols: set[str], a: argparse.Namespace, include_source: bool = False) -> tuple[str, list[Any]]:
    wh: list[str] = []
    ps: list[Any] = []
    if "profile_id" in cols:
        wh.append("profile_id=%s")
        ps.append(a.profile_id)
    dc = date_col(cols)
    if dc:
        wh.append(f"{dc}=%s")
        ps.append(a.target_date)
    if "run_id" in cols:
        wh.append("run_id=%s")
        ps.append(a.run_id)
    if include_source and "source_gen_run_id" in cols:
        wh.append("source_gen_run_id=%s")
        ps.append(a.source_gen_run_id)
    if "scenario_name" in cols:
        wh.append("scenario_name=%s")
        ps.append(a.scenario_name)
    return (" AND ".join(wh) if wh else "1=1", ps)


def fetch_one(cur, table: str, a: argparse.Namespace, wanted: list[str] | None = None) -> dict[str, Any]:
    if not table_exists(cur, table):
        return {}
    cols = colset(cur, table)
    select_cols = [c for c in (wanted or sorted(cols)) if c in cols]
    if not select_cols:
        return {}
    wh, ps = scope_where(cols, a)
    order_cols = [c for c in ["created_at", "updated_at", "run_id"] if c in cols]
    order = " ORDER BY " + ", ".join(f"{c} DESC" for c in order_cols) if order_cols else ""
    sql = f"SELECT {', '.join('`'+c+'`' for c in select_cols)} FROM {table} WHERE {wh}{order} LIMIT 1"
    cur.execute(sql, tuple(ps))
    return cur.fetchone() or {}


def count_rows(cur, table: str, a: argparse.Namespace) -> int:
    if not table_exists(cur, table):
        return 0
    cols = colset(cur, table)
    wh, ps = scope_where(cols, a, include_source=table.startswith("canonical_"))
    cur.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE {wh}", tuple(ps))
    return int(cur.fetchone()["cnt"])


def numeric(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        return default


def text(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


def get_core(cur, a: argparse.Namespace) -> dict[str, Any]:
    core: dict[str, Any] = {}

    core.update(fetch_one(cur, "unified_reliability_score_day_v05", a, [
        "overall_risk_score", "final_risk_level", "dominant_semantic_risk",
        "source_gen_run_id", "scenario_name"
    ]))
    sem = fetch_one(cur, "semantic_interpretation_day_v05", a, [
        "dominant_semantic_risk", "semantic_confidence", "semantic_reason",
        "semantic_status", "risk_reason", "scenario_name"
    ])
    core.update({k: v for k, v in sem.items() if v is not None})
    act = fetch_one(cur, "action_recommendation_day_v05", a, [
        "recommended_action", "action_type", "priority", "action_rank", "action_reason", "scenario_name"
    ])
    core.update({k: v for k, v in act.items() if v is not None})
    recon = fetch_one(cur, "v05_reconciliation_measurement_day", a, [
        "behavior_transaction_match_rate", "transaction_state_match_rate",
        "behavior_only_count", "transaction_only_count", "orphan_state_count",
        "transaction_without_state_count", "duplicate_order_count",
        "payment_order_gap", "delivery_delay", "refund_delay", "scenario_name"
    ])
    core.update({k: v for k, v in recon.items() if v is not None})
    return core


def get_v04_evidence(cur, a: argparse.Namespace) -> dict[str, Any]:
    ev: dict[str, Any] = {}
    ev.update(fetch_one(cur, "measurement_batch_day", a, [
        "completeness_score", "timeliness_score", "availability_score", "integrity_score",
        "total_event_count", "event_count", "row_count", "scenario_name"
    ]))
    ev.update(fetch_one(cur, "measurement_stream_day", a, [
        "duplicate_rate", "ordering_violation_rate", "late_event_rate", "missing_event_rate",
        "stream_event_count", "scenario_name"
    ]))
    ev.update(fetch_one(cur, "measurement_operational_day", a, [
        "availability_score", "performance_score", "throughput_score", "error_rate",
        "scenario_name"
    ]))
    ev.update(fetch_one(cur, "measurement_realism_day", a, [
        "direct_completeness_delta", "direct_timeliness_delta", "direct_availability_delta",
        "direct_integrity_delta", "measurement_realism_status", "realism_reason", "scenario_name"
    ]))
    ev.update(fetch_one(cur, "r_reliability_analysis_result_day", a, [
        "drift_score", "propagation_score", "amplification_score", "distortion_score",
        "baseline_delta", "batch_delta", "selected_source_delta_metric",
        "actual_dominant_layer", "analysis_status", "analysis_reason", "scenario_name"
    ]))
    ev.update(fetch_one(cur, "r_batch_behavior_analysis_day", a, [
        "dominant_batch_signal", "batch_overall_analysis_score", "behavior_distortion_score",
        "session_fragmentation_score", "conversion_distortion_score", "identity_anomaly_score",
        "mapping_risk_score", "batch_quality_risk_score", "analysis_status", "scenario_name"
    ]))
    return ev


def get_batch_distribution(cur, a: argparse.Namespace) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out.update(fetch_one(cur, "v05_batch_behavior_distribution_day", a, [
        "batch_distribution_status", "baseline_event_count", "current_event_count",
        "event_count_delta_rate", "pv_delta_rate", "uv_delta_rate", "conversion_delta_rate",
        "scenario_name"
    ]))
    out.update(fetch_one(cur, "v05_batch_behavior_anomaly_day", a, [
        "anomaly_signal", "anomaly_score", "batch_distribution_risk_score",
        "scenario_name"
    ]))
    return out


def build_feature(cur, a: argparse.Namespace) -> dict[str, Any]:
    core = get_core(cur, a)
    v04 = get_v04_evidence(cur, a)
    batch = get_batch_distribution(cur, a)

    counts = {
        "canonical_behavior_count": count_rows(cur, "canonical_behavior_events", a),
        "canonical_transaction_count": count_rows(cur, "canonical_transaction_events", a),
        "canonical_state_count": count_rows(cur, "canonical_state_events", a),
        "stg_event_stream_count": count_rows(cur, "stg_event_stream", a),
        "stream_replay_event_count": count_rows(cur, "stream_replay_event", a),
        "measurement_batch_count": count_rows(cur, "measurement_batch_day", a),
        "measurement_stream_count": count_rows(cur, "measurement_stream_day", a),
        "measurement_operational_count": count_rows(cur, "measurement_operational_day", a),
    }

    payload = {
        "identity": {
            "profile_id": a.profile_id,
            "target_date": a.target_date,
            "run_id": a.run_id,
            "source_gen_run_id": a.source_gen_run_id,
            "scenario_name": a.scenario_name,
        },
        "counts": counts,
        "v05_authoritative": core,
        "v04_evidence_only": v04,
        "batch_distribution_evidence": batch,
        "notes": [
            "v05 commerce semantic/risk/action is authoritative",
            "v04 measurement/R analytics are evidence only",
            "v04 semantic/risk/action/ml are not authoritative by default",
        ],
    }

    feature = {
        "profile_id": a.profile_id,
        "target_date": a.target_date,
        "dt": a.target_date,
        "run_id": a.run_id,
        "source_gen_run_id": a.source_gen_run_id,
        "scenario_name": a.scenario_name,
        "feature_source": "build_v05_ml_feature_snapshot_schema_aware",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        **counts,
        "overall_risk_score": numeric(core.get("overall_risk_score")),
        "final_risk_level": text(core.get("final_risk_level"), "unknown"),
        "dominant_semantic_risk": text(core.get("dominant_semantic_risk"), "None"),
        "semantic_confidence": numeric(core.get("semantic_confidence"), 0.0),
        "recommended_action": text(core.get("recommended_action") or core.get("action_type"), "no action"),
        "behavior_transaction_match_rate": numeric(core.get("behavior_transaction_match_rate")),
        "transaction_state_match_rate": numeric(core.get("transaction_state_match_rate")),
        "behavior_only_count": int(numeric(core.get("behavior_only_count"))),
        "transaction_only_count": int(numeric(core.get("transaction_only_count"))),
        "orphan_state_count": int(numeric(core.get("orphan_state_count"))),
        "transaction_without_state_count": int(numeric(core.get("transaction_without_state_count"))),
        "direct_completeness_delta": numeric(v04.get("direct_completeness_delta")),
        "direct_timeliness_delta": numeric(v04.get("direct_timeliness_delta")),
        "direct_availability_delta": numeric(v04.get("direct_availability_delta")),
        "direct_integrity_delta": numeric(v04.get("direct_integrity_delta")),
        "drift_score": numeric(v04.get("drift_score")),
        "propagation_score": numeric(v04.get("propagation_score")),
        "amplification_score": numeric(v04.get("amplification_score")),
        "distortion_score": numeric(v04.get("distortion_score")),
        "baseline_delta": numeric(v04.get("baseline_delta")),
        "batch_delta": numeric(v04.get("batch_delta")),
        "dominant_batch_signal": text(v04.get("dominant_batch_signal") or batch.get("anomaly_signal"), "none"),
        "batch_overall_analysis_score": numeric(v04.get("batch_overall_analysis_score")),
        "behavior_distortion_score": numeric(v04.get("behavior_distortion_score")),
        "session_fragmentation_score": numeric(v04.get("session_fragmentation_score")),
        "conversion_distortion_score": numeric(v04.get("conversion_distortion_score")),
        "identity_anomaly_score": numeric(v04.get("identity_anomaly_score")),
        "mapping_risk_score": numeric(v04.get("mapping_risk_score")),
        "batch_quality_risk_score": numeric(v04.get("batch_quality_risk_score")),
        "batch_distribution_status": text(batch.get("batch_distribution_status"), "unknown"),
        "batch_anomaly_signal": text(batch.get("anomaly_signal"), "none"),
        "batch_anomaly_score": numeric(batch.get("anomaly_score")),
        "batch_distribution_risk_score": numeric(batch.get("batch_distribution_risk_score")),
        "feature_payload_json": json.dumps(payload, ensure_ascii=False, default=jdefault),
        "feature_json": json.dumps(payload, ensure_ascii=False, default=jdefault),
        "batch_feature_json": json.dumps({"v04": v04, "batch": batch}, ensure_ascii=False, default=jdefault),
    }
    return feature


def fallback_value(col: str, dtype: str, feature: dict[str, Any], a: argparse.Namespace) -> Any:
    if col in feature:
        return feature[col]
    if col == "profile_id":
        return a.profile_id
    if col in {"target_date", "dt"}:
        return a.target_date
    if col == "run_id":
        return a.run_id
    if col == "source_gen_run_id":
        return a.source_gen_run_id
    if col == "scenario_name":
        return a.scenario_name
    if col in {"created_at", "updated_at", "snapshot_at"}:
        return datetime.now()
    if col.endswith("_json"):
        return "{}"
    if col.endswith("_level"):
        return "unknown"
    if col.endswith("_risk") or col.endswith("_action") or col.endswith("_status") or col.endswith("_signal"):
        return ""
    if col.endswith("_count"):
        return 0
    if col.endswith(("_score", "_ratio", "_rate", "_delta")):
        return 0.0
    if dtype in {"int", "bigint", "smallint", "tinyint", "mediumint"}:
        return 0
    if dtype in {"decimal", "float", "double"}:
        return 0.0
    if dtype == "date":
        return a.target_date
    if dtype in {"datetime", "timestamp"}:
        return datetime.now()
    return ""


def delete_existing(cur, a: argparse.Namespace) -> None:
    table = "v05_ml_feature_snapshot_day"
    if not table_exists(cur, table):
        return
    cols = colset(cur, table)
    wh, ps = scope_where(cols, a, include_source=True)
    cur.execute(f"DELETE FROM {table} WHERE {wh}", tuple(ps))


def insert_snapshot(cur, a: argparse.Namespace, feature: dict[str, Any]) -> None:
    table = "v05_ml_feature_snapshot_day"
    if not table_exists(cur, table):
        print(f"[WARN] {table} missing; skip")
        return
    meta = table_meta(cur, table)
    cols = []
    dtypes = {}
    for r in meta:
        c = str(r["COLUMN_NAME"])
        dtypes[c] = str(r["DATA_TYPE"])
        extra = str(r.get("EXTRA") or "").lower()
        if "auto_increment" in extra:
            continue
        if c in feature or (r["IS_NULLABLE"] == "NO" and r["COLUMN_DEFAULT"] is None):
            cols.append(c)

    if not cols:
        raise RuntimeError("no compatible insert columns for v05_ml_feature_snapshot_day")

    vals = [fallback_value(c, dtypes.get(c, "varchar"), feature, a) for c in cols]
    sql = (
        f"INSERT INTO {table} ("
        + ",".join(f"`{c}`" for c in cols)
        + ") VALUES ("
        + ",".join(["%s"] * len(cols))
        + ")"
    )
    update_cols = [
        c for c in cols
        if c not in {"profile_id", "target_date", "dt", "run_id", "source_gen_run_id", "scenario_name", "created_at"}
    ]
    if update_cols:
        sql += " ON DUPLICATE KEY UPDATE " + ",".join(f"`{c}`=VALUES(`{c}`)" for c in update_cols)
    cur.execute(sql, tuple(vals))


def main() -> int:
    a = parse_args()
    con = connect(a)
    try:
        with con.cursor() as cur:
            if a.truncate_target:
                delete_existing(cur, a)
            feature = build_feature(cur, a)
            insert_snapshot(cur, a, feature)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    print(
        "[OK] build_v05_ml_feature_snapshot schema-aware "
        f"profile_id={a.profile_id} target_date={a.target_date} run_id={a.run_id} "
        f"source_gen_run_id={a.source_gen_run_id} scenario={a.scenario_name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
