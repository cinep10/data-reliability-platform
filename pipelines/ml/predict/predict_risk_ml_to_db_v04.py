#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

import joblib
import pandas as pd
import pymysql
from sqlalchemy import create_engine, text

MODEL_NAME = "phase4_ml_risk"


def engine(args):
    pw = urllib.parse.quote_plus(args.password)
    return create_engine(f"mysql+pymysql://{args.user}:{pw}@{args.host}:{args.port}/{args.db}?charset=utf8mb4")


def conn(args):
    return pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.db,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def safe_identifier(name: str) -> str:
    if not re.match(r"^[A-Za-z0-9_]+$", name or ""):
        raise SystemExit(f"unsafe SQL identifier: {name}")
    return name


def risk_grade(score: float) -> str:
    if score < 0.20:
        return "STABLE"
    if score < 0.45:
        return "WARN"
    if score < 0.75:
        return "HIGH"
    return "CRITICAL"


def resolve_model_path(path: str, output_dir: str, filename: str) -> str:
    candidates = [Path(path), Path(output_dir) / filename, Path("artifacts/ml_v04") / filename]
    for p in candidates:
        if p.exists():
            return str(p)
    raise SystemExit("model file not found. checked: " + ", ".join(str(p) for p in candidates))


def table_exists(cur, table: str) -> bool:
    cur.execute("SHOW TABLES LIKE %s", (table,))
    return cur.fetchone() is not None


def table_columns(cur, db: str, table: str) -> List[Dict[str, Any]]:
    cur.execute(
        """
        SELECT column_name, data_type, is_nullable, column_default, extra
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
        """,
        (db, table),
    )
    return list(cur.fetchall())


def default_for_column(col: Dict[str, Any]) -> Any:
    data_type = str(col.get("data_type") or "").lower()
    nullable = str(col.get("is_nullable") or "YES").upper() == "YES"
    if nullable:
        return None
    if any(t in data_type for t in ["int", "decimal", "double", "float", "real"]):
        return 0
    if data_type in {"date"}:
        return "1970-01-01"
    if "time" in data_type:
        return "1970-01-01 00:00:00"
    if data_type in {"json"}:
        return "{}"
    return ""


def top_features(row: pd.Series, num_cols: List[str], cat_cols: List[str]) -> str:
    vals = []
    for c in num_cols:
        try:
            v = float(row.get(c, 0) or 0)
        except Exception:
            v = 0.0
        vals.append((c, abs(v), v))
    vals.sort(key=lambda x: x[1], reverse=True)
    return json.dumps(
        {
            "source_view": "vw_v04_phase4_ml_training_dataset_day",
            "scenario_name": str(row.get("scenario_name", "")),
            "top_numeric_features": [
                {"name": n, "abs_value": av, "value": v} for n, av, v in vals[:10]
            ],
            "categorical_context": {c: str(row.get(c, "")) for c in cat_cols},
            "rule_score": float(row.get("overall_risk_score", 0) or 0),
            "rule_level": str(row.get("final_risk_level", "")),
            "dominant_semantic_risk": str(row.get("dominant_semantic_risk", "")),
        },
        ensure_ascii=False,
    )


def build_prediction_rows(df: pd.DataFrame, cls_pack: Dict[str, Any], reg_pack: Dict[str, Any]) -> List[Dict[str, Any]]:
    num_cols = cls_pack.get("num_cols") or reg_pack.get("num_cols") or []
    cat_cols = cls_pack.get("cat_cols") or reg_pack.get("cat_cols") or []
    for c in num_cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    for c in cat_cols:
        if c not in df.columns:
            df[c] = "none"
        df[c] = df[c].fillna("none").astype(str)
    X = df[num_cols + cat_cols].copy()

    cls = cls_pack["model"]
    reg = reg_pack["model"]
    labels = cls.predict(X)
    probs = cls.predict_proba(X).max(axis=1) if hasattr(cls, "predict_proba") else [None] * len(df)
    scores = reg.predict(X)
    model_version = f"{cls_pack.get('model_version','classifier')}+{reg_pack.get('model_version','regressor')}"

    rows = []
    for i, r in df.reset_index(drop=True).iterrows():
        ml_score = float(max(0.0, min(1.0, scores[i])))
        ml_grade = risk_grade(ml_score)
        rule_score = float(r.get("overall_risk_score", 0) or 0)
        pred_semantic = str(labels[i])
        confidence = None if probs[i] is None else float(probs[i])
        top_json = top_features(r, num_cols, cat_cols)
        rows.append(
            {
                # v04 canonical columns
                "profile_id": str(r["profile_id"]),
                "dt": str(pd.to_datetime(r["dt"]).date()),
                "run_id": str(r.get("run_id", "") or ""),
                "scenario_name": str(r.get("scenario_name", "") or ""),
                "model_name": MODEL_NAME,
                "model_version": model_version,
                "ml_risk_score": ml_score,
                "ml_risk_grade": ml_grade,
                "predicted_semantic_risk": pred_semantic,
                "prediction_confidence": confidence,
                "top_features_json": top_json,
                "rule_score": rule_score,
                "rule_risk_level": str(r.get("final_risk_level", "") or ""),
                "score_gap": ml_score - rule_score,
                # compatibility columns for older ml_prediction_result schemas
                "predicted_risk_score": ml_score,
                "predicted_risk_status": ml_grade,
                "predicted_risk_level": ml_grade,
                "predicted_risk_grade": ml_grade,
                "predicted_risk_type": pred_semantic,
                "predicted_label": pred_semantic,
                "predicted_class": pred_semantic,
                "confidence": confidence,
                "feature_json": top_json,
                "features_json": top_json,
                "source_rule_score": rule_score,
                "actual_risk_score": rule_score,
                "actual_risk_level": str(r.get("final_risk_level", "") or ""),
                "dominant_semantic_risk": str(r.get("dominant_semantic_risk", "") or ""),
                "recommended_action": str(r.get("recommended_action", "") or ""),
                "priority": str(r.get("priority", "") or ""),
            }
        )
    return rows


