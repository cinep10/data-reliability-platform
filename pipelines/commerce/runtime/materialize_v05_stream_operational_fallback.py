#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any

import pymysql


def connect(args: argparse.Namespace):
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


def table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table,),
    )
    return int(cur.fetchone()["cnt"] or 0) == 1


def columns(cur, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def q(identifier: str) -> str:
    return "`" + identifier.replace("`", "``") + "`"


def first_col(cset: set[str], *names: str, default: str = "NULL") -> str:
    for name in names:
        if name in cset:
            return q(name)
    return default


def ensure_required_tables(cur) -> None:
    # These CREATE statements are only for missing local/dev tables. They do not
    # override existing v0.4/v0.5 schemas. Existing tables are handled by
    # schema-aware insert/delete below.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stg_event_stream (
          stream_ingest_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
          raw_event_id BIGINT UNSIGNED NOT NULL,
          dt DATE NOT NULL,
          ts DATETIME NOT NULL,
          event_name VARCHAR(100) NOT NULL,
          service_domain VARCHAR(50) NULL,
          funnel_stage VARCHAR(50) NULL,
          is_conversion TINYINT(1) NOT NULL DEFAULT 0,
          uid VARCHAR(128) NULL,
          pcid VARCHAR(128) NULL,
          sid VARCHAR(128) NULL,
          ingest_ts DATETIME NOT NULL,
          event_delay_ms BIGINT NULL,
          status INT NULL,
          latency_ms INT NULL,
          source_type VARCHAR(50) NULL,
          path VARCHAR(255) NULL,
          load_status VARCHAR(20) NULL DEFAULT 'loaded',
          profile_id VARCHAR(64) NULL,
          run_id BIGINT NULL,
          canonical_event_id BIGINT NULL,
          source_gen_run_id BIGINT NULL,
          event_type VARCHAR(64) NULL,
          semantic_event_name VARCHAR(128) NULL,
          product_type VARCHAR(128) NULL,
          device_type VARCHAR(64) NULL,
          page_type VARCHAR(128) NULL,
          status_code INT NULL,
          bytes BIGINT NULL,
          schema_version VARCHAR(64) NULL,
          scenario_name VARCHAR(128) NULL,
          anomaly_type VARCHAR(128) NULL,
          stream_payload_json LONGTEXT NULL,
          created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          KEY idx_stg_stream_v05_lookup (profile_id, dt, run_id),
          KEY idx_stg_stream_v05_canonical (canonical_event_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stream_replay_event (
          replay_event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
          run_id BIGINT NULL,
          profile_id VARCHAR(100) NOT NULL,
          target_date DATE NOT NULL,
          canonical_event_id BIGINT NOT NULL,
          event_time DATETIME NOT NULL,
          event_date DATE NOT NULL,
          service_domain VARCHAR(50) NOT NULL,
          event_type VARCHAR(100) NOT NULL,
          uid VARCHAR(128) NULL,
          session_id VARCHAR(128) NULL,
          page_type VARCHAR(32) NULL,
          funnel_stage VARCHAR(50) NULL,
          channel VARCHAR(50) NULL,
          status_code VARCHAR(30) NULL,
          bytes BIGINT NULL,
          latency_ms INT NULL,
          is_conversion TINYINT(1) NOT NULL DEFAULT 0,
          source_gen_run_id BIGINT NULL,
          replay_sequence BIGINT NOT NULL,
          replay_payload_json LONGTEXT NULL,
          replayed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          operation_mode VARCHAR(64) NULL,
          op_materialized_at DATETIME NULL,
          replay_sequence_no BIGINT NULL,
          KEY idx_replay_v05_lookup (profile_id, target_date, run_id),
          KEY idx_replay_v05_canonical (canonical_event_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_performance_summary_day (
          dt DATE NOT NULL,
          pipeline_name VARCHAR(100) NOT NULL,
          entity_scope VARCHAR(100) NOT NULL,
          processing_mode VARCHAR(20) NOT NULL,
          runtime_mode VARCHAR(20) NOT NULL,
          run_id BIGINT NOT NULL,
          source_gen_run_id BIGINT NULL,
          minute_window_count INT NOT NULL DEFAULT 0,
          active_minute_count INT NOT NULL DEFAULT 0,
          observed_event_count BIGINT NOT NULL DEFAULT 0,
          throughput_per_minute_avg DECIMAL(18,4) NULL,
          throughput_per_minute_p50 DECIMAL(18,4) NULL,
          throughput_per_minute_p95 DECIMAL(18,4) NULL,
          freshness_delay_sec_p50 DECIMAL(18,4) NULL,
          freshness_delay_sec_p95 DECIMAL(18,4) NULL,
          freshness_delay_sec_max DECIMAL(18,4) NULL,
          degraded_minute_count INT NOT NULL DEFAULT 0,
          severe_minute_count INT NOT NULL DEFAULT 0,
          metric_version VARCHAR(64) NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (dt, pipeline_name, entity_scope, processing_mode, runtime_mode, run_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_availability_day (
          dt DATE NOT NULL,
          pipeline_name VARCHAR(100) NOT NULL,
          entity_scope VARCHAR(100) NOT NULL,
          processing_mode VARCHAR(20) NOT NULL,
          runtime_mode VARCHAR(20) NOT NULL,
          run_count INT NOT NULL DEFAULT 0,
          success_run_count INT NOT NULL DEFAULT 0,
          failed_run_count INT NOT NULL DEFAULT 0,
          partial_run_count INT NOT NULL DEFAULT 0,
          timeout_run_count INT NOT NULL DEFAULT 0,
          success_rate DECIMAL(18,6) NULL,
          availability_ratio DECIMAL(18,6) NULL,
          zero_output_run_count INT NOT NULL DEFAULT 0,
          metric_version VARCHAR(64) NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (dt, pipeline_name, entity_scope, processing_mode, runtime_mode)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def schema_delete(cur, table: str, filters: dict[str, Any]) -> None:
    if not table_exists(cur, table):
        return
    cset = columns(cur, table)
    where_parts: list[str] = []
    params: list[Any] = []
    for col, value in filters.items():
        if col in cset:
            where_parts.append(f"{q(col)}=%s")
            params.append(value)
    if not where_parts:
        print(f"[WARN] skip delete {table}: no compatible filter columns")
        return
    sql = f"DELETE FROM {q(table)} WHERE " + " AND ".join(where_parts)
    cur.execute(sql, tuple(params))
    print(f"[INFO] deleted {table} rows={cur.rowcount} filters={','.join(k for k in filters if k in cset)}")


def insert_stg_event_stream(cur, args: argparse.Namespace) -> int:
    ce = columns(cur, "canonical_events")
    stg = columns(cur, "stg_event_stream")

    source_select = {
        "raw_event_id": f"COALESCE({first_col(ce, 'raw_event_id', 'canonical_event_id', default='0')}, 0)",
        "dt": first_col(ce, "target_date", "event_date", default="%s"),
        "ts": first_col(ce, "event_time", "event_ts", "ts", "request_ts", default="NOW()"),
        "event_name": first_col(ce, "event_type", "event_name", "page_event", default="'unknown'"),
        "service_domain": first_col(ce, "service_domain", "domain", default="'commerce'"),
        "funnel_stage": first_col(ce, "funnel_stage", default="NULL"),
        "is_conversion": f"COALESCE({first_col(ce, 'is_conversion', default='0')}, 0)",
        "uid": first_col(ce, "uid", "user_id", default="NULL"),
        "pcid": first_col(ce, "pcid", default="NULL"),
        "sid": first_col(ce, "session_id", "sid", default="NULL"),
        "ingest_ts": "NOW()",
        "event_delay_ms": "0",
        "status": first_col(ce, "status_code", "status", default="200"),
        "latency_ms": f"COALESCE({first_col(ce, 'latency_ms', default='0')}, 0)",
        "source_type": first_col(ce, "source_type", default="'canonical_fallback'"),
        "profile_id": first_col(ce, "profile_id", default="%s"),
        "run_id": "%s",
        "canonical_event_id": first_col(ce, "canonical_event_id", "event_id", default="0"),
        "source_gen_run_id": "%s",
        "event_type": first_col(ce, "event_type", "event_name", default="'unknown'"),
        "semantic_event_name": first_col(ce, "event_type", "event_name", default="'unknown'"),
        "product_type": first_col(ce, "product_type", default="NULL"),
        "device_type": first_col(ce, "device_type", default="NULL"),
        "page_type": first_col(ce, "page_type", default="NULL"),
        "status_code": first_col(ce, "status_code", "status", default="200"),
        "bytes": f"COALESCE({first_col(ce, 'bytes', default='0')}, 0)",
        "schema_version": first_col(ce, "schema_version", default="NULL"),
        "scenario_name": "%s",
        "anomaly_type": first_col(ce, "anomaly_type", default="NULL"),
        "stream_payload_json": "JSON_OBJECT('materialized_by','v05_stream_operational_fallback','source','canonical_events')",
    }
    insert_cols = [col for col in source_select if col in stg]
    select_exprs = [source_select[col] for col in insert_cols]

    where_parts = []
    params: list[Any] = []
    # SELECT placeholder parameters in select_exprs, in column order.
    for col in insert_cols:
        if source_select[col] == "%s":
            if col == "dt":
                params.append(args.target_date)
            elif col == "profile_id":
                params.append(args.profile_id)
            elif col == "run_id":
                params.append(args.run_id)
            elif col == "source_gen_run_id":
                params.append(args.source_gen_run_id)
            elif col == "scenario_name":
                params.append(args.scenario_name)

    if "profile_id" in ce:
        where_parts.append("profile_id=%s")
        params.append(args.profile_id)
    if "target_date" in ce:
        where_parts.append("target_date=%s")
        params.append(args.target_date)
    elif "event_date" in ce:
        where_parts.append("event_date=%s")
        params.append(args.target_date)
    if "run_id" in ce:
        where_parts.append("run_id=%s")
        params.append(args.run_id)
    if "source_gen_run_id" in ce:
        where_parts.append("source_gen_run_id=%s")
        params.append(args.source_gen_run_id)

    if not where_parts:
        raise RuntimeError("canonical_events has no compatible date/profile filters")

    sql = f"""
        INSERT INTO stg_event_stream ({', '.join(q(c) for c in insert_cols)})
        SELECT {', '.join(select_exprs)}
        FROM canonical_events
        WHERE {' AND '.join(where_parts)}
    """
    cur.execute(sql, tuple(params))
    return int(cur.rowcount or 0)


def insert_stream_replay_event(cur, args: argparse.Namespace) -> int:
    stg = columns(cur, "stg_event_stream")
    rep = columns(cur, "stream_replay_event")
    source_select = {
        "run_id": first_col(stg, "run_id", default="%s"),
        "profile_id": first_col(stg, "profile_id", default="%s"),
        "target_date": first_col(stg, "dt", default="%s"),
        "canonical_event_id": f"COALESCE({first_col(stg, 'canonical_event_id', 'raw_event_id', default='0')}, 0)",
        "event_time": first_col(stg, "ts", "event_ts", default="NOW()"),
        "event_date": first_col(stg, "dt", default="%s"),
        "service_domain": f"COALESCE({first_col(stg, 'service_domain', default='NULL')}, 'commerce')",
        "event_type": f"COALESCE({first_col(stg, 'event_type', 'event_name', default='NULL')}, 'unknown')",
        "uid": first_col(stg, "uid", default="NULL"),
        "session_id": first_col(stg, "sid", "session_id", default="NULL"),
        "page_type": first_col(stg, "page_type", default="NULL"),
        "funnel_stage": first_col(stg, "funnel_stage", default="NULL"),
        "status_code": first_col(stg, "status_code", "status", default="NULL"),
        "bytes": first_col(stg, "bytes", default="0"),
        "latency_ms": first_col(stg, "latency_ms", default="0"),
        "is_conversion": f"COALESCE({first_col(stg, 'is_conversion', default='0')}, 0)",
        "source_gen_run_id": first_col(stg, "source_gen_run_id", default="%s"),
        "replay_sequence": "ROW_NUMBER() OVER (ORDER BY ts, stream_ingest_id)",
        "replay_payload_json": "JSON_OBJECT('materialized_by','v05_stream_operational_fallback')",
        "operation_mode": "'fallback_from_canonical'",
        "op_materialized_at": "NOW()",
        "replay_sequence_no": "ROW_NUMBER() OVER (ORDER BY ts, stream_ingest_id)",
    }
    insert_cols = [col for col in source_select if col in rep]
    select_exprs = [source_select[col] for col in insert_cols]
    params: list[Any] = []
    for col in insert_cols:
        if source_select[col] == "%s":
            if col == "run_id":
                params.append(args.run_id)
            elif col == "profile_id":
                params.append(args.profile_id)
            elif col in {"target_date", "event_date"}:
                params.append(args.target_date)
            elif col == "source_gen_run_id":
                params.append(args.source_gen_run_id)
    where_parts = []
    if "profile_id" in stg:
        where_parts.append("profile_id=%s")
        params.append(args.profile_id)
    if "dt" in stg:
        where_parts.append("dt=%s")
        params.append(args.target_date)
    if "run_id" in stg:
        where_parts.append("run_id=%s")
        params.append(args.run_id)
    if "source_gen_run_id" in stg:
        where_parts.append("source_gen_run_id=%s")
        params.append(args.source_gen_run_id)
    sql = f"""
        INSERT INTO stream_replay_event ({', '.join(q(c) for c in insert_cols)})
        SELECT {', '.join(select_exprs)}
        FROM stg_event_stream
        WHERE {' AND '.join(where_parts)}
    """
    cur.execute(sql, tuple(params))
    return int(cur.rowcount or 0)


def replace_pipeline_performance_day(cur, args: argparse.Namespace, observed: int) -> None:
    cset = columns(cur, "pipeline_performance_summary_day")
    values: dict[str, Any] = {
        "dt": args.target_date,
        "pipeline_name": "stream_replay",
        "entity_scope": args.profile_id,
        "processing_mode": "stream",
        "runtime_mode": "replay",
        "run_id": args.run_id,
        "source_gen_run_id": args.source_gen_run_id,
        "minute_window_count": 1440,
        "active_minute_count": 1 if observed > 0 else 0,
        "observed_event_count": observed,
        "throughput_per_minute_avg": float(observed),
        "throughput_per_minute_p50": float(observed),
        "throughput_per_minute_p95": float(observed),
        "throughput_drop_ratio_avg": 0.0,
        "throughput_drop_ratio_p95": 0.0,
        "throughput_drop_ratio_max": 0.0,
        "freshness_delay_sec_p50": 0.0,
        "freshness_delay_sec_p95": 0.0,
        "freshness_delay_sec_max": 0.0,
        "consumer_lag_p50": 0.0,
        "consumer_lag_p95": 0.0,
        "consumer_lag_max": 0.0,
        "backlog_size_avg": 0.0,
        "backlog_size_p95": 0.0,
        "backlog_size_max": 0.0,
        "recovery_sec_avg": 0.0,
        "recovery_sec_max": 0.0,
        "degraded_minute_count": 0,
        "severe_minute_count": 0,
        "metric_version": "v05_fallback_from_canonical",
    }
    insert_cols = [col for col in values if col in cset]
    sql = f"REPLACE INTO pipeline_performance_summary_day ({', '.join(q(c) for c in insert_cols)}) VALUES ({', '.join(['%s'] * len(insert_cols))})"
    cur.execute(sql, tuple(values[c] for c in insert_cols))


def replace_pipeline_availability_day(cur, args: argparse.Namespace, observed: int) -> None:
    cset = columns(cur, "pipeline_availability_day")
    values: dict[str, Any] = {
        "dt": args.target_date,
        "pipeline_name": "stream_replay",
        "entity_scope": args.profile_id,
        "processing_mode": "stream",
        "runtime_mode": "replay",
        "run_count": 1,
        "success_run_count": 1 if observed > 0 else 0,
        "failed_run_count": 0 if observed > 0 else 1,
        "partial_run_count": 0,
        "timeout_run_count": 0,
        "success_rate": 1.0 if observed > 0 else 0.0,
        "no_data_interval_sec_sum": 0.0 if observed > 0 else 86400.0,
        "no_data_interval_sec_max": 0.0 if observed > 0 else 86400.0,
        "downtime_sec_sum": 0.0 if observed > 0 else 86400.0,
        "downtime_sec_max": 0.0 if observed > 0 else 86400.0,
        "recovery_sec_avg": 0.0,
        "recovery_sec_max": 0.0,
        "availability_ratio": 1.0 if observed > 0 else 0.0,
        "zero_output_run_count": 0 if observed > 0 else 1,
        "metric_version": "v05_fallback_from_canonical",
    }
    insert_cols = [col for col in values if col in cset]
    sql = f"REPLACE INTO pipeline_availability_day ({', '.join(q(c) for c in insert_cols)}) VALUES ({', '.join(['%s'] * len(insert_cols))})"
    cur.execute(sql, tuple(values[c] for c in insert_cols))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Schema-aware Kafka-off stream/operational fallback materialization for v0.5 commerce."
    )
    parser.add_argument("--db-host", required=True)
    parser.add_argument("--db-port", type=int, required=True)
    parser.add_argument("--db-user", required=True)
    parser.add_argument("--db-pass", required=True)
    parser.add_argument("--db-name", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--target-date", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--source-gen-run-id", required=True, type=int)
    parser.add_argument("--scenario-name", default="baseline")
    parser.add_argument("--truncate-target", action="store_true")
    args = parser.parse_args()

    connection = connect(args)
    try:
        with connection.cursor() as cur:
            ensure_required_tables(cur)
            if not table_exists(cur, "canonical_events"):
                raise RuntimeError("canonical_events table not found")

            if args.truncate_target:
                schema_delete(
                    cur,
                    "stg_event_stream",
                    {
                        "profile_id": args.profile_id,
                        "dt": args.target_date,
                        "run_id": args.run_id,
                        "source_gen_run_id": args.source_gen_run_id,
                    },
                )
                schema_delete(
                    cur,
                    "stream_replay_event",
                    {
                        "profile_id": args.profile_id,
                        "target_date": args.target_date,
                        "run_id": args.run_id,
                        "source_gen_run_id": args.source_gen_run_id,
                    },
                )
                schema_delete(
                    cur,
                    "pipeline_performance_summary_day",
                    {
                        "dt": args.target_date,
                        "pipeline_name": "stream_replay",
                        "entity_scope": args.profile_id,
                        "processing_mode": "stream",
                        "runtime_mode": "replay",
                        "run_id": args.run_id,
                        "source_gen_run_id": args.source_gen_run_id,
                    },
                )
                schema_delete(
                    cur,
                    "pipeline_availability_day",
                    {
                        "dt": args.target_date,
                        "pipeline_name": "stream_replay",
                        "entity_scope": args.profile_id,
                        "processing_mode": "stream",
                        "runtime_mode": "replay",
                    },
                )

            stg_rows = insert_stg_event_stream(cur, args)
            replay_rows = insert_stream_replay_event(cur, args)
            replace_pipeline_performance_day(cur, args, stg_rows)
            replace_pipeline_availability_day(cur, args, stg_rows)

        connection.commit()
        print(
            "[OK] materialize_v05_stream_operational_fallback "
            f"stg_event_stream_rows={stg_rows} stream_replay_event_rows={replay_rows} "
            "performance_table=schema_aware availability_table=schema_aware"
        )
        return 0
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
