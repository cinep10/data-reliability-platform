from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any

from .randomutil import clamp
from .exogenous import ExogenousConfig


@dataclass
class PageSpec:
    path: str
    page_type: str
    weight: float


@dataclass
class TrafficCurveConfig:
    mode: str = "legacy_rps"
    hh_multiplier: List[float] = field(default_factory=lambda: [1.0] * 24)
    target_visit_per_hh: List[int] = field(default_factory=lambda: [0] * 24)
    smooth_window_min: int = 0


@dataclass
class ScenarioConfig:
    site_host: str
    pages: List[PageSpec]
    countries: List[Tuple[str, float]]
    accept_lang_by_country: Dict[str, List[Tuple[str, float]]]
    device_weights: List[Tuple[str, float]]
    uas_mobile: List[Tuple[str, float]]
    uas_desktop: List[Tuple[str, float]]
    event_mix_default: List[Tuple[str, float]]
    event_mix_by_page_type: Dict[str, List[Tuple[str, float]]]

    pcid_reuse: float = 0.82
    pcid_uid_stickiness: float = 0.96

    uid_rate: float = 0.08
    uid_acquire_half_life_sessions: int = 10
    uid_acquire_click_boost: float = 0.04
    uid_acquire_page_types: Tuple[str, ...] = ("home", "forecast", "warning", "now", "life")

    revisit_ratio_daily: float = 0.42
    new_visit_ratio_by_hh: List[float] = field(default_factory=lambda: [0.58] * 24)
    revisit_ratio_by_hh: List[float] = field(default_factory=lambda: [0.42] * 24)

    session_mean_sec: int = 320
    session_event_rate: float = 0.035
    session_event_rate_by_hh: List[float] = field(default_factory=lambda: [0.035] * 24)

    target_pv_per_visit_mean: float = 6.9
    target_pv_per_visit_std: float = 1.4
    max_pageviews_per_session: int = 16

    server_hit_ratio_by_event: Dict[str, float] = field(default_factory=lambda: {
        "view": 1.00,
        "click": 0.25,
        "scroll": 0.03,
        "swipe": 0.02,
    })

    traffic_curve: TrafficCurveConfig = field(default_factory=TrafficCurveConfig)
    weekday_multiplier: Dict[str, float] = field(default_factory=lambda: {
        "sun": 0.92,
        "mon": 1.02,
        "tue": 1.06,
        "wed": 1.10,
        "thu": 0.78,
        "fri": 0.90,
        "sat": 0.88,
    })
    exogenous: ExogenousConfig = field(default_factory=ExogenousConfig)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ScenarioConfig":
        pages = [PageSpec(**p) for p in d["pages"]]
        tc_raw = d.get("traffic_curve", {}) or {}
        traffic_curve = TrafficCurveConfig(
            mode=str(tc_raw.get("mode", "legacy_rps")),
            hh_multiplier=list(tc_raw.get("hh_multiplier", [1.0] * 24)),
            target_visit_per_hh=list(tc_raw.get("target_visit_per_hh", [0] * 24)),
            smooth_window_min=int(tc_raw.get("smooth_window_min", 0)),
        )
        exo_raw = d.get("exogenous", {}) or {}
        exogenous = ExogenousConfig(
            enabled=bool(exo_raw.get("enabled", False)),
            weather_type=str(exo_raw.get("weather_type", "clear")),
            campaign_flag=str(exo_raw.get("campaign_flag", "none")),
            system_flag=str(exo_raw.get("system_flag", "normal")),
            weather_source=str(exo_raw.get("weather_source", "static")),
            weather_file=str(exo_raw.get("weather_file", "")),
            weather_api_base_url=str(exo_raw.get("weather_api_base_url", "")),
            weather_api_key=str(exo_raw.get("weather_api_key", "")),
            use_timeline_db=bool(exo_raw.get("use_timeline_db", False)),
            db_host=str(exo_raw.get("db_host", "127.0.0.1")),
            db_port=int(exo_raw.get("db_port", 3306)),
            db_user=str(exo_raw.get("db_user", "")),
            db_password=str(exo_raw.get("db_password", "")),
            db_name=str(exo_raw.get("db_name", "")),
            profile_id=str(exo_raw.get("profile_id", "")),
        )
        sc = ScenarioConfig(
            site_host=d["site_host"],
            pages=pages,
            countries=[tuple(x) for x in d["countries"]],
            accept_lang_by_country={k: [tuple(x) for x in v] for k, v in d["accept_lang_by_country"].items()},
            device_weights=[tuple(x) for x in d["device_weights"]],
            uas_mobile=[tuple(x) for x in d["uas_mobile"]],
            uas_desktop=[tuple(x) for x in d["uas_desktop"]],
            event_mix_default=[tuple(x) for x in d["event_mix_default"]],
            event_mix_by_page_type={k: [tuple(x) for x in v] for k, v in d.get("event_mix_by_page_type", {}).items()},
            traffic_curve=traffic_curve,
            exogenous=exogenous,
            new_visit_ratio_by_hh=list(d.get("new_visit_ratio_by_hh", [0.58] * 24)),
            revisit_ratio_by_hh=list(d.get("revisit_ratio_by_hh", [0.42] * 24)),
            session_event_rate_by_hh=list(d.get("session_event_rate_by_hh", [0.035] * 24)),
        )
        for k in [
            "pcid_reuse", "pcid_uid_stickiness", "uid_rate", "uid_acquire_half_life_sessions",
            "uid_acquire_click_boost", "uid_acquire_page_types", "revisit_ratio_daily",
            "session_mean_sec", "session_event_rate", "target_pv_per_visit_mean",
            "target_pv_per_visit_std", "max_pageviews_per_session", "server_hit_ratio_by_event",
            "weekday_multiplier",
        ]:
            if k in d:
                setattr(sc, k, d[k])
        sc.pcid_reuse = clamp(float(sc.pcid_reuse), 0.0, 1.0)
        sc.pcid_uid_stickiness = clamp(float(sc.pcid_uid_stickiness), 0.0, 1.0)
        sc.uid_rate = clamp(float(sc.uid_rate), 0.0, 1.0)
        sc.uid_acquire_click_boost = clamp(float(sc.uid_acquire_click_boost), 0.0, 1.0)
        sc.revisit_ratio_daily = clamp(float(sc.revisit_ratio_daily), 0.0, 0.95)
        sc.uid_acquire_half_life_sessions = max(1, int(sc.uid_acquire_half_life_sessions))
        sc.session_mean_sec = max(20, int(sc.session_mean_sec))
        sc.session_event_rate = max(0.0, float(sc.session_event_rate))
        sc.target_pv_per_visit_mean = max(1.0, float(sc.target_pv_per_visit_mean))
        sc.target_pv_per_visit_std = max(0.1, float(sc.target_pv_per_visit_std))
        sc.max_pageviews_per_session = max(1, int(sc.max_pageviews_per_session))
        if len(sc.traffic_curve.hh_multiplier) != 24:
            sc.traffic_curve.hh_multiplier = [1.0] * 24
        if len(sc.traffic_curve.target_visit_per_hh) != 24:
            sc.traffic_curve.target_visit_per_hh = [0] * 24
        if len(sc.new_visit_ratio_by_hh) != 24:
            sc.new_visit_ratio_by_hh = [0.58] * 24
        if len(sc.revisit_ratio_by_hh) != 24:
            sc.revisit_ratio_by_hh = [0.42] * 24
        if len(sc.session_event_rate_by_hh) != 24:
            sc.session_event_rate_by_hh = [float(sc.session_event_rate)] * 24
        sc.new_visit_ratio_by_hh = [clamp(float(x), 0.01, 0.95) for x in sc.new_visit_ratio_by_hh]
        sc.revisit_ratio_by_hh = [clamp(float(x), 0.01, 0.99) for x in sc.revisit_ratio_by_hh]
        sc.session_event_rate_by_hh = [max(0.0, float(x)) for x in sc.session_event_rate_by_hh]
        return sc
