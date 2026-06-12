from __future__ import annotations

import argparse
import pymysql


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--dt-from", required=True)
    p.add_argument("--dt-to", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()


def ensure_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stg_event_batch (
          batch_ingest_id BIGINT NOT NULL AUTO_INCREMENT,
          raw_event_id BIGINT NULL,
          profile_id VARCHAR(100) NULL,
          dt DATE NULL,
          ts DATETIME NULL,
          event_name VARCHAR(100) NULL,
          service_domain VARCHAR(100) NULL,
          funnel_stage VARCHAR(100) NULL,
          is_conversion TINYINT(1) NULL,
          uid VARCHAR(128) NULL,
          pcid VARCHAR(128) NULL,
          sid VARCHAR(128) NULL,
          device_type VARCHAR(50) NULL,
          page_type VARCHAR(50) NULL,
          status INT NULL,
          latency_ms INT NULL,
          path TEXT NULL,
          query TEXT NULL,
          url_norm TEXT NULL,
          kv_raw LONGTEXT NULL,
          evt VARCHAR(100) NULL,
          load_status VARCHAR(20) NOT NULL DEFAULT 'success',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (batch_ingest_id),
          KEY idx_stg_event_batch_profile_dt (profile_id, dt),
          KEY idx_stg_event_batch_raw_event_id (raw_event_id),
          KEY idx_stg_event_batch_ts (ts)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def main():
    args = parse_args()

    conn = pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        autocommit=True,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
    )

    try:
        with conn.cursor() as cur:
            ensure_table(cur)

            if args.truncate_target:
                cur.execute(
                    """
                    DELETE FROM stg_event_batch
                    WHERE profile_id=%s
                      AND dt BETWEEN %s AND %s
                    """,
                    (args.profile_id, args.dt_from, args.dt_to),
                )

            inserted = cur.execute(
                """
                INSERT INTO stg_event_batch
                (
                  raw_event_id,
                  profile_id,
                  dt,
                  ts,
                  event_name,
                  service_domain,
                  funnel_stage,
                  is_conversion,
                  uid,
                  pcid,
                  sid,
                  device_type,
                  page_type,
                  status,
                  latency_ms,
                  path,
                  query,
                  url_norm,
                  kv_raw,
                  evt,
                  load_status
                )
                SELECT
                  ce.raw_event_id,
                  ce.profile_id,
                  ce.target_date AS dt,
                  ce.event_time AS ts,
                  COALESCE(NULLIF(ce.event_type, ''), 'browse') AS event_name,
                  ce.service_domain,
                  ce.funnel_stage,
                  COALESCE(ce.is_conversion, 0) AS is_conversion,
                  ce.uid AS uid,
                  ce.pcid AS pcid,
                  ce.session_id AS sid,
                  NULL AS device_type,
                  ce.page_type,
                  ce.status_code AS status,
                  ce.latency_ms,
                  NULL AS path,
                  NULL AS query,
                  NULL AS url_norm,
                  NULL AS kv_raw,
                  ce.event_type AS evt,
                  'success' AS load_status
                FROM canonical_events ce
                WHERE ce.profile_id=%s
                  AND ce.target_date BETWEEN %s AND %s
                  AND ce.run_id=%s
                """,
                (args.profile_id, args.dt_from, args.dt_to, args.run_id),
            )

            print(f"[DONE] stg_event_batch inserted={inserted}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
