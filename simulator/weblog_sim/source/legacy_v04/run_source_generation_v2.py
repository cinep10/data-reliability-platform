from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

import pymysql
import yaml


SOURCE_SCENARIOS = {
    "source_campaign_spike",
    "source_weather_drop",
    "source_system_degraded",
    "source_no_data",
    "source_partial_missing",
    "source_latency_degradation",
    "source_identity_drift",
    "source_schema_drift",
}

APACHE_TS_RE = re.compile(r"\[(?P<ts>\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}) [+-]\d{4}\]")

COOKIE_FIELD_RE = re.compile(r'"(?P<cookie>[^"\n]*(?:pcid=|sid=|uid=)[^"\n]*)"\s*$')

COOKIE_DEFAULTS = {
    "weather": "clear",
    "weather_type": "clear",
    "campaign_flag": "none",
    "system_flag": "normal",
    "exo_source": "baseline",
}



@dataclass(frozen=True)
class TimelineRule:
    timeline_id: int
    experiment_id: str
    profile_id: str
    target_date: str
    scenario_id: str
    start_ts: datetime
    end_ts: datetime
    entity_type: str
    entity_id: str
    effect_type: str
    effect_value: Optional[float]
    effect_payload_json: Optional[str]
    priority: int
    deterministic_seed: int


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="v0.4 Phase 1 DB-backed source generation")

    # v0.3-compatible orchestration args
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--target-date", required=False, help="YYYY-MM-DD")
    ap.add_argument("--dt-from", required=False, help="alias of --target-date")
    ap.add_argument("--scenario-name", required=False, default="baseline")
    ap.add_argument("--scenario-mode", required=False, default="baseline")
    ap.add_argument("--source-mode", required=False, default="simulator_file_generate")
    ap.add_argument("--profile-config", required=True)
    ap.add_argument("--scenario-config", required=False)
    ap.add_argument("--exogenous-config", required=False, help="kept for v0.3 contract; v2 uses DB timeline")
    ap.add_argument("--avg-rps", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--out-file", required=False)

    # v0.4 args
    ap.add_argument("--experiment-id", required=False)
    ap.add_argument("--scenario-id", required=False)
    ap.add_argument("--start", required=False, help="YYYY-MM-DDTHH:MM:SS")
    ap.add_argument("--end", required=False, help="YYYY-MM-DDTHH:MM:SS")
    ap.add_argument("--auto-seed-timeline", default="true", choices=["true", "false"])
    ap.add_argument("--replace-timeline", action="store_true")
    ap.add_argument("--simulator-version", default="v0.4-phase1")
    ap.add_argument("--created-by", default="local")
    ap.add_argument("--note", default="")

    # DB
    ap.add_argument("--db-host", required=True)
    ap.add_argument("--db-port", required=True, type=int)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", required=True)
    ap.add_argument("--db-name", required=True)

    # execution
    ap.add_argument("--python-bin", default="python")
    ap.add_argument("--simulator-cli-module", default="simulator.weblog_sim.cli")
    return ap.parse_args()


def bool_arg(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def derive_dates(args: argparse.Namespace) -> tuple[str, str, str]:
    target_date = args.target_date or args.dt_from
    if target_date and (args.start or args.end):
        raise ValueError("Use --target-date/--dt-from OR --start/--end, not both.")
    if target_date:
        return target_date, f"{target_date}T00:00:00", f"{target_date}T23:59:59"
    if not (args.start and args.end):
        raise ValueError("Either --target-date/--dt-from or both --start and --end are required.")
    target_date = str(args.start).split("T")[0]
    return target_date, args.start, args.end


def output_path(args: argparse.Namespace, target_date: str, start: str, end: str) -> Path:
    if args.out_file:
        p = Path(args.out_file)
    else:
        start_date = start.split("T")[0]
        end_date = end.split("T")[0]
        p = Path(args.output_dir) / f"{args.profile_id}_{start_date}_{end_date}.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


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


def exec_sql(conn, sql: str, params: Any = None) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params)


def fetch_all(conn, sql: str, params: Any = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def fetch_one(conn, sql: str, params: Any = None) -> Optional[dict[str, Any]]:
    rows = fetch_all(conn, sql, params)
    return rows[0] if rows else None


def table_columns(conn, table_name: str) -> set[str]:
    rows = fetch_all(conn, """
      SELECT column_name
      FROM information_schema.columns
      WHERE table_schema = DATABASE() AND table_name = %s
    """, (table_name,))
    return {str(r["column_name"]) for r in rows}


def ensure_column(conn, table_name: str, column_name: str, ddl_fragment: str) -> None:
    if column_name not in table_columns(conn, table_name):
        exec_sql(conn, f"ALTER TABLE {table_name} ADD COLUMN {ddl_fragment}")
        conn.commit()


def index_exists(conn, table_name: str, index_name: str) -> bool:
    row = fetch_one(conn, """
      SELECT COUNT(*) AS cnt
      FROM information_schema.statistics
      WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s
    """, (table_name, index_name))
    return bool(row and int(row["cnt"]) > 0)


def ensure_index(conn, table_name: str, index_name: str, ddl: str) -> None:
    if not index_exists(conn, table_name, index_name):
        try:
            exec_sql(conn, ddl)
            conn.commit()
        except pymysql.err.OperationalError as exc:
            # 1061 = duplicate key name. Safe when another concurrent/old migration created it.
            if exc.args and exc.args[0] == 1061:
                conn.rollback()
            else:
                raise


def ensure_phase1_migrations(conn) -> None:
    # Existing local DBs may already have older v0.4 tables without profile_id/target_date.
    # CREATE TABLE IF NOT EXISTS does not upgrade those tables, so apply additive migrations.
    ensure_column(conn, "source_scenario_catalog", "scenario_type", "scenario_type VARCHAR(50) NOT NULL DEFAULT 'source'")
    ensure_column(conn, "source_scenario_catalog", "description", "description TEXT NULL")
    ensure_column(conn, "source_scenario_catalog", "expected_signal", "expected_signal VARCHAR(200) NULL")
    ensure_column(conn, "source_scenario_catalog", "expected_risk_layer", "expected_risk_layer VARCHAR(100) NULL")
    ensure_column(conn, "source_scenario_catalog", "default_window_start", "default_window_start TIME NOT NULL DEFAULT '10:00:00'")
    ensure_column(conn, "source_scenario_catalog", "default_window_end", "default_window_end TIME NOT NULL DEFAULT '12:00:00'")
    ensure_column(conn, "source_scenario_catalog", "is_active", "is_active TINYINT(1) NOT NULL DEFAULT 1")
    ensure_column(conn, "source_scenario_catalog", "created_at", "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
    ensure_column(conn, "source_scenario_catalog", "updated_at", "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")

    ensure_column(conn, "exogenous_timeline_v1", "experiment_id", "experiment_id VARCHAR(100) NULL")
    ensure_column(conn, "exogenous_timeline_v1", "profile_id", "profile_id VARCHAR(100) NULL")
    ensure_column(conn, "exogenous_timeline_v1", "target_date", "target_date DATE NULL")
    ensure_column(conn, "exogenous_timeline_v1", "scenario_id", "scenario_id VARCHAR(100) NULL")
    ensure_column(conn, "exogenous_timeline_v1", "start_ts", "start_ts DATETIME NULL")
    ensure_column(conn, "exogenous_timeline_v1", "end_ts", "end_ts DATETIME NULL")
    ensure_column(conn, "exogenous_timeline_v1", "entity_type", "entity_type VARCHAR(50) NOT NULL DEFAULT 'global'")
    ensure_column(conn, "exogenous_timeline_v1", "entity_id", "entity_id VARCHAR(100) NOT NULL DEFAULT 'global'")
    ensure_column(conn, "exogenous_timeline_v1", "effect_type", "effect_type VARCHAR(100) NULL")
    ensure_column(conn, "exogenous_timeline_v1", "effect_value", "effect_value DECIMAL(14,6) NULL")
    ensure_column(conn, "exogenous_timeline_v1", "effect_payload_json", "effect_payload_json JSON NULL")
    ensure_column(conn, "exogenous_timeline_v1", "priority", "priority INT NOT NULL DEFAULT 100")
    ensure_column(conn, "exogenous_timeline_v1", "deterministic_seed", "deterministic_seed BIGINT NOT NULL DEFAULT 42")
    ensure_column(conn, "exogenous_timeline_v1", "created_at", "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
    ensure_index(conn, "exogenous_timeline_v1", "idx_exo_v1_lookup", "ALTER TABLE exogenous_timeline_v1 ADD INDEX idx_exo_v1_lookup (experiment_id, profile_id, target_date, scenario_id, start_ts, end_ts)")
    ensure_index(conn, "exogenous_timeline_v1", "idx_exo_v1_effect", "ALTER TABLE exogenous_timeline_v1 ADD INDEX idx_exo_v1_effect (scenario_id, effect_type)")

    ensure_column(conn, "source_generation_result_summary", "experiment_id", "experiment_id VARCHAR(100) NULL")
    ensure_column(conn, "source_generation_result_summary", "scenario_id", "scenario_id VARCHAR(100) NULL")
    ensure_column(conn, "source_generation_result_summary", "profile_id", "profile_id VARCHAR(100) NULL")
    ensure_column(conn, "source_generation_result_summary", "target_date", "target_date DATE NULL")
    ensure_column(conn, "source_generation_result_summary", "source_gen_run_id", "source_gen_run_id BIGINT NULL")
    ensure_column(conn, "source_generation_result_summary", "source_file_path", "source_file_path VARCHAR(500) NULL")
    ensure_column(conn, "source_generation_result_summary", "simulator_version", "simulator_version VARCHAR(100) NULL")
    ensure_column(conn, "source_generation_result_summary", "deterministic_seed", "deterministic_seed BIGINT NOT NULL DEFAULT 42")
    ensure_column(conn, "source_generation_result_summary", "timeline_hash", "timeline_hash VARCHAR(128) NULL")
    ensure_column(conn, "source_generation_result_summary", "config_hash", "config_hash VARCHAR(128) NULL")
    ensure_column(conn, "source_generation_result_summary", "output_file_checksum", "output_file_checksum VARCHAR(128) NULL")
    ensure_column(conn, "source_generation_result_summary", "row_count", "row_count BIGINT NOT NULL DEFAULT 0")
    ensure_column(conn, "source_generation_result_summary", "affected_row_count", "affected_row_count BIGINT NOT NULL DEFAULT 0")
    ensure_column(conn, "source_generation_result_summary", "min_event_ts", "min_event_ts DATETIME NULL")
    ensure_column(conn, "source_generation_result_summary", "max_event_ts", "max_event_ts DATETIME NULL")
    ensure_column(conn, "source_generation_result_summary", "started_at", "started_at DATETIME NULL")
    ensure_column(conn, "source_generation_result_summary", "finished_at", "finished_at DATETIME NULL")
    ensure_column(conn, "source_generation_result_summary", "created_at", "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
    ensure_index(conn, "source_generation_result_summary", "idx_sgrs_lookup", "ALTER TABLE source_generation_result_summary ADD INDEX idx_sgrs_lookup (experiment_id, scenario_id, profile_id, target_date)")

    exec_sql(conn, """
    CREATE TABLE IF NOT EXISTS source_generation_result_history (
      history_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      experiment_id VARCHAR(100) NOT NULL,
      scenario_id VARCHAR(100) NOT NULL,
      profile_id VARCHAR(100) NOT NULL,
      target_date DATE NOT NULL,
      source_gen_run_id BIGINT NULL,
      source_file_path VARCHAR(500) NOT NULL,
      simulator_version VARCHAR(100) NOT NULL,
      deterministic_seed BIGINT NOT NULL,
      timeline_hash VARCHAR(128) NOT NULL,
      config_hash VARCHAR(128) NOT NULL,
      output_file_checksum VARCHAR(128) NOT NULL,
      row_count BIGINT NOT NULL,
      affected_row_count BIGINT NOT NULL DEFAULT 0,
      min_event_ts DATETIME NULL,
      max_event_ts DATETIME NULL,
      started_at DATETIME NULL,
      finished_at DATETIME NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      KEY idx_sgrh_lookup (experiment_id, scenario_id, profile_id, target_date),
      KEY idx_sgrh_checksum (output_file_checksum)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    ensure_column(conn, "exogenous_state_timeline", "profile_id", "profile_id VARCHAR(100) NULL")
    ensure_column(conn, "exogenous_state_timeline", "dt", "dt DATE NULL")
    ensure_column(conn, "exogenous_state_timeline", "hh", "hh INT NULL")
    ensure_column(conn, "exogenous_state_timeline", "weather_type", "weather_type VARCHAR(50) NOT NULL DEFAULT 'clear'")
    ensure_column(conn, "exogenous_state_timeline", "campaign_flag", "campaign_flag VARCHAR(100) NOT NULL DEFAULT 'none'")
    ensure_column(conn, "exogenous_state_timeline", "system_flag", "system_flag VARCHAR(100) NOT NULL DEFAULT 'normal'")
    ensure_column(conn, "exogenous_state_timeline", "volume_multiplier", "volume_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000")
    ensure_column(conn, "exogenous_state_timeline", "conversion_multiplier", "conversion_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000")
    ensure_column(conn, "exogenous_state_timeline", "timeout_multiplier", "timeout_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000")
    ensure_column(conn, "exogenous_state_timeline", "retry_multiplier", "retry_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000")
    ensure_column(conn, "exogenous_state_timeline", "drop_probability", "drop_probability DECIMAL(14,6) NOT NULL DEFAULT 0.000000")
    ensure_column(conn, "exogenous_state_timeline", "latency_shift_ms", "latency_shift_ms INT NOT NULL DEFAULT 0")
    ensure_column(conn, "exogenous_state_timeline", "suppress_input", "suppress_input TINYINT(1) NOT NULL DEFAULT 0")
    ensure_column(conn, "exogenous_state_timeline", "source", "source VARCHAR(50) NOT NULL DEFAULT 'exogenous_timeline_v1'")
    ensure_column(conn, "exogenous_state_timeline", "anomaly_type", "anomaly_type VARCHAR(100) NOT NULL DEFAULT 'none'")
    ensure_column(conn, "exogenous_state_timeline", "schema_version", "schema_version VARCHAR(100) NOT NULL DEFAULT 'v0.4-source-anomaly-contract'")
    ensure_column(conn, "exogenous_state_timeline", "schema_flag", "schema_flag VARCHAR(50) NOT NULL DEFAULT 'normal'")
    ensure_column(conn, "exogenous_state_timeline", "identity_flag", "identity_flag VARCHAR(50) NOT NULL DEFAULT 'normal'")
    ensure_column(conn, "exogenous_state_timeline", "pcid_stability", "pcid_stability VARCHAR(50) NOT NULL DEFAULT 'stable'")
    ensure_column(conn, "exogenous_state_timeline", "session_stability", "session_stability VARCHAR(50) NOT NULL DEFAULT 'stable'")
    ensure_column(conn, "exogenous_state_timeline", "customer_id_stability", "customer_id_stability VARCHAR(50) NOT NULL DEFAULT 'stable'")
    ensure_column(conn, "exogenous_state_timeline", "traffic_actor", "traffic_actor VARCHAR(50) NOT NULL DEFAULT 'human'")
    ensure_column(conn, "exogenous_state_timeline", "bot_flag", "bot_flag VARCHAR(10) NOT NULL DEFAULT '0'")
    ensure_column(conn, "exogenous_state_timeline", "user_agent_flag", "user_agent_flag VARCHAR(50) NOT NULL DEFAULT 'normal'")
    ensure_column(conn, "exogenous_state_timeline", "ip_concentration_flag", "ip_concentration_flag VARCHAR(50) NOT NULL DEFAULT 'normal'")
    ensure_column(conn, "exogenous_state_timeline", "recovery_flag", "recovery_flag VARCHAR(50) NOT NULL DEFAULT 'none'")
    ensure_column(conn, "exogenous_state_timeline", "backlog_flush", "backlog_flush VARCHAR(10) NOT NULL DEFAULT '0'")
    ensure_column(conn, "exogenous_state_timeline", "transaction_delay_ms", "transaction_delay_ms INT NOT NULL DEFAULT 0")
    ensure_column(conn, "exogenous_state_timeline", "event_ingestion_delay_ms", "event_ingestion_delay_ms INT NOT NULL DEFAULT 0")
    ensure_column(conn, "exogenous_state_timeline", "privacy_flag", "privacy_flag VARCHAR(50) NOT NULL DEFAULT 'normal'")
    ensure_column(conn, "exogenous_state_timeline", "pii_detected", "pii_detected VARCHAR(10) NOT NULL DEFAULT '0'")
    ensure_column(conn, "exogenous_state_timeline", "sensitive_field_flag", "sensitive_field_flag VARCHAR(50) NOT NULL DEFAULT 'none'")
    ensure_column(conn, "exogenous_state_timeline", "masking_status", "masking_status VARCHAR(50) NOT NULL DEFAULT 'masked'")
    ensure_column(conn, "exogenous_state_timeline", "duplicate_multiplier", "duplicate_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000")
    ensure_column(conn, "exogenous_state_timeline", "event_time_skew_ms", "event_time_skew_ms INT NOT NULL DEFAULT 0")
    ensure_column(conn, "exogenous_state_timeline", "created_at", "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
    ensure_index(conn, "exogenous_state_timeline", "idx_est_profile_dt_hh", "ALTER TABLE exogenous_state_timeline ADD INDEX idx_est_profile_dt_hh (profile_id, dt, hh)")


def ensure_phase1_tables(conn) -> None:
    exec_sql(conn, """
    CREATE TABLE IF NOT EXISTS source_scenario_catalog (
      scenario_id VARCHAR(100) NOT NULL PRIMARY KEY,
      scenario_name VARCHAR(200) NOT NULL,
      scenario_type VARCHAR(50) NOT NULL DEFAULT 'source',
      description TEXT NULL,
      expected_signal VARCHAR(200) NULL,
      expected_risk_layer VARCHAR(100) NULL,
      default_window_start TIME NOT NULL DEFAULT '10:00:00',
      default_window_end TIME NOT NULL DEFAULT '12:00:00',
      is_active TINYINT(1) NOT NULL DEFAULT 1,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    exec_sql(conn, """
    CREATE TABLE IF NOT EXISTS exogenous_timeline_v1 (
      timeline_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      experiment_id VARCHAR(100) NOT NULL,
      profile_id VARCHAR(100) NOT NULL,
      target_date DATE NOT NULL,
      scenario_id VARCHAR(100) NOT NULL,
      start_ts DATETIME NOT NULL,
      end_ts DATETIME NOT NULL,
      entity_type VARCHAR(50) NOT NULL DEFAULT 'global',
      entity_id VARCHAR(100) NOT NULL DEFAULT 'global',
      effect_type VARCHAR(100) NOT NULL,
      effect_value DECIMAL(14,6) NULL,
      effect_payload_json JSON NULL,
      priority INT NOT NULL DEFAULT 100,
      deterministic_seed BIGINT NOT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      KEY idx_exo_v1_lookup (experiment_id, profile_id, target_date, scenario_id, start_ts, end_ts),
      KEY idx_exo_v1_effect (scenario_id, effect_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    exec_sql(conn, """
    CREATE TABLE IF NOT EXISTS source_generation_result_summary (
      experiment_id VARCHAR(100) NOT NULL,
      scenario_id VARCHAR(100) NOT NULL,
      profile_id VARCHAR(100) NOT NULL,
      target_date DATE NOT NULL,
      source_gen_run_id BIGINT NULL,
      source_file_path VARCHAR(500) NOT NULL,
      simulator_version VARCHAR(100) NOT NULL,
      deterministic_seed BIGINT NOT NULL,
      timeline_hash VARCHAR(128) NOT NULL,
      config_hash VARCHAR(128) NOT NULL,
      output_file_checksum VARCHAR(128) NOT NULL,
      row_count BIGINT NOT NULL,
      affected_row_count BIGINT NOT NULL DEFAULT 0,
      min_event_ts DATETIME NULL,
      max_event_ts DATETIME NULL,
      started_at DATETIME NULL,
      finished_at DATETIME NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (experiment_id, scenario_id, profile_id, target_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    exec_sql(conn, """
    CREATE TABLE IF NOT EXISTS source_generation_result_history (
      history_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      experiment_id VARCHAR(100) NOT NULL,
      scenario_id VARCHAR(100) NOT NULL,
      profile_id VARCHAR(100) NOT NULL,
      target_date DATE NOT NULL,
      source_gen_run_id BIGINT NULL,
      source_file_path VARCHAR(500) NOT NULL,
      simulator_version VARCHAR(100) NOT NULL,
      deterministic_seed BIGINT NOT NULL,
      timeline_hash VARCHAR(128) NOT NULL,
      config_hash VARCHAR(128) NOT NULL,
      output_file_checksum VARCHAR(128) NOT NULL,
      row_count BIGINT NOT NULL,
      affected_row_count BIGINT NOT NULL DEFAULT 0,
      min_event_ts DATETIME NULL,
      max_event_ts DATETIME NULL,
      started_at DATETIME NULL,
      finished_at DATETIME NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      KEY idx_sgrh_lookup (experiment_id, scenario_id, profile_id, target_date),
      KEY idx_sgrh_checksum (output_file_checksum)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    exec_sql(conn, """
    CREATE TABLE IF NOT EXISTS exogenous_state_timeline (
      profile_id VARCHAR(100) NOT NULL,
      dt DATE NOT NULL,
      hh INT NOT NULL,
      weather_type VARCHAR(50) NOT NULL DEFAULT 'clear',
      campaign_flag VARCHAR(100) NOT NULL DEFAULT 'none',
      system_flag VARCHAR(100) NOT NULL DEFAULT 'normal',
      volume_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000,
      conversion_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000,
      timeout_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000,
      retry_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000,
      drop_probability DECIMAL(14,6) NOT NULL DEFAULT 0.000000,
      latency_shift_ms INT NOT NULL DEFAULT 0,
      suppress_input TINYINT(1) NOT NULL DEFAULT 0,
      source VARCHAR(50) NOT NULL DEFAULT 'exogenous_timeline_v1',
      anomaly_type VARCHAR(100) NOT NULL DEFAULT 'none',
      schema_version VARCHAR(100) NOT NULL DEFAULT 'v0.4-source-anomaly-contract',
      schema_flag VARCHAR(50) NOT NULL DEFAULT 'normal',
      identity_flag VARCHAR(50) NOT NULL DEFAULT 'normal',
      pcid_stability VARCHAR(50) NOT NULL DEFAULT 'stable',
      session_stability VARCHAR(50) NOT NULL DEFAULT 'stable',
      customer_id_stability VARCHAR(50) NOT NULL DEFAULT 'stable',
      traffic_actor VARCHAR(50) NOT NULL DEFAULT 'human',
      bot_flag VARCHAR(10) NOT NULL DEFAULT '0',
      user_agent_flag VARCHAR(50) NOT NULL DEFAULT 'normal',
      ip_concentration_flag VARCHAR(50) NOT NULL DEFAULT 'normal',
      recovery_flag VARCHAR(50) NOT NULL DEFAULT 'none',
      backlog_flush VARCHAR(10) NOT NULL DEFAULT '0',
      transaction_delay_ms INT NOT NULL DEFAULT 0,
      event_ingestion_delay_ms INT NOT NULL DEFAULT 0,
      privacy_flag VARCHAR(50) NOT NULL DEFAULT 'normal',
      pii_detected VARCHAR(10) NOT NULL DEFAULT '0',
      sensitive_field_flag VARCHAR(50) NOT NULL DEFAULT 'none',
      masking_status VARCHAR(50) NOT NULL DEFAULT 'masked',
      duplicate_multiplier DECIMAL(14,6) NOT NULL DEFAULT 1.000000,
      event_time_skew_ms INT NOT NULL DEFAULT 0,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (profile_id, dt, hh)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    exec_sql(conn, """
    CREATE TABLE IF NOT EXISTS verification_snapshot_v1 (
      snapshot_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      profile_id VARCHAR(100) NOT NULL,
      target_date DATE NOT NULL,
      scenario_id VARCHAR(100) NOT NULL,
      source_rows BIGINT NOT NULL DEFAULT 0,
      affected_rows BIGINT NOT NULL DEFAULT 0,
      timeline_rows BIGINT NOT NULL DEFAULT 0,
      checksum_count INT NOT NULL DEFAULT 0,
      validation_status VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
      details_json JSON NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      KEY idx_vs_lookup (profile_id, target_date, scenario_id, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    conn.commit()
    ensure_phase1_migrations(conn)


def seed_scenario_catalog(conn) -> None:
    rows = [
        ("source_campaign_spike", "Source Campaign Spike", "campaign traffic spike", "row_count_up", "source_volume"),
        ("source_weather_drop", "Source Weather Drop", "weather-driven conversion/latency shift", "conversion_down_latency_up", "source_quality"),
        ("source_system_degraded", "Source System Degraded", "timeout/retry/latency increase", "timeout_retry_latency_up", "performance_availability"),
        ("source_no_data", "Source No Data", "source log gap", "row_gap", "availability"),
        ("source_partial_missing", "Source Partial Missing", "partial source event loss", "drop_probability_up", "source_completeness"),
        ("source_latency_degradation", "Source Latency Degradation", "source latency degradation", "latency_shift_up", "source_timeliness"),
        ("source_identity_drift", "Source Identity Drift", "pcid/session/customer stability drift", "identity_flag_drift", "identity_reliability"),
        ("source_schema_drift", "Source Schema Drift", "schema version/flag drift", "schema_flag_drift", "schema_reliability"),
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO source_scenario_catalog
            (scenario_id, scenario_name, description, expected_signal, expected_risk_layer)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              scenario_name=VALUES(scenario_name),
              description=VALUES(description),
              expected_signal=VALUES(expected_signal),
              expected_risk_layer=VALUES(expected_risk_layer),
              updated_at=NOW()
            """,
            rows,
        )
    conn.commit()


def default_rules_for(scenario_id: str, start_ts: datetime, seed: int) -> list[tuple[str, Optional[float], Optional[dict[str, Any]], int]]:
    if scenario_id == "source_campaign_spike":
        return [
            ("volume_multiplier", 3.0, None, 10),
            ("conversion_multiplier", 1.2, None, 20),
            ("campaign_flag", None, {"campaign_flag": "loan_promo"}, 30),
        ]
    if scenario_id == "source_weather_drop":
        return [
            ("volume_multiplier", 0.6, None, 10),
            ("conversion_multiplier", 0.5, None, 20),
            ("timeout_multiplier", 1.15, None, 30),
            ("latency_shift_ms", 200.0, None, 35),
            ("weather_type", None, {"weather_type": "rain"}, 40),
        ]
    if scenario_id == "source_system_degraded":
        return [
            ("timeout_multiplier", 2.0, None, 10),
            ("retry_multiplier", 3.0, None, 20),
            ("latency_shift_ms", 500.0, None, 5),
            ("system_flag", None, {"system_flag": "degraded"}, 30),
        ]
    if scenario_id == "source_no_data":
        return [("suppress_input", 1.0, None, 10), ("anomaly_type", None, {"anomaly_type": "no_data"}, 20)]
    if scenario_id == "source_partial_missing":
        return [
            ("drop_probability", 0.20, None, 10),
            ("anomaly_type", None, {"anomaly_type": "partial_missing"}, 20),
        ]
    if scenario_id == "source_latency_degradation":
        return [
            ("latency_shift_ms", 900.0, None, 10),
            ("timeout_multiplier", 1.20, None, 20),
            ("anomaly_type", None, {"anomaly_type": "latency_degradation"}, 30),
        ]
    if scenario_id == "source_identity_drift":
        return [
            ("identity_flag", None, {"identity_flag": "drift"}, 10),
            ("pcid_stability", None, {"pcid_stability": "unstable"}, 20),
            ("session_stability", None, {"session_stability": "unstable"}, 30),
            ("customer_id_stability", None, {"customer_id_stability": "unstable"}, 40),
            ("anomaly_type", None, {"anomaly_type": "identity_drift"}, 50),
        ]
    if scenario_id == "source_schema_drift":
        return [
            ("schema_flag", None, {"schema_flag": "drift"}, 10),
            ("schema_version", None, {"schema_version": "v0.4-source-anomaly-contract-drifted"}, 20),
            ("anomaly_type", None, {"anomaly_type": "schema_drift"}, 30),
        ]
    return []


def ensure_default_timeline(conn, args, experiment_id: str, scenario_id: str, target_date: str, seed: int) -> None:
    if scenario_id not in SOURCE_SCENARIOS:
        return
    if args.replace_timeline:
        exec_sql(conn, """
        DELETE FROM exogenous_timeline_v1
        WHERE experiment_id=%s AND profile_id=%s AND target_date=%s AND scenario_id=%s
        """, (experiment_id, args.profile_id, target_date, scenario_id))
        conn.commit()
    existing = fetch_one(conn, """
      SELECT COUNT(*) AS cnt FROM exogenous_timeline_v1
      WHERE experiment_id=%s AND profile_id=%s AND target_date=%s AND scenario_id=%s
    """, (experiment_id, args.profile_id, target_date, scenario_id))
    if int(existing["cnt"]) > 0:
        return

    window_start = datetime.fromisoformat(f"{target_date}T10:00:00")
    window_end = datetime.fromisoformat(f"{target_date}T12:00:00")
    if scenario_id == "source_no_data":
        window_end = datetime.fromisoformat(f"{target_date}T11:00:00")

    rows = []
    for effect_type, effect_value, payload, priority in default_rules_for(scenario_id, window_start, seed):
        rows.append((
            experiment_id,
            args.profile_id,
            target_date,
            scenario_id,
            window_start,
            window_end,
            "global",
            "global",
            effect_type,
            effect_value,
            json.dumps(payload, ensure_ascii=False) if payload else None,
            priority,
            seed,
        ))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO exogenous_timeline_v1
            (experiment_id, profile_id, target_date, scenario_id, start_ts, end_ts,
             entity_type, entity_id, effect_type, effect_value, effect_payload_json,
             priority, deterministic_seed)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )
    conn.commit()


def load_rules(conn, experiment_id: str, profile_id: str, target_date: str, scenario_id: str) -> list[TimelineRule]:
    rows = fetch_all(conn, """
      SELECT * FROM exogenous_timeline_v1
      WHERE experiment_id=%s AND profile_id=%s AND target_date=%s AND scenario_id=%s
      ORDER BY start_ts, end_ts, priority, timeline_id
    """, (experiment_id, profile_id, target_date, scenario_id))
    rules = []
    for r in rows:
        rules.append(TimelineRule(
            timeline_id=int(r["timeline_id"]),
            experiment_id=str(r["experiment_id"]),
            profile_id=str(r["profile_id"]),
            target_date=str(r["target_date"]),
            scenario_id=str(r["scenario_id"]),
            start_ts=r["start_ts"],
            end_ts=r["end_ts"],
            entity_type=str(r["entity_type"]),
            entity_id=str(r["entity_id"]),
            effect_type=str(r["effect_type"]),
            effect_value=float(r["effect_value"]) if r["effect_value"] is not None else None,
            effect_payload_json=r.get("effect_payload_json"),
            priority=int(r["priority"]),
            deterministic_seed=int(r["deterministic_seed"]),
        ))
    return rules


def rule_payload(rule: TimelineRule) -> dict[str, Any]:
    if not rule.effect_payload_json:
        return {}
    if isinstance(rule.effect_payload_json, (dict, list)):
        return rule.effect_payload_json if isinstance(rule.effect_payload_json, dict) else {}
    return json.loads(rule.effect_payload_json)


def timeline_hash(rules: Iterable[TimelineRule]) -> str:
    payload = []
    for r in rules:
        payload.append({
            "experiment_id": r.experiment_id,
            "profile_id": r.profile_id,
            "target_date": r.target_date,
            "scenario_id": r.scenario_id,
            "start_ts": r.start_ts.isoformat(sep=" "),
            "end_ts": r.end_ts.isoformat(sep=" "),
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "effect_type": r.effect_type,
            "effect_value": r.effect_value,
            "effect_payload_json": rule_payload(r),
            "priority": r.priority,
            "deterministic_seed": r.deterministic_seed,
        })
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def merge_rules_at(rules: list[TimelineRule], when: datetime) -> dict[str, Any]:
    state = {
        "weather_type": "clear",
        "campaign_flag": "none",
        "system_flag": "normal",
        "volume_multiplier": 1.0,
        "conversion_multiplier": 1.0,
        "timeout_multiplier": 1.0,
        "retry_multiplier": 1.0,
        "drop_probability": 0.0,
        "latency_shift_ms": 0,
        "suppress_input": False,
        "anomaly_type": "none",
        "schema_version": "v0.4-source-anomaly-contract",
        "schema_flag": "normal",
        "identity_flag": "normal",
        "pcid_stability": "stable",
        "session_stability": "stable",
        "customer_id_stability": "stable",
        "traffic_actor": "human",
        "bot_flag": "0",
        "user_agent_flag": "normal",
        "ip_concentration_flag": "normal",
        "recovery_flag": "none",
        "backlog_flush": "0",
        "transaction_delay_ms": 0,
        "event_ingestion_delay_ms": 0,
        "privacy_flag": "normal",
        "pii_detected": "0",
        "sensitive_field_flag": "none",
        "masking_status": "masked",
        "duplicate_multiplier": 1.0,
        "event_time_skew_ms": 0,
    }
    for r in sorted(rules, key=lambda x: x.priority):
        if not (r.start_ts <= when < r.end_ts):
            continue
        payload = rule_payload(r)
        et = r.effect_type
        if et in {"volume_multiplier", "conversion_multiplier", "timeout_multiplier", "retry_multiplier"}:
            state[et] = float(state[et]) * float(r.effect_value or 1.0)
        elif et == "drop_probability":
            p = float(r.effect_value or 0.0)
            state["drop_probability"] = 1.0 - ((1.0 - float(state.get("drop_probability", 0.0))) * (1.0 - p))
        elif et == "latency_shift_ms":
            state["latency_shift_ms"] = int(state.get("latency_shift_ms", 0) or 0) + int(float(r.effect_value or 0))
        elif et == "suppress_input":
            state["suppress_input"] = bool(r.effect_value)
        elif et == "weather_type":
            state["weather_type"] = str(payload.get("weather_type") or r.effect_value or "clear")
        elif et == "campaign_flag":
            state["campaign_flag"] = str(payload.get("campaign_flag") or r.effect_value or "none")
        elif et == "system_flag":
            state["system_flag"] = str(payload.get("system_flag") or r.effect_value or "normal")
        elif et in {"anomaly_type", "schema_version", "schema_flag", "identity_flag", "pcid_stability", "session_stability", "customer_id_stability", "traffic_actor", "bot_flag", "user_agent_flag", "ip_concentration_flag", "recovery_flag", "backlog_flush", "privacy_flag", "pii_detected", "sensitive_field_flag", "masking_status"}:
            state[et] = str(payload.get(et) or r.effect_value or state.get(et) or "none")
        elif et in {"transaction_delay_ms", "event_ingestion_delay_ms", "event_time_skew_ms"}:
            state[et] = int(float(payload.get(et) if payload.get(et) is not None else (r.effect_value or 0)))
        elif et == "duplicate_multiplier":
            state[et] = float(state.get(et, 1.0)) * float(r.effect_value or payload.get(et) or 1.0)
    if state["suppress_input"]:
        state["volume_multiplier"] = 0.0
    return state



def state_is_affected(state: dict[str, Any]) -> bool:
    return (
        state.get("weather_type", "clear") != "clear"
        or state.get("campaign_flag", "none") != "none"
        or state.get("system_flag", "normal") != "normal"
        or float(state.get("volume_multiplier", 1.0)) != 1.0
        or float(state.get("conversion_multiplier", 1.0)) != 1.0
        or float(state.get("timeout_multiplier", 1.0)) != 1.0
        or float(state.get("retry_multiplier", 1.0)) != 1.0
        or float(state.get("drop_probability", 0.0)) != 0.0
        or int(state.get("latency_shift_ms", 0)) != 0
        or bool(state.get("suppress_input", False))
        or state.get("anomaly_type", "none") != "none"
        or state.get("schema_flag", "normal") != "normal"
        or state.get("identity_flag", "normal") != "normal"
        or state.get("traffic_actor", "human") != "human"
        or state.get("privacy_flag", "normal") != "normal"
        or float(state.get("duplicate_multiplier", 1.0)) != 1.0
        or int(state.get("event_time_skew_ms", 0)) != 0
    )


def parse_cookie_pairs(cookie: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for part in cookie.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        pairs[k.strip()] = v.strip()
    return pairs


def render_cookie_pairs(pairs: dict[str, str]) -> str:
    # Preserve the old style: key=value; key=value;
    return "; ".join(f"{k}={v}" for k, v in pairs.items()) + ";"


def update_cookie_with_state(cookie: str, state: dict[str, Any]) -> str:
    pairs = parse_cookie_pairs(cookie)
    # Keep legacy weather and explicit weather_type in sync.
    weather_type = str(state.get("weather_type") or "clear")
    campaign_flag = str(state.get("campaign_flag") or "none")
    system_flag = str(state.get("system_flag") or "normal")

    required = {
        "weather": weather_type,
        "weather_type": weather_type,
        "campaign_flag": campaign_flag,
        "system_flag": system_flag,
        "exo_source": "exogenous_timeline_v1" if state_is_affected(state) else "baseline",
    }
    for k, default_v in COOKIE_DEFAULTS.items():
        if k not in pairs:
            pairs[k] = default_v
    pairs.update(required)
    return render_cookie_pairs(pairs)


def rewrite_line_cookie_with_state(line: str, rules: list[TimelineRule]) -> tuple[str, bool]:
    ts = parse_log_ts(line)
    if ts is None:
        return line, False
    state = merge_rules_at(rules, ts)
    if not state_is_affected(state):
        # Normalize default cookie keys, but do not count as exogenous rewrite.
        m0 = COOKIE_FIELD_RE.search(line.rstrip("\n"))
        if not m0:
            return line, False
        old_cookie0 = m0.group("cookie")
        new_cookie0 = update_cookie_with_state(old_cookie0, state)
        if new_cookie0 == old_cookie0:
            return line, False
        newline = "\n" if line.endswith("\n") else ""
        raw = line.rstrip("\n")
        return raw[:m0.start("cookie")] + new_cookie0 + raw[m0.end("cookie"):] + newline, False

    m = COOKIE_FIELD_RE.search(line.rstrip("\n"))
    if not m:
        return line, False
    old_cookie = m.group("cookie")
    new_cookie = update_cookie_with_state(old_cookie, state)
    newline = "\n" if line.endswith("\n") else ""
    raw = line.rstrip("\n")
    new_line = raw[:m.start("cookie")] + new_cookie + raw[m.end("cookie"):] + newline
    return new_line, new_line != line


def rewrite_source_log_cookies(output_path: Path, rules: list[TimelineRule]) -> int:
    """Inject exogenous flags into the raw source cookie field.

    The downstream collector/batch/stream path parses anomaly context from the raw
    Apache cookie string. DB materialization alone is not enough; source files must
    carry weather/weather_type/campaign_flag/system_flag as first-class cookie keys.
    This post-generation rewrite keeps simulator internals stable while making the
    source file itself the source-level injection contract.
    """
    if not rules or not output_path.exists():
        return 0
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    changed = 0
    with output_path.open("r", encoding="utf-8", errors="replace") as src, tmp.open("w", encoding="utf-8") as dst:
        for line in src:
            new_line, did_change = rewrite_line_cookie_with_state(line, rules)
            if did_change:
                changed += 1
            dst.write(new_line)
    tmp.replace(output_path)
    print(f"[INFO] source cookie exogenous rewrite changed_lines={changed} output={output_path}")
    return changed


def materialize_compat_timeline(conn, profile_id: str, target_date: str, rules: list[TimelineRule]) -> None:
    exec_sql(conn, "DELETE FROM exogenous_state_timeline WHERE profile_id=%s AND dt=%s", (profile_id, target_date))
    rows = []
    base_dt = datetime.fromisoformat(f"{target_date}T00:00:00")
    for hh in range(24):
        st = merge_rules_at(rules, base_dt + timedelta(hours=hh))
        affected = state_is_affected(st)
        rows.append((
            profile_id,
            target_date,
            hh,
            st["weather_type"],
            st["campaign_flag"],
            st["system_flag"],
            st["volume_multiplier"],
            st["conversion_multiplier"],
            st["timeout_multiplier"],
            st["retry_multiplier"],
            st.get("drop_probability", 0.0),
            st.get("latency_shift_ms", 0),
            1 if st.get("suppress_input", False) else 0,
            "exogenous_timeline_v1" if affected else "baseline",
            st.get("anomaly_type", "none"),
            st.get("schema_version", "v0.4-source-anomaly-contract"),
            st.get("schema_flag", "normal"),
            st.get("identity_flag", "normal"),
            st.get("pcid_stability", "stable"),
            st.get("session_stability", "stable"),
            st.get("customer_id_stability", "stable"),
            st.get("traffic_actor", "human"),
            st.get("bot_flag", "0"),
            st.get("user_agent_flag", "normal"),
            st.get("ip_concentration_flag", "normal"),
            st.get("recovery_flag", "none"),
            st.get("backlog_flush", "0"),
            st.get("transaction_delay_ms", 0),
            st.get("event_ingestion_delay_ms", 0),
            st.get("privacy_flag", "normal"),
            st.get("pii_detected", "0"),
            st.get("sensitive_field_flag", "none"),
            st.get("masking_status", "masked"),
            st.get("duplicate_multiplier", 1.0),
            st.get("event_time_skew_ms", 0),
        ))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO exogenous_state_timeline
            (profile_id, dt, hh, weather_type, campaign_flag, system_flag,
             volume_multiplier, conversion_multiplier, timeout_multiplier, retry_multiplier,
             drop_probability, latency_shift_ms, suppress_input, source,
             anomaly_type, schema_version, schema_flag, identity_flag, pcid_stability, session_stability, customer_id_stability,
             traffic_actor, bot_flag, user_agent_flag, ip_concentration_flag, recovery_flag, backlog_flush,
             transaction_delay_ms, event_ingestion_delay_ms, privacy_flag, pii_detected, sensitive_field_flag, masking_status,
             duplicate_multiplier, event_time_skew_ms)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )
    conn.commit()


def sha256_file(path: Path) -> str:
    """Checksum source output bytes.

    The generator is now deterministic, so byte checksum must be stable for
    same seed + same timeline + same config.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_yaml(path: Optional[str]) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {"__missing__": str(path)}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def config_hash(args: argparse.Namespace, start: str, end: str, tl_hash: str) -> str:
    payload = {
        "profile_config": load_yaml(args.profile_config),
        "scenario_config": load_yaml(args.scenario_config),
        "target": {"start": start, "end": end, "avg_rps": args.avg_rps, "seed": args.seed},
        "simulator_version": args.simulator_version,
        "timeline_hash": tl_hash,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_source_generation_run(conn, args, target_date: str, scenario_id: str, cfg_hash: str) -> int:
    cols = table_columns(conn, "source_generation_run")
    values: dict[str, Any] = {
        "profile_id": args.profile_id,
        "target_date": target_date,
        "scenario_name": scenario_id,
        "scenario_mode": args.scenario_mode,
        "source_mode": args.source_mode,
        "exogenous_mode": "timeline_db_v1",
        "simulator_version": args.simulator_version,
        "generator_config_hash": cfg_hash,
        "status": "started",
        "created_by": args.created_by,
        "note": args.note,
    }
    insert_cols = [c for c in values if c in cols]
    if not insert_cols:
        raise RuntimeError("source_generation_run exists but none of the expected columns were found")
    placeholders = ",".join(["%s"] * len(insert_cols))
    sql = f"INSERT INTO source_generation_run ({','.join(insert_cols)}) VALUES ({placeholders})"
    exec_sql(conn, sql, tuple(values[c] for c in insert_cols))
    with conn.cursor() as cur:
        cur.execute("SELECT LAST_INSERT_ID() AS id")
        row = cur.fetchone()
    conn.commit()
    return int(row["id"])


def mark_run(conn, source_gen_run_id: int, status: str, note: str = "") -> None:
    cols = table_columns(conn, "source_generation_run")
    set_parts = []
    params: list[Any] = []
    if "status" in cols:
        set_parts.append("status=%s")
        params.append(status)
    if "ended_at" in cols:
        set_parts.append("ended_at=NOW()")
    if "finished_at" in cols:
        set_parts.append("finished_at=NOW()")
    if "note" in cols:
        set_parts.append("note=%s")
        params.append(note[:1000])
    if not set_parts:
        return
    params.append(source_gen_run_id)
    exec_sql(conn, f"UPDATE source_generation_run SET {', '.join(set_parts)} WHERE source_gen_run_id=%s", tuple(params))
    conn.commit()


def insert_file_manifest(conn, source_gen_run_id: int, profile_id: str, target_date: str, output: Path, checksum: str, row_count: int) -> None:
    cols = table_columns(conn, "source_file_manifest")
    values: dict[str, Any] = {
        "source_gen_run_id": source_gen_run_id,
        "exogenous_snapshot_id": None,
        "profile_id": profile_id,
        "target_date": target_date,
        "service_domain": "all",
        "file_path": str(output),
        "file_name": output.name,
        "file_size_bytes": output.stat().st_size,
        "checksum": checksum,
        "record_count": row_count,
    }
    insert_cols = [c for c in values if c in cols]
    if not insert_cols:
        print("[WARN] source_file_manifest has no compatible columns; skip manifest insert")
        return
    placeholders = ",".join(["%s"] * len(insert_cols))
    sql = f"INSERT INTO source_file_manifest ({','.join(insert_cols)}) VALUES ({placeholders})"
    exec_sql(conn, sql, tuple(values[c] for c in insert_cols))
    conn.commit()


def _build_timeline_profile(args, target_date: str, source_gen_run_id: int | None = None) -> Path:
    """Create a temporary profile YAML that explicitly enables timeline_db.

    The simulator CLI only receives --profile. Relying on environment override alone
    can silently fall back to the static exogenous block embedded in finance_bank.yaml.
    This helper makes the DB provider visible in the YAML itself and keeps env vars as
    a second safety net.
    """
    raw = load_yaml(args.profile_config)
    profile = dict(raw)
    scenario = dict(profile.get("scenario") or profile)
    exo = dict(scenario.get("exogenous") or {})
    exo.update({
        "enabled": True,
        "weather_source": "timeline_db",
        "use_timeline_db": True,
        "db_host": args.db_host,
        "db_port": int(args.db_port),
        "db_user": args.db_user,
        "db_password": args.db_pass,
        "db_name": args.db_name,
        "profile_id": args.profile_id,
        "target_date": target_date,
    })
    scenario["exogenous"] = exo
    if "scenario" in profile:
        profile["scenario"] = scenario
    else:
        profile.update(scenario)
    out_dir = Path(args.output_dir) / ".v04_profiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    scenario_id = args.scenario_id or args.scenario_name or "baseline"
    run_tag = str(source_gen_run_id or "norun")
    tmp_profile = out_dir / f"{args.profile_id}_{target_date}_{scenario_id}_{run_tag}_timeline_db.yaml"
    tmp_profile.write_text(yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return tmp_profile


def run_simulator(args, start: str, end: str, out: Path, target_date: str, source_gen_run_id: int | None = None) -> None:
    env = os.environ.copy()
    scenario_id = args.scenario_id or args.scenario_name or "baseline"
    tmp_profile = _build_timeline_profile(args, target_date, source_gen_run_id)
    env.update({
        "EXO_TIMELINE_ENABLED": "true",
        "EXO_DB_HOST": args.db_host,
        "EXO_DB_PORT": str(args.db_port),
        "EXO_DB_USER": args.db_user,
        "EXO_DB_PASSWORD": args.db_pass,
        "EXO_DB_NAME": args.db_name,
        "EXO_PROFILE_ID": args.profile_id,
        "EXO_TARGET_DATE": target_date,
        "SOURCE_SCENARIO_ID": scenario_id,
        "SOURCE_SCENARIO_NAME": args.scenario_name or scenario_id,
        "SOURCE_EXPERIMENT_ID": args.experiment_id or "none",
        "SOURCE_RUN_ID": str(source_gen_run_id or "none"),
    })
    cmd = [
        args.python_bin,
        "-m",
        args.simulator_cli_module,
        "--profile",
        str(tmp_profile),
        "--start",
        start,
        "--end",
        end,
        "--avg-rps",
        str(args.avg_rps),
        "--seed",
        str(args.seed),
        "--out",
        str(out),
    ]
    print("[INFO] simulator_profile=", tmp_profile)
    print("[INFO] exo_env=", json.dumps({
        "EXO_TIMELINE_ENABLED": env.get("EXO_TIMELINE_ENABLED"),
        "EXO_PROFILE_ID": env.get("EXO_PROFILE_ID"),
        "EXO_TARGET_DATE": env.get("EXO_TARGET_DATE"),
        "SOURCE_SCENARIO_ID": env.get("SOURCE_SCENARIO_ID"),
        "SOURCE_RUN_ID": env.get("SOURCE_RUN_ID"),
    }, ensure_ascii=False))
    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def parse_log_ts(line: str) -> Optional[datetime]:
    m = APACHE_TS_RE.search(line)
    if not m:
        return None
    return datetime.strptime(m.group("ts"), "%d/%b/%Y:%H:%M:%S")


def active_for_any_rule(rules: list[TimelineRule], ts: datetime) -> bool:
    return any(r.start_ts <= ts < r.end_ts for r in rules)


def summarize_output(path: Path, rules: list[TimelineRule]) -> tuple[int, int, Optional[datetime], Optional[datetime]]:
    row_count = 0
    affected = 0
    min_ts = None
    max_ts = None
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            row_count += 1
            ts = parse_log_ts(line)
            if ts is None:
                continue
            min_ts = ts if min_ts is None else min(min_ts, ts)
            max_ts = ts if max_ts is None else max(max_ts, ts)
            if active_for_any_rule(rules, ts):
                affected += 1
    return row_count, affected, min_ts, max_ts


def write_summary(conn, args, experiment_id: str, scenario_id: str, target_date: str, source_gen_run_id: int, out: Path, rules: list[TimelineRule], start_at: datetime, finish_at: datetime, tl_hash: str, cfg_hash: str) -> None:
    checksum = sha256_file(out)
    row_count, affected_count, min_ts, max_ts = summarize_output(out, rules)
    exec_sql(conn, """
      REPLACE INTO source_generation_result_summary
      (experiment_id, scenario_id, profile_id, target_date, source_gen_run_id, source_file_path,
       simulator_version, deterministic_seed, timeline_hash, config_hash, output_file_checksum,
       row_count, affected_row_count, min_event_ts, max_event_ts, started_at, finished_at)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        experiment_id,
        scenario_id,
        args.profile_id,
        target_date,
        source_gen_run_id,
        str(out),
        args.simulator_version,
        args.seed,
        tl_hash,
        cfg_hash,
        checksum,
        row_count,
        affected_count,
        min_ts,
        max_ts,
        start_at,
        finish_at,
    ))
    exec_sql(conn, """
      INSERT INTO source_generation_result_history
      (experiment_id, scenario_id, profile_id, target_date, source_gen_run_id, source_file_path,
       simulator_version, deterministic_seed, timeline_hash, config_hash, output_file_checksum,
       row_count, affected_row_count, min_event_ts, max_event_ts, started_at, finished_at)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        experiment_id,
        scenario_id,
        args.profile_id,
        target_date,
        source_gen_run_id,
        str(out),
        args.simulator_version,
        args.seed,
        tl_hash,
        cfg_hash,
        checksum,
        row_count,
        affected_count,
        min_ts,
        max_ts,
        start_at,
        finish_at,
    ))
    insert_file_manifest(conn, source_gen_run_id, args.profile_id, target_date, out, checksum, row_count)
    conn.commit()
    write_verification_snapshot(conn, args, scenario_id, target_date, out, row_count, affected_count)




def drift_counts(path: Path) -> tuple[int, int, int]:
    drift_on = 0
    drift_off = 0
    weather_alias = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "drift=on" in line:
                drift_on += 1
            if "drift=off" in line:
                drift_off += 1
            if "weather=" in line:
                weather_alias += 1
    return drift_on, drift_off, weather_alias


def write_verification_snapshot(conn, args, scenario_id: str, target_date: str, out: Path, row_count: int, affected_count: int) -> None:
    row = fetch_one(conn, """
      SELECT COUNT(*) AS cnt
      FROM source_generation_result_history
      WHERE profile_id=%s AND target_date=%s AND scenario_id=%s
    """, (args.profile_id, target_date, scenario_id))
    run_count = int(row["cnt"] if row else 0)
    row = fetch_one(conn, """
      SELECT COUNT(DISTINCT output_file_checksum) AS cnt
      FROM source_generation_result_history
      WHERE profile_id=%s AND target_date=%s AND scenario_id=%s
    """, (args.profile_id, target_date, scenario_id))
    checksum_count = int(row["cnt"] if row else 0)
    row = fetch_one(conn, """
      SELECT COUNT(*) AS cnt
      FROM exogenous_state_timeline
      WHERE profile_id=%s AND dt=%s
    """, (args.profile_id, target_date))
    timeline_rows = int(row["cnt"] if row else 0)
    drift_on, drift_off, weather_alias = drift_counts(out)

    status = "PASS"
    reasons = []
    if weather_alias != 0:
        status = "FAIL"; reasons.append("weather_alias_present")
    if scenario_id == "baseline":
        if drift_on != 0 or drift_off == 0:
            status = "FAIL"; reasons.append("baseline_drift_contract_failed")
    else:
        # source_no_data may have affected_rows=0 because suppressed events do not exist; timeline proves the gap.
        if scenario_id != "source_no_data" and drift_on == 0:
            status = "FAIL"; reasons.append("scenario_drift_on_missing")
    if run_count >= 2 and checksum_count != 1:
        status = "FAIL"; reasons.append("deterministic_checksum_failed")

    details = {
        "run_count": run_count,
        "drift_on": drift_on,
        "drift_off": drift_off,
        "weather_alias": weather_alias,
        "reasons": reasons,
    }
    exec_sql(conn, """
      INSERT INTO verification_snapshot_v1
      (profile_id, target_date, scenario_id, source_rows, affected_rows, timeline_rows, checksum_count, validation_status, details_json)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        args.profile_id, target_date, scenario_id, row_count, affected_count, timeline_rows,
        checksum_count, status, json.dumps(details, ensure_ascii=False),
    ))
    conn.commit()

def main() -> None:
    args = parse_args()
    target_date, start, end = derive_dates(args)
    scenario_id = args.scenario_id or args.scenario_name
    experiment_id = args.experiment_id or f"exp_{target_date}_{scenario_id}_{args.profile_id}"
    out = output_path(args, target_date, start, end)

    conn = connect(args)
    source_gen_run_id = None
    try:
        ensure_phase1_tables(conn)
        seed_scenario_catalog(conn)
        if bool_arg(args.auto_seed_timeline):
            ensure_default_timeline(conn, args, experiment_id, scenario_id, target_date, args.seed)
        rules = load_rules(conn, experiment_id, args.profile_id, target_date, scenario_id)
        if scenario_id in SOURCE_SCENARIOS and not rules:
            raise RuntimeError(f"No exogenous_timeline_v1 rows found for {experiment_id}/{args.profile_id}/{target_date}/{scenario_id}")
        materialize_compat_timeline(conn, args.profile_id, target_date, rules)

        tl_hash = timeline_hash(rules)
        cfg_hash = config_hash(args, start, end, tl_hash)
        source_gen_run_id = create_source_generation_run(conn, args, target_date, scenario_id, cfg_hash)

        if args.source_mode == "simulator_file_generate":
            if out.exists():
                out.unlink()
            started = datetime.now()
            run_simulator(args, start, end, out, target_date, source_gen_run_id)
            finished = datetime.now()
        elif args.source_mode in {"existing_file_reuse", "external_collected_file"}:
            if not out.exists():
                raise FileNotFoundError(f"source file not found: {out}")
            started = finished = datetime.now()
        else:
            raise ValueError(f"Unsupported --source-mode: {args.source_mode}")

        if not out.exists():
            raise RuntimeError(f"Simulator finished but output file was not created: {out}")
        write_summary(conn, args, experiment_id, scenario_id, target_date, source_gen_run_id, out, rules, started, finished, tl_hash, cfg_hash)
        mark_run(conn, source_gen_run_id, "completed", args.note)
        print(json.dumps({
            "ok": True,
            "source_gen_run_id": source_gen_run_id,
            "experiment_id": experiment_id,
            "scenario_id": scenario_id,
            "target_date": target_date,
            "output": str(out),
            "timeline_hash": tl_hash,
            "config_hash": cfg_hash,
        }, ensure_ascii=False, indent=2))
    except Exception as exc:
        if source_gen_run_id is not None:
            mark_run(conn, source_gen_run_id, "failed", str(exc))
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
