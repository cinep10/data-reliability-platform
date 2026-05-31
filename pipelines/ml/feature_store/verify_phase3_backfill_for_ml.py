#!/usr/bin/env python3
import argparse
import pymysql

def connect(args):
    return pymysql.connect(
        host=args.db_host,
        port=int(args.db_port),
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )

def main():
    ap = argparse.ArgumentParser(description="Verify Phase3 backfill outputs for Phase4 ML/AI readiness.")
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-port", type=int, default=3306)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", required=True)
    ap.add_argument("--db-name", required=True)
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--min-rows", type=int, default=60)
    args = ap.parse_args()

    cn = connect(args)
    try:
        with cn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM ml_feature_snapshot_day
                WHERE profile_id=%s AND dt BETWEEN %s AND %s
            """, (args.profile_id, args.dt_from, args.dt_to))
            total = int(cur.fetchone()["cnt"] or 0)

            cur.execute("""
                SELECT dominant_semantic_risk, COUNT(*) AS cnt
                FROM ml_feature_snapshot_day
                WHERE profile_id=%s AND dt BETWEEN %s AND %s
                GROUP BY dominant_semantic_risk
                ORDER BY cnt DESC
            """, (args.profile_id, args.dt_from, args.dt_to))
            semantic = cur.fetchall()

            cur.execute("""
                SELECT scenario_name, COUNT(*) AS cnt
                FROM ml_feature_snapshot_day
                WHERE profile_id=%s AND dt BETWEEN %s AND %s
                GROUP BY scenario_name
                ORDER BY cnt DESC
            """, (args.profile_id, args.dt_from, args.dt_to))
            scenario = cur.fetchall()

            cur.execute("""
                SELECT COUNT(*) AS cnt
                FROM vw_v04_phase3_completion_status_day
                WHERE profile_id=%s AND dt BETWEEN %s AND %s
                  AND phase3_completion_status <> 'PASS'
            """, (args.profile_id, args.dt_from, args.dt_to))
            non_pass = int(cur.fetchone()["cnt"] or 0)

        print("[ML_BACKFILL_VERIFY]")
        print(f"profile_id={args.profile_id} dt={args.dt_from}..{args.dt_to}")
        print(f"ml_feature_snapshot_rows={total}")
        print(f"completion_non_pass_rows={non_pass}")
        print("\n[semantic_distribution]")
        for r in semantic:
            print(f"{r['dominant_semantic_risk']}\t{r['cnt']}")
        print("\n[scenario_distribution]")
        for r in scenario:
            print(f"{r['scenario_name']}\t{r['cnt']}")

        failures = 0
        if total < args.min_rows:
            print(f"[FAIL] rows below min_rows={args.min_rows}")
            failures += 1
        if non_pass > 0:
            print("[WARN] completion status has non-PASS rows. Review before training.")
        if len(semantic) < 4:
            print("[WARN] semantic class diversity is low. Consider more anomaly scenarios.")

        raise SystemExit(1 if failures else 0)
    finally:
        cn.close()

if __name__ == "__main__":
    main()
