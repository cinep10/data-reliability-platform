from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


V04_COOKIE_SCHEMA_VERSION = "v0.4-source-anomaly-contract"
DEFAULT_ANOMALY_CONTRACT_ID = "contract_web_source_v04"


@dataclass(frozen=True)
class SourceCookieContext:
    scenario_id: str = "baseline"
    scenario_name: str = "baseline"
    domain: str = "web"
    source_layer: str = "behavior"
    anomaly_type: str = "none"
    exo_state_id: str = "none"
    anomaly_contract_id: str = DEFAULT_ANOMALY_CONTRACT_ID
    experiment_id: str = "none"
    run_id: str = "none"


def normalize_value(value: Any, default: str = "none") -> str:
    if value is None:
        return default
    s = str(value).strip()
    if s == "":
        return default
    return s.replace(";", "_").replace("\n", "_").replace("\r", "_").replace(" ", "_")


def _non_default(exo_state: Any) -> bool:
    if exo_state is None:
        return False
    if bool(getattr(exo_state, "suppress_input", False)):
        return True
    checks = [
        normalize_value(getattr(exo_state, "weather_type", "clear"), "clear") != "clear",
        normalize_value(getattr(exo_state, "campaign_flag", "none"), "none") != "none",
        normalize_value(getattr(exo_state, "system_flag", "normal"), "normal") != "normal",
        normalize_value(getattr(exo_state, "schema_flag", "normal"), "normal") != "normal",
        normalize_value(getattr(exo_state, "identity_flag", "normal"), "normal") != "normal",
        normalize_value(getattr(exo_state, "traffic_actor", "human"), "human") != "human",
        normalize_value(getattr(exo_state, "privacy_flag", "normal"), "normal") != "normal",
        normalize_value(getattr(exo_state, "recovery_flag", "none"), "none") != "none",
        float(getattr(exo_state, "volume_multiplier", 1.0) or 1.0) != 1.0,
        float(getattr(exo_state, "conversion_multiplier", 1.0) or 1.0) != 1.0,
        float(getattr(exo_state, "timeout_multiplier", 1.0) or 1.0) != 1.0,
        float(getattr(exo_state, "retry_multiplier", 1.0) or 1.0) != 1.0,
        float(getattr(exo_state, "drop_probability", 0.0) or 0.0) != 0.0,
        int(getattr(exo_state, "latency_shift_ms", 0) or 0) != 0,
        float(getattr(exo_state, "duplicate_multiplier", 1.0) or 1.0) != 1.0,
        int(getattr(exo_state, "event_time_skew_ms", 0) or 0) != 0,
    ]
    return any(checks)


def is_exogenous_affected(exo_state: Any) -> bool:
    return bool(getattr(exo_state, "affected", False)) or _non_default(exo_state)


def infer_anomaly_type(exo_state: Any, scenario_id: str = "baseline") -> str:
    sid = normalize_value(scenario_id, "baseline")
    explicit = normalize_value(getattr(exo_state, "anomaly_type", "none"), "none") if exo_state else "none"
    if sid == "baseline" or exo_state is None or not is_exogenous_affected(exo_state):
        return "none"
    if explicit != "none":
        return explicit
    mapping = {
        "source_weather_drop": "weather_drop",
        "source_campaign_spike": "campaign_spike",
        "source_system_degraded": "system_degraded",
        "source_no_data": "no_data",
        "source_partial_missing": "partial_missing",
        "source_latency_degradation": "latency_degradation",
        "source_identity_drift": "identity_drift",
        "source_schema_drift": "schema_drift",
        "source_duplicate_burst": "duplicate_burst",
        "source_ordering_shuffle": "ordering_shuffle",
        "source_bot_spike": "bot_spike",
        "source_recovery_after_outage": "recovery_after_outage",
        "source_sensitive_field_exposure": "sensitive_field_exposure",
    }
    return mapping.get(sid, sid)


