from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WeatherDrift:
    weather: str = "none"
    enabled: bool = False

    def traffic_boost(self) -> float:
        if not self.enabled or self.weather == "none":
            return 1.0
        if self.weather in ("rain", "snow"):
            return 1.20
        if self.weather == "heatwave":
            return 1.12
        return 1.0

    def page_weight_multiplier(self, page_type: str) -> float:
        if not self.enabled or self.weather == "none":
            return 1.0
        if self.weather in ("rain", "snow"):
            if page_type in ("forecast", "now", "warning", "radar"):
                return 1.35
            if page_type in ("branch",):
                return 0.80
            return 1.0
        if self.weather == "heatwave":
            if page_type in ("warning", "now", "air"):
                return 1.25
            return 1.0
        return 1.0

    def event_mix_override(self, page_type: str, base_mix):
        if not self.enabled or self.weather == "none":
            return base_mix
        if self.weather in ("rain", "snow") and page_type == "radar":
            return [("view", 0.50), ("swipe", 0.32), ("scroll", 0.12), ("click", 0.06)]
        return base_mix

    def uid_rate_multiplier(self) -> float:
        if not self.enabled or self.weather == "none":
            return 1.0
        if self.weather in ("rain", "snow"):
            return 1.04
        if self.weather == "heatwave":
            return 1.06
        return 1.0


def weekday_profile_multiplier(dt: datetime) -> float:
    dow = dt.weekday()
    return [1.10, 1.08, 1.06, 1.04, 0.98, 0.82, 0.72][dow]


def hourly_shape_multiplier(dt: datetime) -> float:
    h = dt.hour
    weekend = dt.weekday() in (5, 6)
    peak_morning = math.exp(-0.5 * ((h - 10) / 3.0) ** 2)
    peak_evening = math.exp(-0.5 * ((h - 19) / 3.5) ** 2)
    if weekend:
        return 0.16 + 1.05 * (0.45 * peak_morning + 0.65 * peak_evening)
    return 0.18 + 1.20 * (0.55 * peak_morning + 0.75 * peak_evening)


def traffic_multiplier(dt: datetime, drift: WeatherDrift) -> float:
    return hourly_shape_multiplier(dt) * weekday_profile_multiplier(dt) * drift.traffic_boost()


def apply_source_volume(avg_rps: float, exo_state) -> float:
    if getattr(exo_state, "suppress_input", False):
        return 0.0
    return max(0.0, float(avg_rps) * float(getattr(exo_state, "volume_multiplier", 1.0) or 1.0))


def should_drop_source_event(exo_state) -> bool:
    if getattr(exo_state, "suppress_input", False):
        return True
    p = float(getattr(exo_state, "drop_probability", 0.0) or 0.0)
    return p > 0.0 and random.random() < p
