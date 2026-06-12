from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from .randomutil import clamp, make_uid, make_uuid, weighted_choice
from .scenario import ScenarioConfig
from .traffic import WeatherDrift
from .weather_provider import build_weather_provider
from .exogenous import ExogenousState


@dataclass
class Visitor:
    pcid: str
    uid: Optional[str]
    country: str
    accept_lang: str
    device: str
    ua: str
    ip: str
    first_seen: datetime
    last_seen: datetime
    sessions: int = 0
    uid_acquired_at: Optional[datetime] = None


class IdentityPool:
    def __init__(self, scenario: ScenarioConfig, drift: WeatherDrift):
        self.scenario = scenario
        self.drift = drift
        self._visitors: List[Visitor] = []
        self._pcid_to_uid: Dict[str, Optional[str]] = {}
        self.weather_provider = build_weather_provider(getattr(scenario, "exogenous", None))

    def _exo(self, when: datetime) -> ExogenousState:
        return self.weather_provider.get_state(when)

    def _random_ip_for_country(self, cc: str) -> str:
        if cc == "KR":
            first = random.choice([114, 121, 175, 211, 223])
            return f"{first}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
        if cc == "US":
            first = random.choice([3, 13, 34, 52, 54, 63, 65])
            return f"{first}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
        if cc == "JP":
            first = random.choice([106, 133, 153, 210])
            return f"{first}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
        first = random.randint(1, 223)
        return f"{first}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

    def _pick_country(self) -> str:
        return weighted_choice(self.scenario.countries)

    def _pick_accept_language(self, cc: str) -> str:
        pool = self.scenario.accept_lang_by_country.get(cc) or [("en-US,en;q=0.9", 1.0)]
        return weighted_choice(pool)

    def _pick_device(self, now_dt: datetime) -> str:
        exo = self._exo(now_dt)
        if exo.enabled and exo.weather_type == "rain":
            return weighted_choice([("mobile", 0.80), ("desktop", 0.20)])
        if self.drift.enabled and self.drift.weather != "none":
            return weighted_choice([("mobile", 0.80), ("desktop", 0.20)])
        return weighted_choice(self.scenario.device_weights)

    def _pick_ua(self, device: str) -> str:
        pool = self.scenario.uas_mobile if device == "mobile" else self.scenario.uas_desktop
        return weighted_choice(pool)

    def _initial_uid(self, now_dt: datetime) -> Optional[str]:
        exo = self._exo(now_dt)
        p = float(self.scenario.uid_rate)
        if self.drift.enabled and self.drift.weather != "none":
            p *= self.drift.uid_rate_multiplier()
        if exo.enabled and exo.weather_type == "rain":
            p *= 1.03
        p = clamp(p, 0.0, 1.0)
        return make_uid() if random.random() < p else None

    def _uid_acquire_probability_per_session(self, v: Visitor, now_dt: datetime) -> float:
        exo = self._exo(now_dt)
        cap = float(self.scenario.uid_rate)
        if self.drift.enabled and self.drift.weather != "none":
            cap *= self.drift.uid_rate_multiplier()
        if exo.enabled and exo.weather_type == "rain":
            cap *= 1.03
        cap = clamp(cap, 0.0, 1.0)
        hl = max(1, int(self.scenario.uid_acquire_half_life_sessions))
        growth = 1.0 - (2.0 ** (-(max(0, v.sessions)) / float(hl)))
        return clamp(cap * growth * 0.65, 0.0, 1.0)

    def maybe_acquire_uid_on_session_start(self, v: Visitor, now_dt: datetime) -> None:
        if v.uid is not None:
            return
        if random.random() < self._uid_acquire_probability_per_session(v, now_dt):
            v.uid = make_uid()
            v.uid_acquired_at = now_dt
            self._pcid_to_uid[v.pcid] = v.uid

    def maybe_acquire_uid_in_session(self, v: Visitor, now_dt: datetime, event: str, page_type: str) -> None:
        if v.uid is not None:
            return
        cap = clamp(float(self.scenario.uid_rate), 0.0, 1.0)
        base = 0.003 * cap
        if event == "click":
            base += float(self.scenario.uid_acquire_click_boost) * cap
        if page_type in self.scenario.uid_acquire_page_types:
            base *= 1.25
        if random.random() < clamp(base, 0.0, 1.0):
            v.uid = make_uid()
            v.uid_acquired_at = now_dt
            self._pcid_to_uid[v.pcid] = v.uid

    def _create_new_visitor(self, now_dt: datetime) -> Visitor:
        cc = self._pick_country()
        al = self._pick_accept_language(cc)
        device = self._pick_device(now_dt)
        ua = self._pick_ua(device)
        ip = self._random_ip_for_country(cc)
        pcid = make_uuid()
        uid = self._initial_uid(now_dt)
        v = Visitor(
            pcid=pcid, uid=uid, country=cc, accept_lang=al, device=device, ua=ua, ip=ip,
            first_seen=now_dt, last_seen=now_dt, sessions=1,
            uid_acquired_at=(now_dt if uid is not None else None),
        )
        self._visitors.append(v)
        self._pcid_to_uid[pcid] = uid
        return v

    def _reuse_visitor(self, v: Visitor, now_dt: datetime) -> Visitor:
        if random.random() < float(self.scenario.pcid_uid_stickiness):
            v.uid = self._pcid_to_uid.get(v.pcid, v.uid)
        v.ip = self._random_ip_for_country(v.country)
        v.last_seen = now_dt
        v.sessions += 1
        self.maybe_acquire_uid_on_session_start(v, now_dt)
        return v

    def get_or_create_visitor(self, now_dt: datetime) -> Visitor:
        if self._visitors and random.random() < float(self.scenario.pcid_reuse):
            return self._reuse_visitor(random.choice(self._visitors), now_dt)
        return self._create_new_visitor(now_dt)

    def promote_today_to_historical(self) -> None:
        return
