from __future__ import annotations

from datetime import timedelta
from typing import Any
import random

from simulator.customer_journey_sim.journey.model import JourneyContext


def _stage_time(ctx: JourneyContext, stage: str, fallback_offset: int):
    stages = list(getattr(ctx, "stage_sequence", []) or [])
    offsets = list(getattr(ctx, "stage_offsets_sec", []) or [])
    if stage in stages:
        idx = stages.index(stage)
        if idx < len(offsets):
            return ctx.created_at + timedelta(seconds=int(offsets[idx])), int(offsets[idx])
    return ctx.created_at + timedelta(seconds=fallback_offset), fallback_offset


def _anchor_stage(state_name: str) -> str:
    return {
        "order_status_created": "order_complete",
        "delivery_status_assigned": "delivery",
        "delivery_status_delivered": "delivery",
        "refund_status_completed": "refund",
    }.get(state_name, "order_complete")


def _delay_ms(state_name: str) -> int:
    if state_name == "order_status_created":
        return random.randint(1000, 12000)
    if state_name == "delivery_status_assigned":
        return random.randint(5000, 90000)
    if state_name == "delivery_status_delivered":
        return random.randint(12 * 60 * 1000, 70 * 60 * 1000)
    if state_name == "refund_status_completed":
        return random.randint(30 * 1000, 6 * 60 * 60 * 1000)
    return random.randint(1000, 60000)


def build_state_events(ctx: JourneyContext, profile: dict[str, Any], anomaly: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    target_events = set(anomaly.get("target_state_events", []))
    drop_rate = float(anomaly.get("state_drop_rate", 0.0))
    mismatch_rate = float(anomaly.get("coupon_state_mismatch_rate", 0.0))
    candidates: list[str] = []
    if ctx.has_order:
        candidates.append("order_status_created")
    if ctx.has_delivery:
        candidates.append("delivery_status_assigned")
        candidates.append("delivery_status_delivered")
    if ctx.has_refund:
        candidates.append("refund_status_completed")

    last_ts = ctx.created_at
    for seq, state_name in enumerate(candidates):
        if (not target_events or state_name in target_events) and random.random() < drop_rate:
            continue
        anchor_ts, anchor_offset = _stage_time(ctx, _anchor_stage(state_name), 90 + seq * 60)
        delay_ms = _delay_ms(state_name)
        ts = anchor_ts + timedelta(milliseconds=delay_ms)
        if ts <= last_ts:
            ts = last_ts + timedelta(milliseconds=random.randint(1000, 9000))
        last_ts = ts
        state_amount = ctx.final_amount
        if state_name == "order_status_created" and ctx.coupon_id and random.random() < mismatch_rate:
            state_amount = ctx.base_price
        events.append(
            {
                "event_time": ts.isoformat(),
                "profile_id": ctx.profile_id,
                "journey_id": ctx.journey_id,
                "state_event": state_name,
                "customer_id": ctx.customer_id,
                "order_id": ctx.order_id,
                "payment_id": ctx.payment_id,
                "delivery_id": ctx.delivery_id,
                "coupon_id": ctx.coupon_id,
                "order_amount": state_amount,
                "expected_amount": ctx.final_amount,
                "state_status": state_name.replace("_status_", ":"),
                "source_system": "commerce_state_store",
                "behavior_anchor_stage": _anchor_stage(state_name),
                "behavior_anchor_offset_sec": anchor_offset,
                "state_transition_delay_ms": delay_ms,
                "anomaly_flag": bool(anomaly and anomaly.get("anomaly_type", "none") != "none"),
            }
        )
    return events
