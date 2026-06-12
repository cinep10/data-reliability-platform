from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

import pymysql

from .exogenous import ExogenousConfig, ExogenousState


class WeatherProvider:
    def get_state(self, when: datetime) -> ExogenousState:
        raise NotImplementedError


class StaticWeatherProvider(WeatherProvider):
    def __init__(self, cfg: ExogenousConfig):
        self.cfg = cfg

    def get_state(self, when: datetime) -> ExogenousState:
        return self.cfg.resolve_static(when)


class FileWeatherProvider(WeatherProvider):
    def __init__(self, cfg: ExogenousConfig):
        self.cfg = cfg
        self.rows: dict[tuple[str, int], dict] = {}
        if cfg.weather_file and Path(cfg.weather_file).exists():
            with open(cfg.weather_file, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    dt = row.get("dt") or row.get("date")
                    hh = int(row.get("hh") or row.get("hour") or 0)
                    self.rows[(str(dt), hh)] = row

    def get_state(self, when: datetime) -> ExogenousState:
        row = self.rows.get((when.strftime("%Y-%m-%d"), int(when.hour)))
        if not row:
            return self.cfg.resolve_static(when)
        return _state_from_row(row, when)


class ApiWeatherProvider(WeatherProvider):
    def __init__(self, cfg: ExogenousConfig):
        self.cfg = cfg

    def get_state(self, when: datetime) -> ExogenousState:
        return self.cfg.resolve_static(when)


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "0").strip().lower() in {"1", "true", "yes", "y", "on"}


def _to_float(row: dict, k: str, default: float) -> float:
    try:
        return float(row.get(k) if row.get(k) is not None else default)
    except Exception:
        return default


def _to_int(row: dict, k: str, default: int) -> int:
    try:
        return int(float(row.get(k) if row.get(k) is not None else default))
    except Exception:
        return default


def _to_str(row: dict, k: str, default: str) -> str:
    v = row.get(k)
    if v is None or str(v).strip() == "":
        return default
    return str(v)


def _state_from_row(row: dict, when: datetime) -> ExogenousState:
    affected = _is_affected(row)
    return ExogenousState(
        enabled=True,
        weather_type=_to_str(row, "weather_type", "clear"),
        campaign_flag=_to_str(row, "campaign_flag", "none"),
        system_flag=_to_str(row, "system_flag", "normal"),
        volume_multiplier=_to_float(row, "volume_multiplier", 1.0),
        conversion_multiplier=_to_float(row, "conversion_multiplier", 1.0),
        timeout_multiplier=_to_float(row, "timeout_multiplier", 1.0),
        retry_multiplier=_to_float(row, "retry_multiplier", 1.0),
        drop_probability=_to_float(row, "drop_probability", 0.0),
        latency_shift_ms=_to_int(row, "latency_shift_ms", 0),
        suppress_input=_to_bool(row.get("suppress_input")),
        anomaly_type=_to_str(row, "anomaly_type", "none"),
        schema_version=_to_str(row, "schema_version", "v0.4-source-anomaly-contract"),
        schema_flag=_to_str(row, "schema_flag", "normal"),
        identity_flag=_to_str(row, "identity_flag", "normal"),
        pcid_stability=_to_str(row, "pcid_stability", "stable"),
        session_stability=_to_str(row, "session_stability", "stable"),
        customer_id_stability=_to_str(row, "customer_id_stability", "stable"),
        traffic_actor=_to_str(row, "traffic_actor", "human"),
        bot_flag=_to_str(row, "bot_flag", "0"),
        user_agent_flag=_to_str(row, "user_agent_flag", "normal"),
        ip_concentration_flag=_to_str(row, "ip_concentration_flag", "normal"),
        recovery_flag=_to_str(row, "recovery_flag", "none"),
        backlog_flush=_to_str(row, "backlog_flush", "0"),
        transaction_delay_ms=_to_int(row, "transaction_delay_ms", 0),
        event_ingestion_delay_ms=_to_int(row, "event_ingestion_delay_ms", 0),
        privacy_flag=_to_str(row, "privacy_flag", "normal"),
        pii_detected=_to_str(row, "pii_detected", "0"),
        sensitive_field_flag=_to_str(row, "sensitive_field_flag", "none"),
        masking_status=_to_str(row, "masking_status", "masked"),
        duplicate_multiplier=_to_float(row, "duplicate_multiplier", 1.0),
        event_time_skew_ms=_to_int(row, "event_time_skew_ms", 0),
        affected=affected,
        source="exogenous_timeline_v1" if affected else "baseline",
        as_of=when,
    )


