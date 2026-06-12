from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any
import random
import uuid


@dataclass(frozen=True)
class VisitorIdentity:
    visitor_id: str
    customer_id: str
    pcid: str
    customer_segment: str
    device_type: str
    first_seen: datetime
    visit_count: int = 1
    country: str = "KR"
    accept_lang: str = "ko-KR,ko;q=0.9,en-US;q=0.6,en;q=0.4"
    user_agent: str = ""
    ip: str = ""
    app_platform: str = ""
    app_version: str = ""
    sdk_version: str = ""


@dataclass(frozen=True)
class JourneyContext:
    profile_id: str
    journey_id: str
    session_id: str
    visitor_id: str
    customer_id: str
    authenticated_customer_id: str
    auth_start_stage_index: int
    auth_login_stage: str
    pcid: str
    product_id: str
    cart_id: str
    coupon_id: str
    order_id: str
    payment_id: str
    delivery_id: str
    customer_segment: str
    device_type: str
    base_price: int
    discount_amount: int
    final_amount: int
    created_at: datetime
    session_duration_sec: int
    stage_sequence: list[str]
    stage_offsets_sec: list[int]
    behavior_actor: str
    exit_stage: str
    has_cart: bool
    has_checkout: bool
    has_payment: bool
    has_order: bool
    has_delivery: bool
    has_refund: bool
    country: str
    accept_lang: str
    ip: str
    user_agent: str
    visit_count: int
    app_platform: str = ""
    app_version: str = ""
    sdk_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


def weighted_choice(items: list[dict[str, Any]], name_key: str = "name") -> dict[str, Any]:
    total = sum(float(x.get("weight", 1.0)) for x in items)
    pick = random.random() * total
    current = 0.0
    for item in items:
        current += float(item.get("weight", 1.0))
        if pick <= current:
            return item
    return items[-1]


def _weighted_value(items: Any, default: str) -> str:
    if not isinstance(items, list) or not items:
        return default
    normalized: list[tuple[str, float]] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append((str(item.get("value", item.get("name", default))), float(item.get("weight", 1.0))))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            normalized.append((str(item[0]), float(item[1])))
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


def _sample_app_metadata(profile: dict[str, Any], device_type: str) -> tuple[str, str, str]:
    """Sample stable app/sdk metadata for one visitor/session.

    PC web and mobile web are responsive web and intentionally share the same
    WC web SDK version. Native iOS/Android receive app-version and SDK-version
    distributions so CASE-OBS-001 can measure version-specific collection gaps.
    """
    meta = profile.get("app_metadata", {}) if isinstance(profile.get("app_metadata"), dict) else {}
    pc_web_platform = str(meta.get("pc_web_platform", "pc_web"))
    mobile_web_platform = str(meta.get("mobile_web_platform", "mobile_web"))
    ios_app_platform = str(meta.get("ios_app_platform", "ios_app"))
    android_app_platform = str(meta.get("android_app_platform", "android_app"))
    responsive_web_app_version = str(meta.get("responsive_web_app_version", "responsive-web-2026.06.0"))
    responsive_web_sdk_version = str(meta.get("responsive_web_sdk_version", "wc-web-2.8.0"))

    if str(device_type).lower() == "desktop":
        return pc_web_platform, responsive_web_app_version, responsive_web_sdk_version

    platform = _weighted_value(meta.get("mobile_platform_mix"), mobile_web_platform)
    if platform == ios_app_platform:
        return platform, _weighted_value(meta.get("ios_app_versions"), "ios-app-5.3.0"), _weighted_value(meta.get("ios_sdk_versions"), "wc-ios-3.2.1")
    if platform == android_app_platform:
        return platform, _weighted_value(meta.get("android_app_versions"), "android-app-4.9.0"), _weighted_value(meta.get("android_sdk_versions"), "wc-aos-2.7.1")
    return mobile_web_platform, responsive_web_app_version, responsive_web_sdk_version


