from __future__ import annotations

from datetime import timedelta, datetime, time
from typing import Any
import random
import uuid

from simulator.customer_journey_sim.journey.model import JourneyContext


def _ua(device_type: str) -> str:
    mobile = [
        "Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/122.0.0.0 Mobile/15E148 Safari/604.1",
    ]
    desktop = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]
    return random.choice(mobile if device_type == "mobile" else desktop)


def _referer(stage: str, device_type: str) -> str:
    host = "https://m.commerce-deliver.example.com" if device_type == "mobile" else "https://www.commerce-deliver.example.com"
    if stage in {"home", "browse"}:
        pool = [
            ("-", 0.32),
            ("https://search.naver.com/search.naver?query=delivery", 0.18),
            ("https://www.google.com/search?q=food+delivery", 0.14),
            ("https://search.daum.net/search?q=chicken+delivery", 0.08),
            ("https://m.search.daum.net/search?q=pizza", 0.06),
            ("https://talk.kakao.com/channel/commerce-deliver", 0.05),
            (f"{host}/event/coupon.do?utm_source=campaign&utm_medium=push", 0.09),
            (f"{host}/main.do", 0.08),
        ]
        total = sum(w for _, w in pool)
        pick = random.random() * total
        cur = 0.0
        for value, weight in pool:
            cur += weight
            if pick <= cur:
                return value
        return pool[-1][0]
    prev = {
        "search": "/main.do",
        "product_view": "/search/result.do?keyword=chicken",
        "add_cart": "/product/view.do",
        "checkout": "/cart/view.do",
        "payment": "/checkout/start.do",
        "order_complete": "/payment/request.do",
        "delivery": "/order/complete.do",
        "refund": "/order/detail.do",
    }.get(stage, "/main.do")
    return f"{host}{prev}"

def _ip() -> str:
    return random.choice(["211.54", "223.113", "223.177", "121.140", "59.6"]) + f".{random.randint(1,254)}.{random.randint(1,254)}"


def _event_type(stage: str) -> str:
    if stage in {"home", "browse", "product_view", "delivery"}:
        return "view"
    if stage in {"search"}:
        return "search"
    return "click"


def _page_type(stage: str) -> str:
    mapping = {
        "home": "home",
        "browse": "category",
        "search": "search",
        "product_view": "product",
        "add_cart": "cart",
        "checkout": "checkout",
        "payment": "payment",
        "order_complete": "order",
        "delivery": "delivery",
        "refund": "refund",
    }
    return mapping.get(stage, stage)




def _resolve_app_metadata(ctx: JourneyContext, profile: dict[str, Any]) -> tuple[str, str, str]:
    """Return app_platform/app_version/sdk_version for behavior observability.

    CASE-OBS-001 Phase2 treats PC web and mobile web as responsive web: they
    may have different app_platform values for analysis, but they intentionally
    share the same WC web SDK version. Native app values can be supplied later
    through profile["app_metadata"] without changing the source contract.
    """
    explicit_platform = str(getattr(ctx, "app_platform", "") or "")
    explicit_app_version = str(getattr(ctx, "app_version", "") or "")
    explicit_sdk_version = str(getattr(ctx, "sdk_version", "") or "")
    if explicit_platform and explicit_app_version and explicit_sdk_version:
        return explicit_platform, explicit_app_version, explicit_sdk_version

    meta = profile.get("app_metadata", {}) if isinstance(profile.get("app_metadata"), dict) else {}
    device_type = str(getattr(ctx, "device_type", "") or "").lower()

    pc_web_platform = str(meta.get("pc_web_platform", "pc_web"))
    mobile_web_platform = str(meta.get("mobile_web_platform", "mobile_web"))
    ios_app_platform = str(meta.get("ios_app_platform", "ios_app"))
    android_app_platform = str(meta.get("android_app_platform", "android_app"))
    responsive_web_app_version = str(meta.get("responsive_web_app_version", "responsive-web-2026.06.0"))
    responsive_web_sdk_version = str(meta.get("responsive_web_sdk_version", "wc-web-2.8.0"))

    explicit_platform_l = explicit_platform.lower()
    if explicit_platform_l in {"ios", "native_ios", "ios_app"}:
        return ios_app_platform, "ios-app-5.3.0", "wc-ios-3.2.1"
    if explicit_platform_l in {"android", "native_android", "android_app"}:
        return android_app_platform, "android-app-4.9.0", "wc-aos-2.7.1"

    if device_type == "desktop":
        return pc_web_platform, responsive_web_app_version, responsive_web_sdk_version
    return mobile_web_platform, responsive_web_app_version, responsive_web_sdk_version

