from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ExogenousState:
    """v0.4 Phase 1 source anomaly state.

    This is read by generator.py/traffic.py/http_model.py and rendered directly
    into the source access-log cookie. Normal pipeline must not rewrite the
    source file after generation.
    """
    enabled: bool = False

    weather_type: str = "clear"
    campaign_flag: str = "none"
    system_flag: str = "normal"

    volume_multiplier: float = 1.0
    conversion_multiplier: float = 1.0
    timeout_multiplier: float = 1.0
    retry_multiplier: float = 1.0

    drop_probability: float = 0.0
    latency_shift_ms: int = 0
    suppress_input: bool = False

    # v0.4 source anomaly contract extension fields.
    anomaly_type: str = "none"
    schema_version: str = "v0.4-source-anomaly-contract"
    schema_flag: str = "normal"
    identity_flag: str = "normal"
    pcid_stability: str = "stable"
    session_stability: str = "stable"
    customer_id_stability: str = "stable"
    traffic_actor: str = "human"
    bot_flag: str = "0"
    user_agent_flag: str = "normal"
    ip_concentration_flag: str = "normal"
    recovery_flag: str = "none"
    backlog_flush: str = "0"
    transaction_delay_ms: int = 0
    event_ingestion_delay_ms: int = 0
    privacy_flag: str = "normal"
    pii_detected: str = "0"
    sensitive_field_flag: str = "none"
    masking_status: str = "masked"
    duplicate_multiplier: float = 1.0
    event_time_skew_ms: int = 0

    affected: bool = False
    source: str = "baseline"
    as_of: Optional[datetime] = None

    @classmethod
    def baseline(cls, as_of: Optional[datetime] = None) -> "ExogenousState":
        return cls(enabled=False, affected=False, source="baseline", as_of=as_of)


@dataclass
class ExogenousConfig:
    enabled: bool = False
    weather_type: str = "clear"
    campaign_flag: str = "none"
    system_flag: str = "normal"
    weather_source: str = "static"
    weather_file: str = ""
    weather_api_base_url: str = ""
    weather_api_key: str = ""

    use_timeline_db: bool = False
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = ""
    db_password: str = ""
    db_name: str = ""
    profile_id: str = ""
    target_date: str = ""

    def resolve_static(self, when: Optional[datetime] = None) -> ExogenousState:
        affected = (
            bool(self.enabled)
            and (
                self.weather_type != "clear"
                or self.campaign_flag != "none"
                or self.system_flag != "normal"
            )
        )
        return ExogenousState(
            enabled=bool(self.enabled),
            weather_type=self.weather_type or "clear",
            campaign_flag=self.campaign_flag or "none",
            system_flag=self.system_flag or "normal",
            affected=affected,
            source="static" if affected else "baseline",
            anomaly_type="static" if affected else "none",
            as_of=when,
        )
