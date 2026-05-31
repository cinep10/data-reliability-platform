#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
import pymysql


def connect(args):
    return pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user, password=args.db_pass, database=args.db_name, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)


def scalar(cur, sql, params):
    cur.execute(sql, params)
    row = cur.fetchone()
    return list(row.values())[0] if row else None


def main():
    ap = argparse.ArgumentParser(description="Verify v0.4 Phase4 ML output tables.")
    ap.add_argument("--db-host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    ap.add_argument("--db-user", default=os.getenv("DB_USER", "nethru"))
    ap.add_argument("--db-pass", default=os.getenv("DB_PASSWORD", "nethru1234"))
    ap.add_argument("--db-name", default=os.getenv("DB_NAME", "weblog"))
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--min-rows", type=int, default=30)
    ap.add_argument("--max-fallback-rows", type=int, default=0)
    args = ap.parse_args()

    conn = connect(args)
    failures = []
    try:
        with conn.cursor() as cur:
            snapshot_cnt = int(scalar(cur, "SELECT COUNT(*) FROM ml_feature_snapshot_day WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, args.dt_from, args.dt_to)) or 0)
            pred_cnt = int(scalar(cur, "SELECT COUNT(*) FROM ml_risk_score_day WHERE profile_id=%s AND dt BETWEEN %s AND %s AND model_name='phase4_ml_risk'", (args.profile_id, args.dt_from, args.dt_to)) or 0)
            label_cnt = int(scalar(cur, "SELECT COUNT(DISTINCT label_risk_family) FROM vw_v04_phase4_ml_training_dataset_day WHERE profile_id=%s AND dt BETWEEN %s AND %s", (args.profile_id, args.dt_from, args.dt_to)) or 0)
            direct_cnt = int(scalar(cur, "SELECT COUNT(*) FROM ml_feature_snapshot_day WHERE profile_id=%s AND dt BETWEEN %s AND %s AND delta_source_type='DIRECT_MEASUREMENT'", (args.profile_id, args.dt_from, args.dt_to)) or 0)
            fallback_cnt = int(scalar(cur, "SELECT COUNT(*) FROM ml_feature_snapshot_day WHERE profile_id=%s AND dt BETWEEN %s AND %s AND COALESCE(fallback_used,0)<>0", (args.profile_id, args.dt_from, args.dt_to)) or 0)
            gap_null_cnt = int(scalar(cur, "SELECT COUNT(*) FROM ml_risk_score_day WHERE profile_id=%s AND dt BETWEEN %s AND %s AND model_name='phase4_ml_risk' AND score_gap IS NULL", (args.profile_id, args.dt_from, args.dt_to)) or 0)

            print(f"[VERIFY] snapshot_rows={snapshot_cnt}")
            print(f"[VERIFY] prediction_rows={pred_cnt}")
            print(f"[VERIFY] distinct_labels={label_cnt}")
            print(f"[VERIFY] direct_measurement_rows={direct_cnt}")
            print(f"[VERIFY] fallback_rows={fallback_cnt}")
            print(f"[VERIFY] score_gap_null_rows={gap_null_cnt}")

            if snapshot_cnt < args.min_rows:
                failures.append(f"ml_feature_snapshot_day rows {snapshot_cnt} < min_rows {args.min_rows}")
            if pred_cnt < args.min_rows:
                failures.append(f"ml_risk_score_day rows {pred_cnt} < min_rows {args.min_rows}")
            if label_cnt < 2:
                failures.append("label diversity is too low; need at least stable + anomaly label")
            if direct_cnt == 0:
                failures.append("no DIRECT_MEASUREMENT rows found")
            if fallback_cnt > args.max_fallback_rows:
                failures.append(f"fallback rows {fallback_cnt} > allowed {args.max_fallback_rows}")
            if gap_null_cnt > 0:
                failures.append("score_gap has NULL rows")

            cur.execute(
                """
                SELECT label_risk_family, final_risk_level, dominant_semantic_risk, COUNT(*) AS cnt
                FROM vw_v04_phase4_ml_training_dataset_day
                WHERE profile_id=%s AND dt BETWEEN %s AND %s
                GROUP BY label_risk_family, final_risk_level, dominant_semantic_risk
                ORDER BY cnt DESC
                """,
                (args.profile_id, args.dt_from, args.dt_to),
            )
            print("[VERIFY] label distribution")
            for r in cur.fetchall():
                print(f"  {r['label_risk_family']} / {r['final_risk_level']} / {r['dominant_semantic_risk']} = {r['cnt']}")
    finally:
        conn.close()

    if failures:
        print("[FAIL]")
        for f in failures:
            print(f" - {f}")
        raise SystemExit(1)
    print("[OK] Phase4 ML verification passed")


if __name__ == "__main__":
    main()