def insert_dynamic(cur, db: str, table: str, rows: List[Dict[str, Any]]) -> None:
    cols_meta = table_columns(cur, db, table)
    if not cols_meta:
        raise SystemExit(f"target table columns not found: {table}")

    insert_cols = []
    for col in cols_meta:
        name = col["column_name"]
        extra = str(col.get("extra") or "").lower()
        # Let DB manage auto/generated/update timestamps unless value is clearly needed.
        if "auto_increment" in extra or "generated" in extra:
            continue
        if name in {"created_at", "updated_at", "created_dt", "updated_dt"}:
            continue
        if name in rows[0]:
            insert_cols.append(name)
        elif str(col.get("is_nullable") or "YES").upper() == "NO" and col.get("column_default") is None:
            insert_cols.append(name)

    final_rows = []
    meta_by_name = {c["column_name"]: c for c in cols_meta}
    for r in rows:
        out = {}
        for c in insert_cols:
            out[c] = r[c] if c in r else default_for_column(meta_by_name[c])
        final_rows.append(out)

    placeholders = ",".join([f"%({c})s" for c in insert_cols])
    col_sql = ", ".join([f"`{c}`" for c in insert_cols])
    update_sql = ", ".join(
        [f"`{c}`=VALUES(`{c}`)" for c in insert_cols if c not in {"profile_id", "dt", "run_id", "model_name", "model_version"}]
    )
    sql = f"INSERT INTO `{table}` ({col_sql}) VALUES ({placeholders})"
    if update_sql:
        sql += f" ON DUPLICATE KEY UPDATE {update_sql}"
    cur.executemany(sql, final_rows)


def delete_existing(cur, table: str, profile_id: str, dt_from: str, dt_to: str) -> None:
    cols = {r["Field"] for r in _describe(cur, table)}
    conditions = ["profile_id=%s", "dt BETWEEN %s AND %s"]
    params: List[Any] = [profile_id, dt_from, dt_to]
    if "model_name" in cols:
        conditions.append("model_name=%s")
        params.append(MODEL_NAME)
    cur.execute(f"DELETE FROM `{table}` WHERE " + " AND ".join(conditions), params)


def _describe(cur, table: str):
    cur.execute(f"DESCRIBE `{table}`")
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser(description="Predict v0.4 Phase4 ML risk and persist to DB.")
    ap.add_argument("--host", "--db-host", dest="host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--port", "--db-port", dest="port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    ap.add_argument("--user", "--db-user", dest="user", default=os.getenv("DB_USER", "nethru"))
    ap.add_argument("--password", "--db-pass", dest="password", default=os.getenv("DB_PASSWORD", "nethru1234"))
    ap.add_argument("--db", "--db-name", dest="db", default=os.getenv("DB_NAME", "weblog"))
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--view-name", default="vw_v04_phase4_ml_training_dataset_day")
    ap.add_argument("--output-dir", default="artifacts/ml_v04")
    ap.add_argument("--classifier-path", default="artifacts/ml_v04/risk_multiclass_model_v04.joblib")
    ap.add_argument("--regressor-path", default="artifacts/ml_v04/risk_score_regressor_v04.joblib")
    ap.add_argument("--target-table", default="ml_prediction_result")
    ap.add_argument("--also-write-legacy-table", action="store_true", default=True)
    args = ap.parse_args()

    args.view_name = safe_identifier(args.view_name)
    args.target_table = safe_identifier(args.target_table)

    classifier_path = resolve_model_path(args.classifier_path, args.output_dir, "risk_multiclass_model_v04.joblib")
    regressor_path = resolve_model_path(args.regressor_path, args.output_dir, "risk_score_regressor_v04.joblib")

    df = pd.read_sql(
        text(
            f"""
            SELECT * FROM `{args.view_name}`
            WHERE profile_id=:p AND dt BETWEEN :a AND :b
            ORDER BY dt, run_id
            """
        ),
        engine(args),
        params={"p": args.profile_id, "a": args.dt_from, "b": args.dt_to},
    )
    if df.empty:
        raise SystemExit("prediction dataframe is empty")

    cls_pack = joblib.load(classifier_path)
    reg_pack = joblib.load(regressor_path)
    rows = build_prediction_rows(df, cls_pack, reg_pack)

    c = conn(args)
    try:
        with c.cursor() as cur:
            if not table_exists(cur, args.target_table):
                raise SystemExit(f"target table does not exist: {args.target_table}")
            delete_existing(cur, args.target_table, args.profile_id, args.dt_from, args.dt_to)
            insert_dynamic(cur, args.db, args.target_table, rows)

            if args.also_write_legacy_table and args.target_table != "ml_risk_score_day" and table_exists(cur, "ml_risk_score_day"):
                delete_existing(cur, "ml_risk_score_day", args.profile_id, args.dt_from, args.dt_to)
                insert_dynamic(cur, args.db, "ml_risk_score_day", rows)
        c.commit()
        print(f"[OK] persisted {args.target_table} rows={len(rows)} model={MODEL_NAME}")
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


if __name__ == "__main__":
    main()
