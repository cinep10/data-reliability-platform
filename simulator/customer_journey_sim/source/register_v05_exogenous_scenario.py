from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pymysql

SOURCE_SCENARIOS = {
    "baseline": [],
    "source_campaign_spike": [
        ("volume_multiplier", 3.0, None, 10),
        ("conversion_multiplier", 1.2, None, 20),
        ("campaign_flag", None, {"campaign_flag": "commerce_promo"}, 30),
    ],
    "source_weather_drop": [
        ("volume_multiplier", 0.6, None, 10),
        ("conversion_multiplier", 0.5, None, 20),
        ("timeout_multiplier", 1.15, None, 30),
        ("latency_shift_ms", 200.0, None, 35),
        ("weather_type", None, {"weather_type": "rain"}, 40),
    ],
    "source_system_degraded": [
        ("timeout_multiplier", 2.0, None, 10),
        ("retry_multiplier", 3.0, None, 20),
        ("latency_shift_ms", 500.0, None, 5),
        ("system_flag", None, {"system_flag": "degraded"}, 30),
    ],
    "source_no_data": [
        ("suppress_input", 1.0, None, 10),
        ("anomaly_type", None, {"anomaly_type": "no_data"}, 20),
    ],
    "source_partial_missing": [
        ("drop_probability", 0.20, None, 10),
        ("anomaly_type", None, {"anomaly_type": "partial_missing"}, 20),
    ],
    "source_latency_degradation": [
        ("latency_shift_ms", 900.0, None, 10),
        ("timeout_multiplier", 1.20, None, 20),
        ("anomaly_type", None, {"anomaly_type": "latency_degradation"}, 30),
    ],
    "source_identity_drift": [
        ("identity_flag", None, {"identity_flag": "drift"}, 10),
        ("pcid_stability", None, {"pcid_stability": "unstable"}, 20),
        ("session_stability", None, {"session_stability": "unstable"}, 30),
        ("customer_id_stability", None, {"customer_id_stability": "unstable"}, 40),
        ("anomaly_type", None, {"anomaly_type": "identity_drift"}, 50),
    ],
    "source_schema_drift": [
        ("schema_flag", None, {"schema_flag": "drift"}, 10),
        ("schema_version", None, {"schema_version": "v05-source-anomaly-contract-drifted"}, 20),
        ("anomaly_type", None, {"anomaly_type": "schema_drift"}, 30),
    ],
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Register v0.5 exogenous scenario provenance before journey source generation.")
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", default="baseline")
    p.add_argument("--scenario-id")
    p.add_argument("--experiment-id")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--replace-timeline", action="store_true")
    p.add_argument("--window-start", default="10:00:00")
    p.add_argument("--window-end", default="12:00:00")
    p.add_argument("--profile-config")
    p.add_argument("--scenario-config")
    p.add_argument("--exogenous-config")
    p.add_argument("--snapshot-out")
    return p.parse_args()


def connect(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def exec_sql(conn, sql: str, params: Any = None) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params)


def sha_optional(path_value: Optional[str]) -> Optional[str]:
    if not path_value:
        return None
    p = Path(path_value)
    h = hashlib.sha256()
    if not p.exists():
        h.update(json.dumps({"missing_path": path_value}, sort_keys=True).encode("utf-8"))
        return h.hexdigest()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_tables(conn) -> None:
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
    CREATE TABLE IF NOT EXISTS v05_exogenous_registration_snapshot (
      snapshot_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      experiment_id VARCHAR(100) NOT NULL,
      profile_id VARCHAR(100) NOT NULL,
      target_date DATE NOT NULL,
      scenario_id VARCHAR(100) NOT NULL,
      timeline_rows INT NOT NULL DEFAULT 0,
      timeline_hash VARCHAR(128) NOT NULL,
      profile_config_hash VARCHAR(128) NULL,
      scenario_config_hash VARCHAR(128) NULL,
      exogenous_config_hash VARCHAR(128) NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      KEY idx_v05_exo_snapshot_lookup (profile_id, target_date, scenario_id, experiment_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    conn.commit()


def seed_catalog(conn, scenario_id: str) -> None:
    descriptions = {
        "baseline": ("Baseline", "normal source timeline", "no_anomaly", "low"),
        "source_campaign_spike": ("Source Campaign Spike", "campaign traffic spike", "row_count_up", "source_volume"),
        "source_weather_drop": ("Source Weather Drop", "weather-driven conversion/latency shift", "conversion_down_latency_up", "source_quality"),
        "source_system_degraded": ("Source System Degraded", "timeout/retry/latency increase", "timeout_retry_latency_up", "performance_availability"),
        "source_no_data": ("Source No Data", "source log gap", "row_gap", "availability"),
        "source_partial_missing": ("Source Partial Missing", "partial source event loss", "drop_probability_up", "source_completeness"),
        "source_latency_degradation": ("Source Latency Degradation", "source latency degradation", "latency_shift_up", "source_timeliness"),
        "source_identity_drift": ("Source Identity Drift", "pcid/session/customer stability drift", "identity_flag_drift", "identity_reliability"),
        "source_schema_drift": ("Source Schema Drift", "schema version/flag drift", "schema_flag_drift", "schema_reliability"),
    }
    name, desc, signal, risk = descriptions.get(scenario_id, (scenario_id, "custom v0.5 source scenario", "custom", "unknown"))
    exec_sql(conn, """
    INSERT INTO source_scenario_catalog
      (scenario_id, scenario_name, description, expected_signal, expected_risk_layer)
    VALUES (%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      scenario_name=VALUES(scenario_name), description=VALUES(description),
      expected_signal=VALUES(expected_signal), expected_risk_layer=VALUES(expected_risk_layer), updated_at=NOW()
    """, (scenario_id, name, desc, signal, risk))


def timeline_hash(rows: list[dict[str, Any]]) -> str:
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> int:
    a = parse_args()
    scenario_id = a.scenario_id or a.scenario_name
    experiment_id = a.experiment_id or f"v05_{a.profile_id}_{a.target_date}_{scenario_id}"
    rules = SOURCE_SCENARIOS.get(scenario_id, [])
    start_ts = f"{a.target_date} {a.window_start}"
    end_ts = f"{a.target_date} {a.window_end}"
    if scenario_id == "source_no_data" and a.window_end == "12:00:00":
        end_ts = f"{a.target_date} 11:00:00"

    conn = connect(a)
    try:
        ensure_tables(conn)
        seed_catalog(conn, scenario_id)
        if a.replace_timeline:
            exec_sql(conn, """
            DELETE FROM exogenous_timeline_v1
            WHERE experiment_id=%s AND profile_id=%s AND target_date=%s AND scenario_id=%s
            """, (experiment_id, a.profile_id, a.target_date, scenario_id))
        rows = []
        for effect_type, effect_value, payload, priority in rules:
            row = {
                "experiment_id": experiment_id,
                "profile_id": a.profile_id,
                "target_date": a.target_date,
                "scenario_id": scenario_id,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "entity_type": "global",
                "entity_id": "global",
                "effect_type": effect_type,
                "effect_value": effect_value,
                "effect_payload_json": payload,
                "priority": priority,
                "deterministic_seed": a.seed,
            }
            rows.append(row)
            exec_sql(conn, """
            INSERT INTO exogenous_timeline_v1
              (experiment_id, profile_id, target_date, scenario_id, start_ts, end_ts,
               entity_type, entity_id, effect_type, effect_value, effect_payload_json,
               priority, deterministic_seed)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                experiment_id, a.profile_id, a.target_date, scenario_id,
                datetime.fromisoformat(start_ts), datetime.fromisoformat(end_ts),
                "global", "global", effect_type, effect_value,
                json.dumps(payload, ensure_ascii=False) if payload else None,
                priority, a.seed,
            ))
        tl_hash = timeline_hash(rows)
        exec_sql(conn, """
        INSERT INTO v05_exogenous_registration_snapshot
          (experiment_id, profile_id, target_date, scenario_id, timeline_rows, timeline_hash,
           profile_config_hash, scenario_config_hash, exogenous_config_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            experiment_id, a.profile_id, a.target_date, scenario_id, len(rows), tl_hash,
            sha_optional(a.profile_config), sha_optional(a.scenario_config), sha_optional(a.exogenous_config),
        ))
        with conn.cursor() as cur:
            cur.execute("SELECT LAST_INSERT_ID() AS snapshot_id")
            snapshot_id = int(cur.fetchone()["snapshot_id"])
        conn.commit()
        result = {
            "ok": True,
            "snapshot_id": snapshot_id,
            "experiment_id": experiment_id,
            "profile_id": a.profile_id,
            "target_date": a.target_date,
            "scenario_id": scenario_id,
            "timeline_rows": len(rows),
            "timeline_hash": tl_hash,
        }
        if a.snapshot_out:
            Path(a.snapshot_out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.snapshot_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
