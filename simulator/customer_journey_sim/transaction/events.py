from __future__ import annotations

from datetime import timedelta
from typing import Any
import random

from simulator.customer_journey_sim.journey.model import JourneyContext


def _stage_time(ctx: JourneyContext, stage: str, fallback_offset: int) -> tuple[Any, int]:
    stages = list(getattr(ctx, "stage_sequence", []) or [])
    offsets = list(getattr(ctx, "stage_offsets_sec", []) or [])
    if stage in stages:
        idx = stages.index(stage)
        if idx < len(offsets):
            return ctx.created_at + timedelta(seconds=int(offsets[idx])), int(offsets[idx])
    return ctx.created_at + timedelta(seconds=fallback_offset), fallback_offset


def _delay_ms(event_name: str) -> int:
    if event_name == "coupon_applied":
        return random.randint(120, 1200)
    if event_name == "payment_requested":
        return random.randint(200, 1800)
    if event_name == "payment_approved":
        return random.randint(700, 6500)
    if event_name == "order_created":
        return random.randint(1200, 9000)
    if event_name == "refund_completed":
        return random.randint(3000, 45000)
    return random.randint(200, 5000)


def _anchor_stage(event_name: str) -> str:
    return {
        "coupon_applied": "checkout",
        "payment_requested": "payment",
        "payment_approved": "payment",
        "order_created": "order_complete",
        "refund_completed": "refund",
    }.get(event_name, "payment")


def build_transaction_events(ctx: JourneyContext, profile: dict[str, Any], anomaly: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    target_events = set(anomaly.get("target_transaction_events", []))
    drop_rate = float(anomaly.get("transaction_drop_rate", 0.0))
    candidates: list[str] = []
    if ctx.coupon_id and ctx.has_checkout:
        candidates.append("coupon_applied")
    if ctx.has_payment:
        candidates.append("payment_requested")
        candidates.append("payment_approved")
    if ctx.has_order:
        candidates.append("order_created")
    if ctx.has_refund:
        candidates.append("refund_completed")

    last_ts = ctx.created_at
    for seq, event_name in enumerate(candidates):
        if (not target_events or event_name in target_events) and random.random() < drop_rate:
            continue
        anchor_ts, anchor_offset = _stage_time(ctx, _anchor_stage(event_name), 40 + seq * 15)
        delay_ms = _delay_ms(event_name)
        ts = anchor_ts + timedelta(milliseconds=delay_ms)
        # Keep per-journey transaction order monotonic even when anchors are close.
        if ts <= last_ts:
            ts = last_ts + timedelta(milliseconds=random.randint(200, 1500))
        last_ts = ts
        events.append(
            {
                "event_time": ts.isoformat(),
                "profile_id": ctx.profile_id,
                "journey_id": ctx.journey_id,
                "transaction_event": event_name,
                "customer_id": ctx.customer_id,
                "product_id": ctx.product_id,
                "cart_id": ctx.cart_id,
                "coupon_id": ctx.coupon_id,
                "order_id": ctx.order_id,
                "payment_id": ctx.payment_id,
                "delivery_id": ctx.delivery_id,
                "amount": ctx.final_amount,
                "currency": "KRW",
                "source_system": "commerce_order_api",
                "behavior_anchor_stage": _anchor_stage(event_name),
                "behavior_anchor_offset_sec": anchor_offset,
                "transaction_delay_ms": delay_ms,
                "anomaly_flag": bool(anomaly and anomaly.get("anomaly_type", "none") != "none"),
            }
        )
    return events