def build_source_cookie_kv(*, base_fields: Dict[str, Any], exo_state: Any, context: Optional[SourceCookieContext] = None) -> str:
    ctx = context or SourceCookieContext()
    affected = is_exogenous_affected(exo_state)
    drift = "on" if affected else "off"
    anomaly_type = infer_anomaly_type(exo_state, ctx.scenario_id)
    exo_source = normalize_value(getattr(exo_state, "source", "baseline"), "baseline")
    if not affected:
        exo_source = "baseline"

    schema_version = normalize_value(getattr(exo_state, "schema_version", V04_COOKIE_SCHEMA_VERSION), V04_COOKIE_SCHEMA_VERSION)
    if normalize_value(getattr(exo_state, "schema_flag", "normal"), "normal") != "normal":
        schema_version = f"{V04_COOKIE_SCHEMA_VERSION}-drifted"

    ordered: list[tuple[str, Any]] = []
    for k in ["cc", "al", "channel", "device", "pcid", "sid", "uid", "evt", "event_type", "page_type", "product_type", "latency_ms", "http_status"]:
        if k in base_fields:
            ordered.append((k, base_fields[k]))

    ordered.extend([
        ("schema_version", schema_version),
        ("scenario_id", ctx.scenario_id),
        ("scenario_name", ctx.scenario_name),
        ("domain", ctx.domain),
        ("source_layer", ctx.source_layer),
        ("anomaly_type", anomaly_type),
        ("drift", drift),
        ("affected", "1" if affected else "0"),
        ("exo_state_id", ctx.exo_state_id),
        ("anomaly_contract_id", ctx.anomaly_contract_id),
        ("experiment_id", ctx.experiment_id),
        ("run_id", ctx.run_id),
        ("exo_source", exo_source),
        ("weather_type", getattr(exo_state, "weather_type", "clear") if exo_state else "clear"),
        ("campaign_flag", getattr(exo_state, "campaign_flag", "none") if exo_state else "none"),
        ("system_flag", getattr(exo_state, "system_flag", "normal") if exo_state else "normal"),
        ("volume_multiplier", getattr(exo_state, "volume_multiplier", 1.0) if exo_state else 1.0),
        ("conversion_multiplier", getattr(exo_state, "conversion_multiplier", 1.0) if exo_state else 1.0),
        ("latency_shift_ms", getattr(exo_state, "latency_shift_ms", 0) if exo_state else 0),
        ("drop_probability", getattr(exo_state, "drop_probability", 0.0) if exo_state else 0.0),
        ("timeout_multiplier", getattr(exo_state, "timeout_multiplier", 1.0) if exo_state else 1.0),
        ("retry_multiplier", getattr(exo_state, "retry_multiplier", 1.0) if exo_state else 1.0),
        ("duplicate_multiplier", getattr(exo_state, "duplicate_multiplier", 1.0) if exo_state else 1.0),
        ("event_time_skew_ms", getattr(exo_state, "event_time_skew_ms", 0) if exo_state else 0),
        ("suppress_input", "1" if bool(getattr(exo_state, "suppress_input", False)) else "0"),
        ("schema_flag", getattr(exo_state, "schema_flag", "normal") if exo_state else "normal"),
        ("identity_flag", getattr(exo_state, "identity_flag", "normal") if exo_state else "normal"),
        ("pcid_stability", getattr(exo_state, "pcid_stability", "stable") if exo_state else "stable"),
        ("session_stability", getattr(exo_state, "session_stability", "stable") if exo_state else "stable"),
        ("customer_id_stability", getattr(exo_state, "customer_id_stability", "stable") if exo_state else "stable"),
        ("traffic_actor", getattr(exo_state, "traffic_actor", "human") if exo_state else "human"),
        ("bot_flag", getattr(exo_state, "bot_flag", "0") if exo_state else "0"),
        ("user_agent_flag", getattr(exo_state, "user_agent_flag", "normal") if exo_state else "normal"),
        ("ip_concentration_flag", getattr(exo_state, "ip_concentration_flag", "normal") if exo_state else "normal"),
        ("recovery_flag", getattr(exo_state, "recovery_flag", "none") if exo_state else "none"),
        ("backlog_flush", getattr(exo_state, "backlog_flush", "0") if exo_state else "0"),
        ("transaction_delay_ms", getattr(exo_state, "transaction_delay_ms", 0) if exo_state else 0),
        ("event_ingestion_delay_ms", getattr(exo_state, "event_ingestion_delay_ms", 0) if exo_state else 0),
        ("privacy_flag", getattr(exo_state, "privacy_flag", "normal") if exo_state else "normal"),
        ("pii_detected", getattr(exo_state, "pii_detected", "0") if exo_state else "0"),
        ("sensitive_field_flag", getattr(exo_state, "sensitive_field_flag", "none") if exo_state else "none"),
        ("masking_status", getattr(exo_state, "masking_status", "masked") if exo_state else "masked"),
        ("financial_product", normalize_value(base_fields.get("product_type"), "none")),
        ("funnel_stage", normalize_value(base_fields.get("page_type"), "none")),
        ("state_transition", "none"),
        ("expected_state", "none"),
        ("actual_state", "none"),
        ("amount_expected", "0"),
        ("amount_actual", "0"),
        ("amount_delta", "0"),
        ("approval_result", "none"),
        ("execution_result", "none"),
        ("account_status", "none"),
        ("ledger_status", "none"),
        ("balance_delta", "0"),
        ("reconciliation_flag", "none"),
    ])
    return " ".join(f"{k}={normalize_value(v)};" for k, v in ordered)