def _choose_actor(segment: str, device_type: str, hour: int) -> str:
    # v0.5 baseline must look like real users, not one deterministic stage sequence.
    # Actor controls browsing depth, backtracking, dwell time, and abandon behavior.
    weights = [
        ("bounce", 0.16),
        ("quick_order", 0.30),
        ("normal_browse", 0.34),
        ("compare_heavy", 0.13),
        ("coupon_hunter", 0.07),
    ]
    if segment in {"returning", "vip"}:
        weights = [(k, v + (0.10 if k == "quick_order" else 0.0)) for k, v in weights]
    if device_type == "mobile" and hour in {11, 12, 18, 19, 20}:
        weights = [(k, v + (0.06 if k == "quick_order" else 0.0)) for k, v in weights]
    if hour in {0, 1, 2, 3, 4, 5, 22, 23}:
        weights = [(k, v + (0.06 if k in {"bounce", "normal_browse"} else 0.0)) for k, v in weights]
    total = sum(v for _, v in weights)
    pick = random.random() * total
    current = 0.0
    for name, value in weights:
        current += value
        if pick <= current:
            return name
    return "normal_browse"


def _append_compare_loop(stages: list[str], actor: str, meal_peak: float) -> None:
    if actor == "bounce":
        return
    if actor == "quick_order":
        max_loop = random.choice([0, 1, 1, 2])
    elif actor == "normal_browse":
        max_loop = random.choice([0, 1, 1, 2, 3])
    elif actor == "compare_heavy":
        max_loop = random.choice([1, 2, 3, 4])
    else:  # coupon_hunter
        max_loop = random.choice([1, 2, 3, 4])
    for _ in range(max_loop):
        # Non-linear navigation: category back, search refinement, product revisit.
        stages.append(random.choice(["browse", "search", "product_view", "product_view"]))
        if random.random() < 0.12 + 0.05 * meal_peak:
            stages.append(random.choice(["search", "browse"]))


def _stage_offsets(stages: list[str], actor: str, device_type: str) -> tuple[list[int], int]:
    offsets: list[int] = []
    elapsed = 0
    for idx, stage in enumerate(stages):
        offsets.append(elapsed)
        if idx == len(stages) - 1:
            break
        if stage == "home":
            think = random.randint(5, 24)
        elif stage == "browse":
            think = random.randint(18, 75)
        elif stage == "search":
            think = random.randint(25, 95)
        elif stage == "product_view":
            think = random.randint(35, 150)
        elif stage == "add_cart":
            think = random.randint(12, 55)
        elif stage == "checkout":
            think = random.randint(30, 180)
        elif stage == "payment":
            think = random.randint(12, 85)
        else:
            think = random.randint(12, 80)
        if actor == "compare_heavy":
            think = int(think * random.uniform(1.2, 1.8))
        elif actor == "quick_order":
            think = int(think * random.uniform(0.55, 0.9))
        elif actor == "bounce":
            think = int(think * random.uniform(0.35, 0.75))
        elif actor == "coupon_hunter":
            think = int(think * random.uniform(1.05, 1.45))
        if device_type == "mobile":
            think = int(think * random.uniform(0.85, 1.15))
        elapsed += max(3, think)
    return offsets, max(0, elapsed)


