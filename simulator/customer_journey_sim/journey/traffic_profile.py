from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
import random
import uuid

from simulator.customer_journey_sim.journey.model import VisitorIdentity, weighted_choice


DEFAULT_HOURLY_VISIT_WEIGHTS = [
    0.01070, 0.01272, 0.00946, 0.01210, 0.01288, 0.01815,
    0.02575, 0.02886, 0.04437, 0.04887, 0.05973, 0.05880,
    0.04871, 0.04561, 0.05026, 0.05290, 0.05507, 0.06066,
    0.06283, 0.07121, 0.06407, 0.05926, 0.04871, 0.03832,
]


def _weighted_pair_choice(items: Any, default: str) -> str:
    if not isinstance(items, list) or not items:
        return default
    normalized: list[tuple[str, float]] = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized.append((str(item[0]), float(item[1])))
        elif isinstance(item, dict):
            normalized.append((str(item.get("name", item.get("value", default))), float(item.get("weight", 1.0))))
        else:
            normalized.append((str(item), 1.0))
    total = sum(max(0.0, w) for _, w in normalized)
    if total <= 0:
        return normalized[0][0]
    pick = random.random() * total
    cur = 0.0
    for value, weight in normalized:
        cur += max(0.0, weight)
        if pick <= cur:
            return value
    return normalized[-1][0]


def _random_ip_for_country(cc: str) -> str:
    if cc == "KR":
        first = random.choice([114, 121, 175, 211, 223, 59])
    elif cc == "US":
        first = random.choice([3, 13, 34, 52, 54, 63, 65])
    elif cc == "JP":
        first = random.choice([106, 133, 153, 210])
    else:
        first = random.randint(1, 223)
    return f"{first}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def _same_subnet_ip(ip: str) -> str:
    parts = ip.split(".")
    if len(parts) != 4:
        return ip
    return f"{parts[0]}.{parts[1]}.{parts[2]}.{random.randint(1,254)}"


def _pick_user_agent(profile: dict[str, Any], device: str) -> str:
    if device == "desktop":
        pool = profile.get("uas_desktop") or []
    else:
        pool = profile.get("uas_mobile") or []
    if pool:
        return random.choice([str(x[0]) if isinstance(x, (list, tuple)) else str(x) for x in pool])
    if device == "desktop":
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    return "Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"


def _pick_accept_language(profile: dict[str, Any], cc: str) -> str:
    al = profile.get("accept_lang_by_country") or {}
    pool = al.get(cc) or [["ko-KR,ko;q=0.9,en-US;q=0.6,en;q=0.4", 1.0]]
    return _weighted_pair_choice(pool, "ko-KR,ko;q=0.9,en-US;q=0.6,en;q=0.4")


