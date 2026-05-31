#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from typing import Optional

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


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


def should_apply_lag(event_time: datetime, lag_from: Optional[datetime], lag_to: Optional[datetime]) -> bool:
    if lag_from is None or lag_to is None:
        return False
    return lag_from <= event_time <= lag_to


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
    ap.add_argument("--lag-spike-from")
    ap.add_argument("--lag-spike-to")
    ap.add_argument("--lag-spike-sleep-ms", type=int, default=0)
    ap.add_argument("--lag-spike-every-n", type=int, default=0)
    ap.add_argument("--commit-every", type=int, default=1000)
    ap.add_argument("--batch-size", type=int, default=1000)
    args = ap.parse_args()

    lag_from = parse_dt(args.lag_spike_from)
    lag_to = parse_dt(args.lag_spike_to)

    conn = connect_mysql(args)
    lag_spike_matches = 0
    lag_spike_sleeps = 0
    try:
        with conn.cursor() as cur:
            if args.truncate_target:
                cur.execute(
                    """
                    DELETE FROM stream_replay_event
                    WHERE profile_id=%s
                      AND target_date BETWEEN %s AND %s
                    """,
                    (args.profile_id, args.dt_from, args.dt_to),
                )
                conn.commit()

            cur.execute(
                """
                SELECT
                    canonical_event_id, profile_id, target_date, event_time, event_date,
                    service_domain, event_type, uid, session_id, page_type, funnel_stage,
                    channel, status_code, bytes, latency_ms, is_conversion,
                    source_gen_run_id, exogenous_snapshot_id, source_file_id, raw_snapshot_id,
                    source_mode, exogenous_mode, weather_type, campaign_flag, system_flag,
                    canonical_payload_json
                FROM canonical_events
                WHERE profile_id=%s
                  AND target_date BETWEEN %s AND %s
                  AND run_id=%s
                ORDER BY event_time, canonical_event_id
                """,
                (args.profile_id, args.dt_from, args.dt_to, args.run_id),
            )
            rows = cur.fetchall()

            sql = """
                INSERT INTO stream_replay_event
                (
                    run_id, profile_id, target_date, canonical_event_id, event_time, event_date,
                    service_domain, event_type, uid, session_id, page_type, funnel_stage,
                    channel, status_code, bytes, latency_ms, is_conversion,
                    source_gen_run_id, exogenous_snapshot_id, source_file_id, raw_snapshot_id,
                    source_mode, exogenous_mode, weather_type, campaign_flag, system_flag,
                    replay_sequence, replay_payload_json
                )
                VALUES
                (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """

            inserts = []
            for idx, r in enumerate(rows, start=1):
                event_time = r["event_time"]
                if should_apply_lag(event_time, lag_from, lag_to):
                    lag_spike_matches += 1
                    if args.lag_spike_every_n > 0 and args.lag_spike_sleep_ms > 0 and (lag_spike_matches % args.lag_spike_every_n == 0):
                        time.sleep(args.lag_spike_sleep_ms / 1000.0)
                        lag_spike_sleeps += 1

                replay_payload = json.dumps(
                    {
                        "replay_sequence": idx,
                        "canonical_event_id": r["canonical_event_id"],
                        "canonical_payload_json": r.get("canonical_payload_json"),
                        "lineage": {
                            "source_gen_run_id": r.get("source_gen_run_id"),
                            "exogenous_snapshot_id": r.get("exogenous_snapshot_id"),
                            "source_file_id": r.get("source_file_id"),
                            "raw_snapshot_id": r.get("raw_snapshot_id"),
                            "source_mode": r.get("source_mode"),
                            "exogenous_mode": r.get("exogenous_mode"),
                        },
                        "op_scenario": {
                            "lag_spike_from": args.lag_spike_from,
                            "lag_spike_to": args.lag_spike_to,
                            "lag_spike_sleep_ms": args.lag_spike_sleep_ms,
                            "lag_spike_every_n": args.lag_spike_every_n,
                        },
                    },
                    ensure_ascii=False,
                )

                inserts.append(
                    (
                        args.run_id,
                        r["profile_id"],
                        r["target_date"],
                        r["canonical_event_id"],
                        r["event_time"],
                        r["event_date"],
                        r["service_domain"],
                        r["event_type"],
                        r.get("uid"),
                        r.get("session_id"),
                        r.get("page_type"),
                        r.get("funnel_stage"),
                        r.get("channel"),
                        r.get("status_code"),
                        r.get("bytes"),
                        r.get("latency_ms"),
                        int(r.get("is_conversion") or 0),
                        r.get("source_gen_run_id"),
                        r.get("exogenous_snapshot_id"),
                        r.get("source_file_id"),
                        r.get("raw_snapshot_id"),
                        r.get("source_mode"),
                        r.get("exogenous_mode"),
                        r.get("weather_type"),
                        r.get("campaign_flag"),
                        r.get("system_flag"),
                        idx,
                        replay_payload,
                    )
                )

                if len(inserts) >= args.batch_size:
                    if args.debug_preview and idx == len(inserts):
                        print("[replay_preview_first_batch_row]", repr(inserts[0]))
                    cur.executemany(sql, inserts)
                    if args.commit_every > 0 and idx % args.commit_every == 0:
                        conn.commit()
                    inserts = []

            if inserts:
                if args.debug_preview:
                    print("[replay_preview_final_batch_row]", repr(inserts[0]))
                cur.executemany(sql, inserts)

        conn.commit()
        print(
            f"[run_stream_replay_from_canonical] done rows={len(rows)} "
            f"lag_spike_matches={lag_spike_matches} lag_spike_sleeps={lag_spike_sleeps}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