def _sample_stage_sequence(profile: dict[str, Any], created_at: datetime, segment: str, device_type: str) -> tuple[list[str], list[int], str, dict[str, bool]]:
    """Build a user-like commerce visit path.

    This is not a Behavior -> Transaction trigger. The generated journey intent is the source,
    and behavior/transaction/state are later derived independently from this journey context.
    """
    hour = created_at.hour
    meal_peak = 1.0 if hour in (11, 12, 13, 18, 19, 20, 21) else 0.0
    evening = 1.0 if 17 <= hour <= 22 else 0.0
    actor = _choose_actor(segment, device_type, hour)
    vip_boost = 0.09 if segment == "vip" else 0.0
    returning_boost = 0.05 if segment == "returning" else 0.0
    mobile_boost = 0.03 if device_type == "mobile" else 0.0

    stages: list[str] = []
    if actor == "quick_order" and random.random() < 0.45:
        stages.extend(["search", "product_view"])
    else:
        stages.append("home" if random.random() < 0.56 else "browse")
        if random.random() < 0.78:
            stages.append("browse")
        if random.random() < 0.58 + 0.07 * meal_peak:
            stages.append("search")
        if random.random() < 0.78 + 0.06 * meal_peak:
            stages.append("product_view")

    # Bounce/light exits are explicit, because v0.4-like user behavior includes shallow visits.
    if actor == "bounce":
        if len(stages) > random.choice([1, 2]):
            stages = stages[: random.choice([1, 2])]
        offsets, duration = _stage_offsets(stages, actor, device_type)
        return stages, offsets, actor, {
            "has_cart": False,
            "has_checkout": False,
            "has_payment": False,
            "has_order": False,
            "has_delivery": False,
            "has_refund": False,
            "session_duration_sec": duration,
        }

    _append_compare_loop(stages, actor, meal_peak)

    p_cart = 0.23 + 0.10 * meal_peak + vip_boost + returning_boost
    p_checkout = 0.63 + 0.06 * meal_peak + vip_boost
    p_payment = 0.71 + 0.05 * meal_peak + mobile_boost
    p_order = 0.86 + 0.04 * meal_peak
    p_delivery = 0.53 + 0.08 * evening
    p_refund = 0.018
    if actor == "quick_order":
        p_cart += 0.18; p_checkout += 0.10; p_payment += 0.07
    elif actor == "compare_heavy":
        p_cart -= 0.04; p_checkout -= 0.06
    elif actor == "coupon_hunter":
        p_cart += 0.06; p_checkout += 0.03; p_payment -= 0.02

    has_cart = random.random() < min(0.90, max(0.03, p_cart))
    has_checkout = False
    has_payment = False
    has_order = False
    has_delivery = False
    has_refund = False

    if has_cart:
        stages.append("add_cart")
        # Abandon model: cart/checkout exits must exist for conversion distortion baseline realism.
        has_checkout = random.random() < min(0.93, max(0.10, p_checkout))
    if has_checkout:
        stages.append("checkout")
        if actor == "coupon_hunter" and random.random() < 0.55:
            stages.insert(max(1, len(stages) - 1), random.choice(["search", "product_view"]))
        has_payment = random.random() < min(0.95, max(0.10, p_payment))
    if has_payment:
        stages.append("payment")
        has_order = random.random() < min(0.97, max(0.30, p_order))
    if has_order:
        stages.append("order_complete")
        has_delivery = random.random() < min(0.82, max(0.15, p_delivery))
    if has_delivery:
        stages.append("delivery")
    if has_order and random.random() < p_refund:
        stages.append("refund")
        has_refund = True

    # Cap extreme paths while preserving entropy.
    if len(stages) > 10:
        # Keep tail transaction states if they exist.
        tail = [s for s in stages if s in {"add_cart", "checkout", "payment", "order_complete", "delivery", "refund"}]
        head = stages[: max(3, 10 - len(tail))]
        stages = head + tail
    offsets, duration = _stage_offsets(stages, actor, device_type)
    return stages, offsets, actor, {
        "has_cart": has_cart,
        "has_checkout": has_checkout,
        "has_payment": has_payment,
        "has_order": has_order,
        "has_delivery": has_delivery,
        "has_refund": has_refund,
        "session_duration_sec": duration,
    }



def _rate_by_segment(config: dict[str, Any], segment: str, default: float) -> float:
    values = config.get("logged_in_session_rate_by_segment") or {}
    try:
        return float(values.get(segment, default))
    except Exception:
        return default


def _resolve_cookie_uid_auth(
    profile: dict[str, Any],
    stages: list[str],
    customer_segment: str,
    customer_id: str,
) -> tuple[str, int, str]:
    """Resolve whether/when uid should appear in behavior cookie."""
    identity = profile.get("identity_model", {}) or {}
    policy = str(identity.get("uid_cookie_policy", "authenticated_only"))

    if policy == "always":
        return customer_id, 0, "session_start"
    if policy in {"never", "anonymous_only"}:
        return "", -1, "anonymous"

    default_rate = float(identity.get("default_logged_in_session_rate", 0.18))
    start_rate = max(0.0, min(1.0, _rate_by_segment(identity, customer_segment, default_rate)))
    if random.random() < start_rate:
        return customer_id, 0, "session_start"

    force_uid_stages = set(identity.get("force_uid_stages") or ["order_complete", "delivery", "refund"])
    exposure_stages = set(identity.get("uid_exposure_stages") or ["checkout", "payment", "order_complete", "delivery", "refund"])
    stage_prob = identity.get("auth_stage_probability") or {
        "checkout": 0.55,
        "payment": 0.85,
        "order_complete": 1.00,
        "delivery": 1.00,
        "refund": 1.00,
    }

    for idx, stage in enumerate(stages):
        if stage in force_uid_stages:
            return customer_id, idx, stage
        if stage not in exposure_stages:
            continue
        p = max(0.0, min(1.0, float(stage_prob.get(stage, 0.0))))
        if random.random() < p:
            return customer_id, idx, stage

    return "", -1, "anonymous"