def _cookie(ctx: JourneyContext, stage: str, stage_index: int, profile: dict[str, Any], anomaly: dict[str, Any], status: str, latency_ms: int) -> str:
    scenario = str(anomaly.get("scenario_id", anomaly.get("scenario_name", "baseline")))
    if scenario == "none":
        scenario = "baseline"
    anomaly_type = str(anomaly.get("anomaly_type", "none"))
    reconciliation_flag = str(anomaly.get("reconciliation_flag", "none"))
    affected = "1" if anomaly_type != "none" and stage in set(anomaly.get("target_stages", [])) else "0"
    domain = str(profile.get("domain", "commerce"))
    run_id = str(profile.get("run_id", "v05_phase1"))
    experiment_id = f"exp_v05_phase1_{domain}_{ctx.created_at.strftime('%Y-%m-%d')}_{scenario}"
    auth_uid = str(getattr(ctx, "authenticated_customer_id", "") or "")
    auth_start_idx = int(getattr(ctx, "auth_start_stage_index", -1) or -1)
    cookie_uid = auth_uid if auth_uid and auth_start_idx >= 0 and int(stage_index) >= auth_start_idx else ""
    uid_present = "1" if cookie_uid else "0"
    app_platform, app_version, sdk_version = _resolve_app_metadata(ctx, profile)
    pairs = {
        # Existing v0.4 source contract style fields
        "cc": getattr(ctx, "country", "KR"),
        "al": str(getattr(ctx, "accept_lang", "ko-KR,ko;q=0.9,en-US;q=0.6,en;q=0.4")).replace(";", ",").replace("=", "_"),
        "device": ctx.device_type,
        "app_platform": app_platform,
        "app_version": app_version,
        "sdk_version": sdk_version,
        "pcid": ctx.pcid,
        "sid": ctx.session_id,
        "uid": cookie_uid,
        "evt": _event_type(stage),
        "event_type": _event_type(stage),
        "page_type": _page_type(stage),
        "product_type": "commerce_delivery",
        "latency_ms": str(latency_ms),
        "http_status": status,
        "schema_version": "v0.5-commerce-source-contract",
        "scenario_id": scenario,
        "scenario_name": scenario,
        "domain": domain,
        "source_layer": "behavior",
        "anomaly_type": anomaly_type,
        "drift": str(anomaly.get("drift", "off")),
        "affected": affected,
        "exo_state_id": "none",
        "anomaly_contract_id": "contract_web_source_v05_commerce",
        "experiment_id": experiment_id,
        "run_id": run_id,
        "exo_source": scenario,
        "weather_type": "clear",
        "campaign_flag": str(anomaly.get("campaign_flag", "none")),
        "system_flag": str(anomaly.get("system_flag", "normal")),
        "volume_multiplier": str(anomaly.get("volume_multiplier", 1.0)),
        "conversion_multiplier": str(anomaly.get("conversion_multiplier", 1.0)),
        "latency_shift_ms": str(anomaly.get("latency_shift_ms", 0)),
        "drop_probability": str(anomaly.get("behavior_drop_rate", 0.0)),
        "timeout_multiplier": str(anomaly.get("timeout_multiplier", 1.0)),
        "retry_multiplier": str(anomaly.get("retry_multiplier", 1.0)),
        "duplicate_multiplier": str(anomaly.get("duplicate_multiplier", 1.0)),
        "event_time_skew_ms": str(anomaly.get("event_time_skew_ms", 0)),
        "suppress_input": "0",
        "schema_flag": str(anomaly.get("schema_flag", "normal")),
        "identity_flag": str(anomaly.get("identity_flag", "normal")),
        "pcid_stability": "stable",
        "session_stability": "stable",
        "customer_id_stability": "authenticated_cookie_visible" if cookie_uid else "anonymous_cookie",
        "login_status": "authenticated" if cookie_uid else "anonymous",
        "uid_present": uid_present,
        "auth_login_stage": str(getattr(ctx, "auth_login_stage", "anonymous")),
        "traffic_actor": getattr(ctx, "behavior_actor", "human"),
        "bot_flag": "0",
        "user_agent_flag": "normal",
        "ip_concentration_flag": "normal",
        "recovery_flag": "none",
        "backlog_flush": "0",
        "transaction_delay_ms": str(anomaly.get("transaction_delay_ms", 0)),
        "event_ingestion_delay_ms": str(anomaly.get("event_ingestion_delay_ms", 0)),
        "privacy_flag": "normal",
        "pii_detected": "0",
        "sensitive_field_flag": "none",
        "masking_status": "masked",
        # v0.5 commerce extensions
        "journey_id": ctx.journey_id,
        "journey_stage": stage,
        "product_id": ctx.product_id,
        "cart_id": ctx.cart_id,
        "coupon_id": ctx.coupon_id,
        "order_id": ctx.order_id,
        "payment_id": ctx.payment_id,
        "delivery_id": ctx.delivery_id,
        "customer_segment": ctx.customer_segment,
        "device_type": ctx.device_type,
        "commerce_product": "delivery_food",
        "funnel_stage": stage,
        "exit_stage": getattr(ctx, "exit_stage", stage),
        "session_duration_sec": str(getattr(ctx, "session_duration_sec", 0)),
        "state_transition": "none",
        "expected_state": "none",
        "actual_state": "none",
        "amount_expected": str(getattr(ctx, "final_amount", 0)),
        "amount_actual": str(getattr(ctx, "final_amount", 0)),
        "amount_delta": "0",
        "approval_result": "none",
        "execution_result": "none",
        "account_status": "none",
        "ledger_status": "none",
        "balance_delta": "0",
        "reconciliation_flag": reconciliation_flag,
    }
    return "; ".join(f"{k}={v}" for k, v in pairs.items()) + ";"