@dataclass
class IdentityPool:
    profile: dict[str, Any]
    visitors: list[VisitorIdentity]

    @classmethod
    def create(cls, profile: dict[str, Any]) -> "IdentityPool":
        return cls(profile=profile, visitors=[])

    def _new_visitor(self, when: datetime) -> VisitorIdentity:
        segment = weighted_choice(self.profile.get("customer_segments", [{"name": "new", "weight": 1}]))
        device = weighted_choice(self.profile.get("device_types", [{"name": "mobile", "weight": 1}]))
        country = _weighted_pair_choice(self.profile.get("countries"), "KR")
        device_type = str(device.get("name", "mobile"))
        visitor_id = f"V{uuid.uuid4().hex[:12]}"
        ip = _random_ip_for_country(country)
        return VisitorIdentity(
            visitor_id=visitor_id,
            customer_id=f"MEM{random.randint(1000000,9999999)}_{random.randint(10000000000,99999999999)}",
            pcid=str(uuid.uuid5(uuid.NAMESPACE_DNS, visitor_id)),
            customer_segment=str(segment.get("name", "new")),
            device_type=device_type,
            first_seen=when,
            visit_count=1,
            country=country,
            accept_lang=_pick_accept_language(self.profile, country),
            user_agent=_pick_user_agent(self.profile, device_type),
            ip=ip,
        )

    def _reuse_visitor(self, base: VisitorIdentity, when: datetime) -> VisitorIdentity:
        traffic = self.profile.get("traffic_model", {}) or {}
        ip_stickiness = float(traffic.get("repeat_ip_stickiness", 0.72))
        subnet_stickiness = float(traffic.get("repeat_subnet_stickiness", 0.22))
        if random.random() < ip_stickiness:
            ip = base.ip
        elif random.random() < subnet_stickiness:
            ip = _same_subnet_ip(base.ip)
        else:
            ip = _random_ip_for_country(base.country)
        # v0.4-style pcid/uid stickiness: same pcid + same uid, but new sid will be assigned by JourneyContext.
        return VisitorIdentity(
            visitor_id=base.visitor_id,
            customer_id=base.customer_id,
            pcid=base.pcid,
            customer_segment=base.customer_segment if base.customer_segment != "new" else random.choice(["new", "returning"]),
            device_type=base.device_type,
            first_seen=base.first_seen,
            visit_count=base.visit_count + 1,
            country=base.country,
            accept_lang=base.accept_lang,
            user_agent=base.user_agent,
            ip=ip,
        )

    def get(self, when: datetime) -> VisitorIdentity:
        traffic = self.profile.get("traffic_model", {}) or {}
        target_uv = int(traffic.get("target_daily_uv", 0) or 0)
        if target_uv > 0 and len(self.visitors) < target_uv:
            progress = len(self.visitors) / max(1, target_uv)
            new_ratio = max(0.35, 0.92 - 0.45 * progress)
        else:
            by_hh = traffic.get("new_visit_ratio_by_hh") or self.profile.get("new_visit_ratio_by_hh")
            new_ratio = float(by_hh[when.hour]) if by_hh and len(by_hh) == 24 else 0.55
        if not self.visitors or random.random() < new_ratio:
            visitor = self._new_visitor(when)
            self.visitors.append(visitor)
            return visitor
        eligible = [v for v in self.visitors if v.first_seen <= when] or self.visitors
        base = random.choice(eligible)
        reused = self._reuse_visitor(base, when)
        # update stored record so future repeat_visit_count and IP continuity reflect latest session.
        try:
            idx = self.visitors.index(base)
            self.visitors[idx] = reused
        except ValueError:
            pass
        return reused


def _weekday_key(dt: datetime) -> str:
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][dt.weekday()]


def target_daily_visits(profile: dict[str, Any], event_date: str, requested_journeys: int | None) -> int:
    if requested_journeys and requested_journeys > 0:
        return int(requested_journeys)
    traffic = profile.get("traffic_model", {})
    base = int(traffic.get("target_daily_visits", profile.get("target_daily_visits", 6446)))
    dt = datetime.fromisoformat(event_date)
    multiplier = float((traffic.get("weekday_multiplier") or {}).get(_weekday_key(dt), 1.0))
    return max(1, int(round(base * multiplier)))


def allocate_hourly_counts(profile: dict[str, Any], total_visits: int) -> list[int]:
    traffic = profile.get("traffic_model", {})
    weights = traffic.get("hourly_visit_weights") or traffic.get("hh_visit_weights") or DEFAULT_HOURLY_VISIT_WEIGHTS
    weights = [max(0.0, float(x)) for x in weights]
    if len(weights) != 24 or sum(weights) <= 0:
        weights = DEFAULT_HOURLY_VISIT_WEIGHTS
    total_weight = sum(weights)
    raw = [total_visits * w / total_weight for w in weights]
    counts = [int(x) for x in raw]
    remainder = total_visits - sum(counts)
    order = sorted(range(24), key=lambda h: raw[h] - counts[h], reverse=True)
    for h in order[:remainder]:
        counts[h] += 1
    return counts


def _minute_second_for_burst(hour: int, traffic: dict[str, Any]) -> tuple[int, int]:
    burst_enabled = bool(traffic.get("micro_burst_enabled", True))
    base_prob = float(traffic.get("micro_burst_probability", 0.18))
    peak_bonus = 0.10 if hour in {11, 12, 18, 19, 20} else 0.0
    if burst_enabled and random.random() < base_prob + peak_bonus:
        anchor = random.choice([0, 10, 15, 20, 30, 40, 45, 50])
        minute = min(59, max(0, int(random.gauss(anchor, 2.2))))
        second = min(59, max(0, int(random.expovariate(1 / 8))))
        return minute, second
    return random.randint(0, 59), random.randint(0, 59)


def generate_visit_times(profile: dict[str, Any], event_date: str, total_visits: int) -> list[datetime]:
    base = datetime.fromisoformat(event_date)
    counts = allocate_hourly_counts(profile, total_visits)
    traffic = profile.get("traffic_model", {})
    times: list[datetime] = []
    for hour, count in enumerate(counts):
        for _ in range(count):
            minute, second = _minute_second_for_burst(hour, traffic)
            times.append(base + timedelta(hours=hour, minutes=minute, seconds=second))
    return sorted(times)
