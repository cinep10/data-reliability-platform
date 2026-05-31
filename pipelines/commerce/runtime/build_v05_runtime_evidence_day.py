#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pymysql


def jdefault(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
    return str(v)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build v0.5 runtime evidence interface from v0.4 measurement/R evidence tables.")
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()


def connect(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name,
        charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor,
    )


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["cnt"]) == 1


def cols(cur, table: str) -> set[str]:
    if not table_exists(cur, table):
        return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {str(r["column_name"]) for r in cur.fetchall()}


def scoped_where(table_cols: set[str], a: argparse.Namespace) -> tuple[str, list[Any]]:
    where, params = [], []
    if "profile_id" in table_cols:
        where.append("profile_id=%s"); params.append(a.profile_id)
    if "target_date" in table_cols:
        where.append("target_date=%s"); params.append(a.target_date)
    elif "dt" in table_cols:
        where.append("dt=%s"); params.append(a.target_date)
    if "run_id" in table_cols:
        where.append("run_id=%s"); params.append(a.run_id)
    if "source_gen_run_id" in table_cols and a.source_gen_run_id is not None:
        where.append("source_gen_run_id=%s"); params.append(a.source_gen_run_id)
    if "scenario_name" in table_cols:
        where.append("scenario_name=%s"); params.append(a.scenario_name)
    return (" AND ".join(where) if where else "1=1", params)


def fetch_one(cur, table: str, a: argparse.Namespace) -> dict[str, Any]:
    if not table_exists(cur, table):
        return {}
    c = cols(cur, table)
    where, params = scoped_where(c, a)
    order_cols = [x for x in ["created_at", "updated_at", "run_id"] if x in c]
    sql = f"SELECT * FROM {table} WHERE {where}"
    if order_cols:
        sql += " ORDER BY " + ", ".join(f"{x} DESC" for x in order_cols)
    sql += " LIMIT 1"
    cur.execute(sql, tuple(params))
    return dict(cur.fetchone() or {})


def count_rows(cur, table: str, a: argparse.Namespace) -> int:
    if not table_exists(cur, table):
        return 0
    c = cols(cur, table)
    where, params = scoped_where(c, a)
    cur.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE {where}", tuple(params))
    return int(cur.fetchone()["cnt"])