def build_behavior_rows(ctx: JourneyContext, profile: dict[str, Any], anomaly: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    stages = list(getattr(ctx, "stage_sequence", None) or profile.get("journey_stages", []))
    paths = dict(profile.get("behavior_paths", {}))
    target_stages = set(anomaly.get("target_stages", []))
    drop_rate = float(anomaly.get("behavior_drop_rate", 0.0))
    latency_shift = int(anomaly.get("latency_shift_ms", 0))
    for stage_index, stage in enumerate(stages):
        offset = stage_index
        if target_stages and stage in target_stages and random.random() < drop_rate:
            continue
        path_template = str(paths.get(stage, f"/{stage}.do"))
        path = path_template.format(
            product_id=ctx.product_id,
            order_id=ctx.order_id,
            payment_id=ctx.payment_id,
            delivery_id=ctx.delivery_id,
            cart_id=ctx.cart_id,
            coupon_id=ctx.coupon_id,
        )
        query = profile.get("behavior_query", {}).get(stage, "")
        if query:
            query = str(query).format(
                journey_id=ctx.journey_id,
                product_id=ctx.product_id,
                cart_id=ctx.cart_id,
                coupon_id=ctx.coupon_id,
                order_id=ctx.order_id,
                payment_id=ctx.payment_id,
                delivery_id=ctx.delivery_id,
                journey_stage=stage,
            )
            uri = f"{path}?{query}"
        else:
            uri = path
        stage_offsets = list(getattr(ctx, "stage_offsets_sec", []))
        sec_offset = stage_offsets[offset] if offset < len(stage_offsets) else offset * random.randint(20, 90)
        ts = ctx.created_at + timedelta(seconds=sec_offset)
        # Keep behavior source log inside the event_date directory's calendar day.
        # Transaction/state evidence may carry operational delay, but user behavior hits should remain day-bounded.
        day_end = datetime.combine(ctx.created_at.date(), time(23, 59, 59))
        if ts > day_end:
            ts = day_end
        latency_ms = max(1, random.randint(35, 180) + latency_shift)
        status = "200"
        rows.append(
            {
                "ip": getattr(ctx, "ip", "") or _ip(),
                "event_time": ts.isoformat(),
                "timestamp": ts.strftime("%d/%b/%Y:%H:%M:%S +0900"),
                "method": "GET" if stage not in {"checkout", "payment", "refund"} else "POST",
                "uri": uri,
                "status": status,
                "bytes": str(random.randint(900, 48000)),
                "referer": _referer(stage, ctx.device_type),
                "user_agent": getattr(ctx, "user_agent", "") or _ua(ctx.device_type),
                "cookie": _cookie(ctx, stage, stage_index, profile, anomaly, status, latency_ms),
                "journey_id": ctx.journey_id,
                "order_id": ctx.order_id,
                "payment_id": ctx.payment_id,
                "stage": stage,
            }
        )
    return rows


def to_apache_line(row: dict[str, str]) -> str:
    # Apache combined style plus quoted cookie field, compatible with existing v0.4 source examples.
    return (
        f'{row.get("ip", "-")} - - [{row.get("timestamp", "-")}] '
        f'"{row.get("method", "GET")} {row.get("uri", "/")} HTTP/1.1" '
        f'{row.get("status", "200")} {row.get("bytes", "0")} '
        f'"{row.get("referer", "-")}" "{row.get("user_agent", "-")}" '
        f'"{row.get("cookie", "")}"'
    )


def to_w3c_line(row: dict[str, str]) -> str:
    # Backward-compatible alias. The generated file is Apache access-log format.
    return to_apache_line(row)
