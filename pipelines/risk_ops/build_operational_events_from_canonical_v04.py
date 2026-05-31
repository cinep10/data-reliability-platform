#!/usr/bin/env python3
from __future__ import annotations

"""
v0.4 operational materializer from canonical_events.

Why this exists:
- The old name "stream replay" came from the earlier stream-injection/Kafka replay design.
- In v0.4 Phase2 source-only propagation, operational risk still needs an operational event table
  to measure delay, throughput, availability, and run-level performance.
- Therefore this script keeps writing stream_replay_event for compatibility with existing
  risk_ops scripts, but the operation is now named "operational event materialization",
  not stream injection/replay.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from pipelines.common.v04_integrated_risk_common import json_default
except Exception:
    def json_default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat(sep=" ")
        return str(obj)

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
    return datetime.fromisoformat(value.replace("T", " "))

def should_apply_lag(event_time: datetime, lag_from: Optional[datetime], lag_to: Optional[datetime]) -> bool:
    if lag_from is None or lag_to is None:
        return False
    return lag_from <= event_time <= lag_to

def table_columns(cur, table_name: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table_name,),
    )
    return {r["column_name"] for r in cur.fetchall()}

def ensure_columns(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stream_replay_event (
          replay_event_id BIGINT NOT NULL AUTO_INCREMENT,
          run_id BIGINT NOT NULL,
          profile_id VARCHAR(64) NOT NULL,
          target_date DATE NOT NULL,
          canonical_event_id BIGINT NULL,
          event_time DATETIME NULL,
          event_date DATE NULL,
          service_domain VARCHAR(128) NULL,
          event_type VARCHAR(64) NULL,
          uid VARCHAR(128) NULL,
          session_id VARCHAR(128) NULL,
          page_type VARCHAR(128) NULL,
          funnel_stage VARCHAR(128) NULL,
          channel VARCHAR(128) NULL,
          status_code INT NULL,
          bytes BIGINT NULL,
          latency_ms INT NULL,
          is_conversion TINYINT(1) NULL,
          source_gen_run_id BIGINT NULL,
          exogenous_snapshot_id BIGINT NULL,
          source_file_id BIGINT NULL,
          raw_snapshot_id BIGINT NULL,
          source_mode VARCHAR(128) NULL,
          exogenous_mode VARCHAR(128) NULL,
          weather_type VARCHAR(128) NULL,
          campaign_flag VARCHAR(128) NULL,
          system_flag VARCHAR(128) NULL,
          replay_sequence_no BIGINT NULL,
          replay_started_at DATETIME NULL,
          replay_emitted_at DATETIME NULL,
          replay_lag_ms BIGINT NULL,
          replay_payload_json JSON NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (replay_event_id),
          KEY idx_sre_profile_target_run (profile_id, target_date, run_id),
          KEY idx_sre_canonical_event_id (canonical_event_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute("ALTER TABLE stream_replay_event ADD COLUMN IF NOT EXISTS replay_sequence BIGINT NULL")
    cur.execute("ALTER TABLE stream_replay_event ADD COLUMN IF NOT EXISTS replay_sequence_no BIGINT NULL")
    cur.execute("ALTER TABLE stream_replay_event ADD COLUMN IF NOT EXISTS operation_mode VARCHAR(64) NULL")
    cur.execute("ALTER TABLE stream_replay_event ADD COLUMN IF NOT EXISTS op_materialized_at DATETIME NULL")
    cur.execute("ALTER TABLE stream_replay_event ADD INDEX IF NOT EXISTS idx_sre_profile_target_run_canonical (profile_id, target_date, run_id, canonical_event_id)")

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
    inserted = 0
    try:
        with conn.cursor() as cur:
            ensure_columns(cur)
            if args.truncate_target:
                cur.execute(
                    """
                    DELETE FROM stream_replay_event
                    WHERE profile_id=%s
                      AND target_date BETWEEN %s AND %s
                      AND run_id=%s
                    """,
                    (args.profile_id, args.dt_from, args.dt_to, args.run_id),
                )
                conn.commit()

            ce_cols = table_columns(cur, "canonical_events")
            select_cols = [
                "canonical_event_id", "profile_id", "target_date", "event_time", "event_date",
                "service_domain", "event_type", "uid", "session_id", "page_type", "funnel_stage",
                "channel", "status_code", "bytes", "latency_ms", "is_conversion",
                "source_gen_run_id", "exogenous_snapshot_id", "source_file_id", "raw_snapshot_id",
                "source_mode", "exogenous_mode", "weather_type", "campaign_flag", "system_flag",
                "canonical_payload_json",
            ]
            select_cols = [c for c in select_cols if c in ce_cols]
            cur.execute(
                f"""
                SELECT {', '.join(select_cols)}
                FROM canonical_events
                WHERE profile_id=%s
                  AND target_date BETWEEN %s AND %s
                  AND run_id=%s
                ORDER BY event_time, canonical_event_id
                """,
                (args.profile_id, args.dt_from, args.dt_to, args.run_id),
            )
            rows = cur.fetchall()

            target_cols = [
                "run_id", "profile_id", "target_date", "canonical_event_id", "event_time", "event_date",
                "service_domain", "event_type", "uid", "session_id", "page_type", "funnel_stage",
                "channel", "status_code", "bytes", "latency_ms", "is_conversion",
                "source_gen_run_id", "exogenous_snapshot_id", "source_file_id", "raw_snapshot_id",
                "source_mode", "exogenous_mode", "weather_type", "campaign_flag", "system_flag",
                "replay_sequence", "replay_sequence_no", "replay_started_at", "replay_emitted_at", "replay_lag_ms",
                "replay_payload_json", "operation_mode", "op_materialized_at",
            ]
            existing = table_columns(cur, "stream_replay_event")
            target_cols = [c for c in target_cols if c in existing]
            sql = f"INSERT INTO stream_replay_event ({','.join(target_cols)}) VALUES ({','.join(['%s']*len(target_cols))})"

            started_at = datetime.now()
            batch = []
            seq = 0
            for r in rows:
                seq += 1
                event_time = r.get("event_time")
                if should_apply_lag(event_time, lag_from, lag_to):
                    lag_spike_matches += 1
                    if args.lag_spike_sleep_ms > 0 and args.lag_spike_every_n > 0 and lag_spike_matches % args.lag_spike_every_n == 0:
                        time.sleep(args.lag_spike_sleep_ms / 1000.0)
                        lag_spike_sleeps += 1

                emitted_at = datetime.now()
                lag_ms = int((emitted_at - event_time).total_seconds() * 1000) if event_time else 0
                payload = json.dumps(
                    {
                        "operation_mode": "canonical_operational_materialization",
                        "canonical_event_id": r.get("canonical_event_id"),
                        "lineage": {
                            "run_id": args.run_id,
                            "source_gen_run_id": r.get("source_gen_run_id"),
                            "raw_snapshot_id": r.get("raw_snapshot_id"),
                        },
                        "canonical_payload": r.get("canonical_payload_json"),
                    },
                    default=json_default,
                    ensure_ascii=False,
                )
                rowmap = {
                    **r,
                    "run_id": args.run_id,
                    "replay_sequence": seq,
                    "replay_sequence_no": seq,
                    "replay_started_at": started_at,
                    "replay_emitted_at": emitted_at,
                    "replay_lag_ms": lag_ms,
                    "replay_payload_json": payload,
                    "operation_mode": "canonical_operational_materialization",
                    "op_materialized_at": emitted_at,
                }
                batch.append([rowmap.get(c) for c in target_cols])
                if len(batch) >= args.batch_size:
                    cur.executemany(sql, batch)
                    inserted += len(batch)
                    conn.commit()
                    batch = []
            if batch:
                cur.executemany(sql, batch)
                inserted += len(batch)
                conn.commit()

            if args.debug_preview:
                print(json.dumps(rows[:3], default=json_default, ensure_ascii=False, indent=2))
    finally:
        conn.close()

    print(
        "[build_operational_events_from_canonical_v04] "
        f"profile_id={args.profile_id} dt_from={args.dt_from} dt_to={args.dt_to} run_id={args.run_id} "
        f"canonical_rows={len(rows)} inserted={inserted} lag_matches={lag_spike_matches} lag_sleeps={lag_spike_sleeps}"
    )

if __name__ == "__main__":
    main()
