#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
import urllib.parse
from pathlib import Path
from typing import List
import joblib
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

MODEL_VERSION = "risk_multiclass_model_v04"
NUM_COLS: List[str] = [
    "direct_completeness_delta", "direct_timeliness_delta", "direct_availability_delta", "direct_integrity_delta",
    "drift_score", "propagation_score", "amplification_score", "distortion_score", "baseline_delta", "correlation_score",
    "integrity_score", "completeness_score", "timeliness_score", "consistency_score", "availability_score", "semantic_confidence",
    "overall_risk_score", "fallback_used",
]
CAT_COLS: List[str] = ["final_risk_level", "delta_source_type", "priority"]
LABEL_COL = "label_risk_family"


def engine(args):
    pw = urllib.parse.quote_plus(args.password)
    return create_engine(f"mysql+pymysql://{args.user}:{pw}@{args.host}:{args.port}/{args.db}?charset=utf8mb4")


def read_training_frame(args) -> pd.DataFrame:
    sql = text(
        f"""
        SELECT *
        FROM {args.view_name}
        WHERE profile_id=:profile_id AND dt BETWEEN :dt_from AND :dt_to
        ORDER BY dt, run_id
        """
    )
    return pd.read_sql(sql, engine(args), params={"profile_id": args.profile_id, "dt_from": args.dt_from, "dt_to": args.dt_to})


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    for c in NUM_COLS:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in CAT_COLS:
        if c not in df.columns:
            df[c] = "none"
        df[c] = df[c].fillna("none").astype(str)
    if LABEL_COL not in df.columns:
        raise SystemExit(f"missing label column: {LABEL_COL}")
    df[LABEL_COL] = df[LABEL_COL].fillna("unknown_risk").astype(str)
    return df


def main():
    ap = argparse.ArgumentParser(description="Train v0.4 Phase4 semantic risk multiclass classifier.")
    ap.add_argument("--host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    ap.add_argument("--user", default=os.getenv("DB_USER", "nethru"))
    ap.add_argument("--password", default=os.getenv("DB_PASSWORD", "nethru1234"))
    ap.add_argument("--db", default=os.getenv("DB_NAME", "weblog"))
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--view-name", default="vw_v04_phase4_ml_training_dataset_day")
    ap.add_argument("--output-dir", default="artifacts/ml_v04")
    args = ap.parse_args()

    df = normalize(read_training_frame(args))
    if df.empty:
        raise SystemExit("training dataframe is empty")
    y = df[LABEL_COL]
    X = df[NUM_COLS + CAT_COLS].copy()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pre = ColumnTransformer([
        ("num", Pipeline([("imputer", SimpleImputer(strategy="constant", fill_value=0.0))]), NUM_COLS),
        ("cat", Pipeline([("imputer", SimpleImputer(strategy="constant", fill_value="none")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), CAT_COLS),
    ])
    clf = RandomForestClassifier(
        n_estimators=500,
        max_depth=8,
        min_samples_leaf=1,
        random_state=42,
        class_weight="balanced_subsample",
    )
    model = Pipeline([("pre", pre), ("clf", clf)])
    stratify = y if y.nunique() > 1 and y.value_counts().min() >= 2 else None
    if len(df) >= 10 and y.nunique() > 1:
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.30, random_state=42, stratify=stratify)
    else:
        Xtr, Xte, ytr, yte = X, X, y, y
    model.fit(Xtr, ytr)
    pred = model.predict(Xte)
    labels = sorted(set(y.tolist()) | set(pred.tolist()))
    report = classification_report(yte, pred, labels=labels, output_dict=True, zero_division=0)
    cm = confusion_matrix(yte, pred, labels=labels)

    pack = {
        "model": model,
        "model_name": "semantic_risk_classifier",
        "model_version": MODEL_VERSION,
        "num_cols": NUM_COLS,
        "cat_cols": CAT_COLS,
        "label_col": LABEL_COL,
        "labels": labels,
    }
    joblib.dump(pack, out / "risk_multiclass_model_v04.joblib")
    (out / "ml_classification_report_v04.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(cm, index=labels, columns=labels).to_csv(out / "ml_confusion_matrix_v04.csv")
    df[["profile_id", "dt", "run_id", "scenario_name", LABEL_COL, "dominant_semantic_risk", "final_risk_level", "overall_risk_score"]].to_csv(out / "ml_training_rows_classifier_v04.csv", index=False)
    print(f"[OK] trained {MODEL_VERSION} rows={len(df)} labels={dict(y.value_counts())} output_dir={out}")


if __name__ == "__main__":
    main()