def num(row: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for k in keys:
        if k in row and row[k] is not None:
            try:
                return float(row[k])
            except Exception:
                pass
    return default


def integer(row: dict[str, Any], *keys: str, default: int = 0) -> int:
    for k in keys:
        if k in row and row[k] is not None:
            try:
                return int(float(row[k]))
            except Exception:
                pass
    return default


def txt(row: dict[str, Any], *keys: str, default: str | None = None) -> str | None:
    for k in keys:
        if k in row and row[k] is not None:
            return str(row[k])
    return default


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def evidence_level(score: float) -> str:
    if score >= 0.75:
        return "critical"
    if score >= 0.50:
        return "high"
    if score >= 0.25:
        return "warning"
    return "low"


def dominant(scores: dict[str, float]) -> str:
    if not scores:
        return "none"
    k, v = max(scores.items(), key=lambda x: x[1])
    return k if v > 0 else "none"


def build(cur, a: argparse.Namespace) -> dict[str, Any]:
    mb = fetch_one(cur, "measurement_batch_day", a)
    ms = fetch_one(cur, "measurement_stream_day", a)
    mo = fetch_one(cur, "measurement_operational_day", a)
    mr = fetch_one(cur, "measurement_realism_day", a)
    rb = fetch_one(cur, "r_batch_behavior_analysis_day", a)
    bd = fetch_one(cur, "v05_batch_behavior_distribution_day", a)
    bda = fetch_one(cur, "r_v05_batch_distribution_analysis_day", a)
    ba = fetch_one(cur, "v05_batch_behavior_anomaly_day", a)
    sday = fetch_one(cur, "stream_reliability_summary_day", a)

    canonical_event_count = count_rows(cur, "canonical_events", a)
    canonical_behavior_count = count_rows(cur, "canonical_behavior_events", a)
    canonical_transaction_count = count_rows(cur, "canonical_transaction_events", a)
    canonical_state_count = count_rows(cur, "canonical_state_events", a)
    stg_event_stream_count = count_rows(cur, "stg_event_stream", a)

    direct_completeness_delta = clamp01(abs(num(mr, "direct_completeness_delta")))
    direct_timeliness_delta = clamp01(abs(num(mr, "direct_timeliness_delta")))
    direct_availability_delta = clamp01(abs(num(mr, "direct_availability_delta")))
    direct_integrity_delta = clamp01(abs(num(mr, "direct_integrity_delta")))

    behavior_distortion_score = clamp01(num(rb, "behavior_distortion_score"))
    conversion_distortion_score = clamp01(num(rb, "conversion_distortion_score"))
    session_fragmentation_score = clamp01(num(rb, "session_fragmentation_score"))
    identity_anomaly_score = clamp01(num(rb, "identity_anomaly_score"))
    mapping_risk_score = clamp01(num(rb, "mapping_risk_score"))
    batch_quality_risk_score = clamp01(num(rb, "batch_quality_risk_score"))

    batch_distribution_score = clamp01(
        num(ba, "batch_distribution_risk_score", "anomaly_score", default=0.0)
        or num(bda, "batch_distribution_risk_score", "batch_distribution_score", default=0.0)
        or abs(num(bd, "event_count_delta_rate", default=0.0))
    )
    batch_evidence_score = clamp01(max(
        behavior_distortion_score, conversion_distortion_score, session_fragmentation_score,
        identity_anomaly_score, mapping_risk_score, batch_quality_risk_score, batch_distribution_score
    ))

    stream_duplicate_rate = clamp01(num(ms, "duplicate_rate", "stream_duplicate_rate", default=0.0) or num(sday, "duplicate_rate", default=0.0))
    stream_late_event_rate = clamp01(num(ms, "late_event_rate", "stream_late_event_rate", default=0.0) or num(sday, "late_event_rate", default=0.0))
    stream_missing_event_rate = clamp01(num(ms, "missing_event_rate", "stream_missing_event_rate", default=0.0) or num(sday, "missing_event_rate", default=0.0))
    stream_ordering_violation_rate = clamp01(num(ms, "ordering_violation_rate", "stream_ordering_violation_rate", default=0.0) or num(sday, "ordering_violation_rate", default=0.0))
    stream_event_count = integer(ms, "stream_event_count", "event_count", default=stg_event_stream_count)
    stream_evidence_score = clamp01(max(stream_duplicate_rate, stream_late_event_rate, stream_missing_event_rate, stream_ordering_violation_rate))

    operational_availability_score = clamp01(num(mo, "availability_score", "operational_availability_score", default=1.0))
    operational_performance_score = clamp01(num(mo, "performance_score", "operational_performance_score", default=1.0))
    operational_error_rate = clamp01(num(mo, "error_rate", "operational_error_rate", default=0.0))
    operational_evidence_score = clamp01(max(1.0 - operational_availability_score, 1.0 - operational_performance_score, operational_error_rate))

    realism_evidence_score = clamp01(max(direct_completeness_delta, direct_timeliness_delta, direct_availability_delta, direct_integrity_delta))
    scores = {
        "batch": batch_evidence_score,
        "stream": stream_evidence_score,
        "operational": operational_evidence_score,
        "realism": realism_evidence_score,
    }
    runtime_evidence_score = clamp01(max(scores.values()))
    dom = dominant(scores)

    is_baseline_like = (a.scenario_name or "").lower() in {"baseline", "normal", "stable"}
    if is_baseline_like:
        # Baseline runs are calibration references. If direct measurement deltas are zero,
        # runtime evidence must not be converted into warning/critical just because count-like
        # runtime rows exist.
        if max(direct_completeness_delta, direct_timeliness_delta, direct_availability_delta, direct_integrity_delta) <= 0.0001:
            batch_evidence_score = 0.0
            stream_evidence_score = 0.0
            operational_evidence_score = 0.0
            realism_evidence_score = 0.0
            scores = {"batch": 0.0, "stream": 0.0, "operational": 0.0, "realism": 0.0}
            runtime_evidence_score = 0.0
            dom = "none"

    payload = {
        "principle": "runtime evidence only; not authoritative risk/action",
        "source_tables": {
            "measurement_batch_day": mb,
            "measurement_stream_day": ms,
            "measurement_operational_day": mo,
            "measurement_realism_day": mr,
            "r_batch_behavior_analysis_day": rb,
            "v05_batch_behavior_distribution_day": bd,
            "r_v05_batch_distribution_analysis_day": bda,
            "v05_batch_behavior_anomaly_day": ba,
            "stream_reliability_summary_day": sday,
        },
        "scores": scores,
        "dominant_runtime_signal": dom,
        "notes": [
            "r_reliability_analysis.R is intentionally not used by default.",
            "Commerce reconciliation remains authoritative.",
            "Runtime evidence may be used as supplementary context by ML/AI or future commerce analytics enrichment.",
        ],
    }

    return {
        "profile_id": a.profile_id,
        "target_date": a.target_date,
        "dt": a.target_date,
        "run_id": a.run_id,
        "source_gen_run_id": a.source_gen_run_id,
        "scenario_name": a.scenario_name,
        "batch_evidence_score": batch_evidence_score,
        "stream_evidence_score": stream_evidence_score,
        "operational_evidence_score": operational_evidence_score,
        "realism_evidence_score": realism_evidence_score,
        "runtime_evidence_score": runtime_evidence_score,
        "batch_signal": txt(rb, "dominant_batch_signal", default=None) or txt(ba, "anomaly_signal", default=None) or ("batch" if batch_evidence_score > 0 else "none"),
        "stream_signal": txt(sday, "dominant_stream_signal", "stream_signal", default=None) or ("stream" if stream_evidence_score > 0 else "none"),
        "operational_signal": txt(mo, "dominant_operational_signal", "operational_signal", default=None) or ("operational" if operational_evidence_score > 0 else "none"),
        "realism_signal": txt(mr, "measurement_realism_status", "realism_status", default=None) or ("realism" if realism_evidence_score > 0 else "none"),
        "dominant_runtime_signal": dom,
        "direct_completeness_delta": direct_completeness_delta,
        "direct_timeliness_delta": direct_timeliness_delta,
        "direct_availability_delta": direct_availability_delta,
        "direct_integrity_delta": direct_integrity_delta,
        "behavior_distortion_score": behavior_distortion_score,
        "conversion_distortion_score": conversion_distortion_score,
        "session_fragmentation_score": session_fragmentation_score,
        "identity_anomaly_score": identity_anomaly_score,
        "mapping_risk_score": mapping_risk_score,
        "batch_quality_risk_score": batch_quality_risk_score,
        "stream_duplicate_rate": stream_duplicate_rate,
        "stream_late_event_rate": stream_late_event_rate,
        "stream_missing_event_rate": stream_missing_event_rate,
        "stream_ordering_violation_rate": stream_ordering_violation_rate,
        "stream_event_count": stream_event_count,
        "operational_availability_score": operational_availability_score,
        "operational_performance_score": operational_performance_score,
        "operational_error_rate": operational_error_rate,
        "batch_event_count": integer(mb, "batch_event_count", "event_count", "total_event_count", default=0),
        "canonical_event_count": canonical_event_count,
        "canonical_behavior_count": canonical_behavior_count,
        "canonical_transaction_count": canonical_transaction_count,
        "canonical_state_count": canonical_state_count,
        "evidence_level": evidence_level(runtime_evidence_score),
        "evidence_status": "completed",
        "evidence_policy": "v05_runtime_evidence_only",
        "evidence_payload_json": json.dumps(payload, ensure_ascii=False, default=jdefault),
    }


def insert_row(cur, row: dict[str, Any]) -> None:
    c = cols(cur, "v05_runtime_evidence_day")
    insert_cols = [k for k in row if k in c]
    if not insert_cols:
        raise RuntimeError("v05_runtime_evidence_day has no compatible columns")
    sql = "INSERT INTO v05_runtime_evidence_day (" + ",".join(f"`{x}`" for x in insert_cols) + ") VALUES (" + ",".join(["%s"] * len(insert_cols)) + ")"
    update_cols = [x for x in insert_cols if x not in {"profile_id", "target_date", "dt", "run_id", "scenario_name", "created_at"}]
    if update_cols:
        sql += " ON DUPLICATE KEY UPDATE " + ",".join(f"`{x}`=VALUES(`{x}`)" for x in update_cols)
    cur.execute(sql, tuple(row[x] for x in insert_cols))


def main() -> int:
    a = parse_args()
    con = connect(a)
    try:
        with con.cursor() as cur:
            if not table_exists(cur, "v05_runtime_evidence_day"):
                raise RuntimeError("missing table v05_runtime_evidence_day. Apply sql/035_v05_runtime_evidence_interface_mariadb.sql first.")
            if a.truncate_target:
                c = cols(cur, "v05_runtime_evidence_day")
                where, params = scoped_where(c, a)
                cur.execute(f"DELETE FROM v05_runtime_evidence_day WHERE {where}", tuple(params))
            row = build(cur, a)
            insert_row(cur, row)
        con.commit()
        print(f"[OK] build_v05_runtime_evidence_day profile_id={a.profile_id} target_date={a.target_date} run_id={a.run_id} scenario={a.scenario_name} score={row['runtime_evidence_score']:.6f} level={row['evidence_level']} dominant={row['dominant_runtime_signal']}")
        return 0
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
