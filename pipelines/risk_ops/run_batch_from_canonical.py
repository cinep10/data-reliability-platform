#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

import pymysql


def connect_mysql(args):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    ap.add_argument("--db-user", default=os.getenv("DB_USER"))
    ap.add_argument("--db-pass", default=os.getenv("DB_PASSWORD", ""))
    ap.add_argument("--db-name", default=os.getenv("DB_NAME"))
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--run-id", required=True, type=int)
    ap.add_argument("--truncate-target", action="store_true")
    ap.add_argument("--debug-preview", action="store_true")
    args = ap.parse_args()

    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            if args.truncate_target:
                cur.execute(
                    """
                    DELETE FROM batch_input_day
                    WHERE profile_id=%s
                      AND target_date BETWEEN %s AND %s
                    """,
                    (args.profile_id, args.dt_from, args.dt_to),
                )

            cur.execute(
                """
                SELECT
                    profile_id,
                    target_date,
                    service_domain,
                    COUNT(*) AS event_count,
                    COUNT(DISTINCT uid) AS unique_user_count,
                    COUNT(DISTINCT session_id) AS unique_session_count,
                    SUM(CASE WHEN is_conversion=1 THEN 1 ELSE 0 END) AS conversion_count,
                    SUM(CASE
                          WHEN CAST(status_code AS CHAR) IN ('500','502','503','504')
                          THEN 1 ELSE 0
                        END) AS error_count,
                    AVG(latency_ms) AS avg_latency_ms,
                    MIN(source_gen_run_id) AS source_gen_run_id,
                    MIN(exogenous_snapshot_id) AS exogenous_snapshot_id,
                    MIN(source_mode) AS source_mode,
                    MIN(exogenous_mode) AS exogenous_mode,
                    MIN(weather_type) AS weather_type,
                    MIN(campaign_flag) AS campaign_flag,
                    MIN(system_flag) AS system_flag
                FROM canonical_events
                WHERE profile_id=%s
                  AND target_date BETWEEN %s AND %s
                GROUP BY profile_id, target_date, service_domain
                ORDER BY target_date, service_domain
                """,
                (args.profile_id, args.dt_from, args.dt_to),
            )
            rows = cur.fetchall()

            inserts = []
            for r in rows:
                batch_payload = json.dumps(
                    {
                        "event_count": int(r.get("event_count") or 0),
                        "unique_user_count": int(r.get("unique_user_count") or 0),
                        "unique_session_count": int(r.get("unique_session_count") or 0),
                        "conversion_count": int(r.get("conversion_count") or 0),
                        "error_count": int(r.get("error_count") or 0),
                        "avg_latency_ms": float(r.get("avg_latency_ms")) if r.get("avg_latency_ms") is not None else None,
                        "lineage": {
                            "source_gen_run_id": r.get("source_gen_run_id"),
                            "exogenous_snapshot_id": r.get("exogenous_snapshot_id"),
                            "source_mode": r.get("source_mode"),
                            "exogenous_mode": r.get("exogenous_mode"),
                            "weather_type": r.get("weather_type"),
                            "campaign_flag": r.get("campaign_flag"),
                            "system_flag": r.get("system_flag"),
                        },
                    },
                    ensure_ascii=False,
                )

                inserts.append(
                    (
                        args.run_id,
                        r["profile_id"],
                        r["target_date"],
                        r["service_domain"],
                        int(r.get("event_count") or 0),
                        int(r.get("unique_user_count") or 0),
                        int(r.get("unique_session_count") or 0),
                        int(r.get("conversion_count") or 0),
                        int(r.get("error_count") or 0),
                        r.get("avg_latency_ms"),
                        r.get("source_gen_run_id"),
                        r.get("exogenous_snapshot_id"),
                        r.get("source_mode"),
                        r.get("exogenous_mode"),
                        r.get("weather_type"),
                        r.get("campaign_flag"),
                        r.get("system_flag"),
                        batch_payload,
                    )
                )

            if args.debug_preview and inserts:
                print("[batch_preview_first_row]")
                for i, v in enumerate(inserts[0], start=1):
                    print(i, repr(v))

            if inserts:
                cur.executemany(
                    """
                    INSERT INTO batch_input_day
                    (
                        run_id, profile_id, target_date, service_domain,
                        event_count, unique_user_count, unique_session_count, conversion_count,
                        error_count, avg_latency_ms,
                        source_gen_run_id, exogenous_snapshot_id, source_mode, exogenous_mode,
                        weather_type, campaign_flag, system_flag, batch_payload_json
                    )
                    VALUES
                    (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    inserts,
                )

        conn.commit()
        print(f"[run_batch_from_canonical] done rows={len(inserts)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