def build_journey_context(
    profile: dict[str, Any],
    event_date: str,
    index: int,
    created_at: datetime | None = None,
    visitor: VisitorIdentity | None = None,
) -> JourneyContext:
    profile_id = str(profile.get("profile_id", "commerce_deliver"))
    if created_at is None:
        random_second = random.randint(0, 86399)
        created_at = datetime.fromisoformat(event_date) + timedelta(seconds=random_second)
    product = random.choice(profile.get("products", [{"product_id": "P10001", "base_price": 10000}]))
    if visitor is None:
        segment = weighted_choice(profile.get("customer_segments", [{"name": "new", "weight": 1}]))
        device = weighted_choice(profile.get("device_types", [{"name": "mobile", "weight": 1}]))
        visitor_id = f"V{random.randint(100000,999999)}"
        customer_id = f"C{random.randint(10000,99999)}"
        pcid = str(uuid.uuid5(uuid.NAMESPACE_DNS, visitor_id))
        customer_segment = str(segment.get("name", "new"))
        device_type = str(device.get("name", "mobile"))
        country = "KR"
        accept_lang = "ko-KR,ko;q=0.9,en-US;q=0.6,en;q=0.4"
        ip = f"223.113.{random.randint(1,254)}.{random.randint(1,254)}"
        user_agent = "Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
        app_platform, app_version, sdk_version = _sample_app_metadata(profile, device_type)
    else:
        visitor_id = visitor.visitor_id
        customer_id = visitor.customer_id
        pcid = visitor.pcid
        customer_segment = visitor.customer_segment
        device_type = visitor.device_type
        country = visitor.country
        accept_lang = visitor.accept_lang
        ip = visitor.ip
        user_agent = visitor.user_agent
        app_platform = visitor.app_platform
        app_version = visitor.app_version
        sdk_version = visitor.sdk_version

    coupon_id = ""
    discount = 0
    for coupon in profile.get("coupons", []):
        if random.random() <= float(coupon.get("apply_rate", 0.0)):
            coupon_id = str(coupon.get("coupon_id", ""))
            discount = int(coupon.get("discount_amount", 0))
            break
    base_price = int(product.get("base_price", 10000))
    final_amount = max(0, base_price - discount)
    suffix = f"{event_date.replace('-', '')}{index:06d}"
    stages, offsets, actor, flags = _sample_stage_sequence(profile, created_at, customer_segment, device_type)
    session_duration = max(0, int(flags.pop("session_duration_sec", 0)))
    authenticated_customer_id, auth_start_stage_index, auth_login_stage = _resolve_cookie_uid_auth(
        profile, stages, customer_segment, customer_id
    )
    return JourneyContext(
        profile_id=profile_id,
        journey_id=f"J{suffix}",
        session_id=f"S{suffix}",
        visitor_id=visitor_id,
        customer_id=customer_id,
        authenticated_customer_id=authenticated_customer_id,
        auth_start_stage_index=auth_start_stage_index,
        auth_login_stage=auth_login_stage,
        pcid=pcid,
        product_id=str(product.get("product_id", "P10001")),
        cart_id=f"CART{suffix}",
        coupon_id=coupon_id,
        order_id=f"ORD{suffix}",
        payment_id=f"PAY{suffix}",
        delivery_id=f"DLV{suffix}",
        customer_segment=customer_segment,
        device_type=device_type,
        base_price=base_price,
        discount_amount=discount,
        final_amount=final_amount,
        created_at=created_at,
        session_duration_sec=session_duration,
        stage_sequence=stages,
        stage_offsets_sec=offsets,
        behavior_actor=actor,
        exit_stage=stages[-1] if stages else "none",
        country=country,
        accept_lang=accept_lang,
        ip=ip,
        user_agent=user_agent,
        visit_count=int(getattr(visitor, "visit_count", 1) if visitor is not None else 1),
        app_platform=app_platform,
        app_version=app_version,
        sdk_version=sdk_version,
        **flags,
    )