def _is_affected(row: dict) -> bool:
    return (
        _to_str(row, "weather_type", "clear") != "clear"
        or _to_str(row, "campaign_flag", "none") != "none"
        or _to_str(row, "system_flag", "normal") != "normal"
        or _to_str(row, "schema_flag", "normal") != "normal"
        or _to_str(row, "identity_flag", "normal") != "normal"
        or _to_str(row, "traffic_actor", "human") != "human"
        or _to_str(row, "privacy_flag", "normal") != "normal"
        or _to_float(row, "volume_multiplier", 1.0) != 1.0
        or _to_float(row, "conversion_multiplier", 1.0) != 1.0
        or _to_float(row, "timeout_multiplier", 1.0) != 1.0
        or _to_float(row, "retry_multiplier", 1.0) != 1.0
        or _to_float(row, "drop_probability", 0.0) != 0.0
        or _to_int(row, "latency_shift_ms", 0) != 0
        or _to_bool(row.get("suppress_input"))
        or _to_float(row, "duplicate_multiplier", 1.0) != 1.0
        or _to_int(row, "event_time_skew_ms", 0) != 0
    )


class TimelineDbProviderV2(WeatherProvider):
    """Cached DB provider for v0.4 source generation.

    The generator reads materialized state once from exogenous_state_timeline and
    emits source anomaly cookies directly. run_source_generation_v2 only seeds and
    materializes DB timeline; it does not rewrite source files.
    """

    def __init__(self, cfg: ExogenousConfig):
        self.cfg = cfg
        self.cache: dict[tuple[str, int], ExogenousState] = {}
        self.conn = pymysql.connect(
            host=cfg.db_host,
            port=int(cfg.db_port),
            user=cfg.db_user,
            password=cfg.db_password,
            database=cfg.db_name,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )
        self._preload()

    def _preload(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM exogenous_state_timeline
                WHERE profile_id=%s
                  AND (%s = '' OR dt = %s)
                """,
                (self.cfg.profile_id, getattr(self.cfg, "target_date", "") or os.getenv("EXO_TARGET_DATE", ""), getattr(self.cfg, "target_date", "") or os.getenv("EXO_TARGET_DATE", "")),
            )
            rows = list(cur.fetchall())
        affected_hours = 0
        for row in rows:
            dt_value = row["dt"].isoformat() if hasattr(row.get("dt"), "isoformat") else str(row.get("dt"))
            hh = int(row["hh"])
            state = _state_from_row(row, datetime.fromisoformat(f"{dt_value}T{hh:02d}:00:00"))
            affected_hours += 1 if state.affected else 0
            self.cache[(dt_value, hh)] = state
        print(f"[EXO_PROVIDER] timeline_db profile={self.cfg.profile_id} target_date={getattr(self.cfg, 'target_date', '') or os.getenv('EXO_TARGET_DATE', '')} rows={len(rows)} affected_hours={affected_hours}", flush=True)

    def get_state(self, when: datetime) -> ExogenousState:
        key = (when.strftime("%Y-%m-%d"), int(when.hour))
        state = self.cache.get(key)
        if state is None:
            return ExogenousState.baseline(when)
        return ExogenousState(**{**state.__dict__, "as_of": when})


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _cfg_from_env(cfg: ExogenousConfig) -> ExogenousConfig:
    exo = ExogenousConfig(**cfg.__dict__)
    if _bool_env("EXO_TIMELINE_ENABLED", False):
        exo.enabled = True
        exo.use_timeline_db = True
        exo.weather_source = "timeline_db"
        exo.db_host = os.getenv("EXO_DB_HOST", exo.db_host or "127.0.0.1")
        exo.db_port = int(os.getenv("EXO_DB_PORT", str(exo.db_port or 3306)))
        exo.db_user = os.getenv("EXO_DB_USER", exo.db_user or "")
        exo.db_password = os.getenv("EXO_DB_PASSWORD", exo.db_password or "")
        exo.db_name = os.getenv("EXO_DB_NAME", exo.db_name or "")
        exo.profile_id = os.getenv("EXO_PROFILE_ID", exo.profile_id or "")
        exo.target_date = os.getenv("EXO_TARGET_DATE", getattr(exo, "target_date", "") or "")
    return exo


def build_weather_provider(cfg: Optional[ExogenousConfig]) -> WeatherProvider:
    if cfg is None:
        cfg = ExogenousConfig(enabled=False)
    cfg = _cfg_from_env(cfg)
    source = (cfg.weather_source or "static").lower()
    if source == "timeline_db" or getattr(cfg, "use_timeline_db", False):
        if all([cfg.db_host, cfg.db_user, cfg.db_name, cfg.profile_id]):
            return TimelineDbProviderV2(cfg)
    if source == "file":
        return FileWeatherProvider(cfg)
    if source == "api":
        return ApiWeatherProvider(cfg)
    return StaticWeatherProvider(cfg)
