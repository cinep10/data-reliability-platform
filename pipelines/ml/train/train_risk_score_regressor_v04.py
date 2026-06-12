#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
import urllib.parse
from pathlib import Path
import joblib
import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

try:
    from pipelines.ml.train.train_risk_multiclass_model_v04 import NUM_COLS, CAT_COLS
except Exception:
    from train_risk_multiclass_model_v04 import NUM_COLS, CAT_COLS

MODEL_VERSION = "risk_score_regressor_v04"
TARGET_COL = "overall_risk_score"


def engine(args):
    pw = urllib.parse.quote_plus(args.password)
    return create_engine(f"mysql+pymysql://{args.user}:{pw}@{args.host}:{args.port}/{args.db}?charset=utf8mb4")


def main():
    ap = argparse.ArgumentParser(description="Train v0.4 Phase4 risk score regressor against rule-based unified score.")
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

    df = pd.read_sql(
        text(f"SELECT * FROM {args.view_name} WHERE profile_id=:p AND dt BETWEEN :a AND :b ORDER BY dt, run_id"),
        engine(args),
        params={"p": args.profile_id, "a": args.dt_from, "b": args.dt_to},
    )
    if df.empty:
        raise SystemExit("training dataframe is empty")
    for c in NUM_COLS:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in CAT_COLS:
        if c not in df.columns:
            df[c] = "none"
        df[c] = df[c].fillna("none").astype(str)
    if TARGET_COL not in df.columns:
        raise SystemExit(f"missing target column: {TARGET_COL}")
    y = pd.to_numeric(df[TARGET_COL], errors="coerce").fillna(0.0)
    X = df[NUM_COLS + CAT_COLS].copy()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pre = ColumnTransformer([
        ("num", Pipeline([("imputer", SimpleImputer(strategy="constant", fill_value=0.0))]), NUM_COLS),
        ("cat", Pipeline([("imputer", SimpleImputer(strategy="constant", fill_value="none")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), CAT_COLS),
    ])
    model = Pipeline([
        ("pre", pre),
        ("reg", RandomForestRegressor(n_estimators=500, max_depth=8, min_samples_leaf=1, random_state=42)),
    ])
    if len(df) >= 10:
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.30, random_state=42)
    else:
        Xtr, Xte, ytr, yte = X, X, y, y
    model.fit(Xtr, ytr)
    pred = model.predict(Xte)
    metrics = {
        "rows": int(len(df)),
        "mae": float(mean_absolute_error(yte, pred)),
        "r2": float(r2_score(yte, pred)) if len(set(yte)) > 1 else None,
        "target_col": TARGET_COL,
    }
    pack = {
        "model": model,
        "model_name": "risk_score_regressor",
        "model_version": MODEL_VERSION,
        "num_cols": NUM_COLS,
        "cat_cols": CAT_COLS,
        "target_col": TARGET_COL,
    }
    joblib.dump(pack, out / "risk_score_regressor_v04.joblib")
    (out / "ml_regression_metrics_v04.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame({"actual_rule_score": yte.values, "predicted_ml_score": pred, "score_gap": pred - yte.values}).to_csv(out / "ml_regression_predictions_v04.csv", index=False)
    print(f"[OK] trained {MODEL_VERSION} rows={len(df)} mae={metrics['mae']:.4f} output_dir={out}")


if __name__ == "__main__":
    main()
