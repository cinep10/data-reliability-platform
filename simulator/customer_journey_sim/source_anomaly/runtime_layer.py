from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any
import random
import re


_COOKIE_PAIR_RE = re.compile(r"(?P<key>[^=;\s]+)=(?P<value>[^;]*);?")


def _parse_cookie(cookie: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for match in _COOKIE_PAIR_RE.finditer(cookie or ""):
        pairs[match.group("key").strip()] = match.group("value").strip()
    return pairs


def _format_cookie(pairs: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in pairs.items()) + ";"


def _set_cookie(row: dict[str, str], updates: dict[str, Any]) -> None:
    pairs = _parse_cookie(str(row.get("cookie", "")))
    for key, value in updates.items():
        pairs[str(key)] = str(value)
    row["cookie"] = _format_cookie(pairs)


def _get_cookie(row: dict[str, str], key: str, default: str = "") -> str:
    return _parse_cookie(str(row.get("cookie", ""))).get(key, default)


def _set_event_time(row: dict[str, str], new_ts: datetime) -> None:
    # Behavior source log uses both ISO event_time and Apache timestamp.
    row["event_time"] = new_ts.isoformat()
    row["timestamp"] = new_ts.strftime("%d/%b/%Y:%H:%M:%S +0900")


def _parse_event_time(row: dict[str, str]) -> datetime | None:
    raw = str(row.get("event_time", ""))
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _is_behavior_row_target(row: dict[str, str], target_stages: set[str]) -> bool:
    stage = str(row.get("stage") or _get_cookie(row, "journey_stage") or "")
    return (not target_stages) or stage in target_stages


def _apply_batch_distribution_distortion(
    behavior_rows: list[dict[str, str]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Distort behavior source semantics while keeping rows physically valid.

    This is intentionally applied to source behavior rows before file writing.
    It does not mutate stage/canonical/measurement tables.
    """

    target_stages = set(cfg.get("target_stages", ["browse", "search", "product_view"]))
    ratio = float(cfg.get("page_type_distortion_rate", 0.35))
    forced_page_type = str(cfg.get("forced_page_type", "promo_shadow"))
    forced_stage = str(cfg.get("forced_journey_stage", forced_page_type))
    forced_referer = str(cfg.get("forced_referer", "https://m.commerce-deliver.example.com/event/runtime-layer-test?utm_source=campaign&utm_medium=push"))
    affected = 0

    for row in behavior_rows:
        if not _is_behavior_row_target(row, target_stages):
            continue
        if random.random() >= ratio:
            continue
        # Keep the raw hit parseable, but distort source semantics used by batch mapping/distribution.
        row["uri"] = f"/event/runtime-layer-test.do?journey_stage={forced_stage}&source_anomaly=batch_asset"
        row["referer"] = forced_referer
        _set_cookie(row, {
            "page_type": forced_page_type,
            "journey_stage": forced_stage,
            "funnel_stage": forced_stage,
            "source_layer": "behavior",
            "anomaly_type": "batch_asset_distribution_distortion",
            "drift": "on",
            "affected": "1",
            "campaign_flag": "runtime_batch_asset_test",
            "reconciliation_flag": "batch_distribution_distortion",
        })
        affected += 1

    return {"batch_distribution_distorted_rows": affected}


def _apply_stream_source_anomaly(
    behavior_rows: list[dict[str, str]],
    cfg: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Inject duplicate/drop/skew at behavior source level.

    The downstream batch/stream layers should observe this through normal ingestion.
    """

    target_stages = set(cfg.get("target_stages", ["product_view", "add_cart", "checkout", "payment"]))
    duplicate_rate = float(cfg.get("source_duplicate_rate", 0.04))
    drop_rate = float(cfg.get("source_drop_rate", 0.015))
    skew_rate = float(cfg.get("event_time_skew_rate", 0.03))
    skew_seconds = int(cfg.get("event_time_skew_seconds", 900))

    out: list[dict[str, str]] = []
    dropped = 0
    duplicated = 0
    skewed = 0

    for row in behavior_rows:
        target = _is_behavior_row_target(row, target_stages)
        if target and random.random() < drop_rate:
            dropped += 1
            continue

        new_row = deepcopy(row)
        if target and random.random() < skew_rate:
            ts = _parse_event_time(new_row)
            if ts is not None:
                shifted = ts + timedelta(seconds=random.choice([-1, 1]) * skew_seconds)
                # Keep source log inside the same calendar day for file partition realism.
                day_start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = ts.replace(hour=23, minute=59, second=59, microsecond=0)
                shifted = max(day_start, min(day_end, shifted))
                _set_event_time(new_row, shifted)
                _set_cookie(new_row, {
                    "anomaly_type": "stream_source_ordering_duplicate_distortion",
                    "drift": "on",
                    "affected": "1",
                    "event_time_skew_ms": str(skew_seconds * 1000),
                    "reconciliation_flag": "stream_source_distortion",
                })
                skewed += 1
        out.append(new_row)

        if target and random.random() < duplicate_rate:
            dup = deepcopy(new_row)
            _set_cookie(dup, {
                "anomaly_type": "stream_source_duplicate_distortion",
                "drift": "on",
                "affected": "1",
                "duplicate_multiplier": "2.0",
                "reconciliation_flag": "stream_duplicate_distortion",
            })
            out.append(dup)
            duplicated += 1

    return out, {"source_dropped_rows": dropped, "source_duplicated_rows": duplicated, "source_time_skewed_rows": skewed}


def _apply_operational_source_anomaly(
    behavior_rows: list[dict[str, str]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Inject operational symptoms into source logs: status/latency/backlog/microburst.

    This keeps the experiment source-level. Downstream operational measurement observes
    status, throughput, and timing via normal ingestion/replay paths.
    """

    target_stages = set(cfg.get("target_stages", ["checkout", "payment", "order_complete"]))
    error_rate = float(cfg.get("http_error_rate", 0.10))
    latency_rate = float(cfg.get("latency_injection_rate", 0.18))
    latency_ms = int(cfg.get("latency_ms", 4500))
    microburst_rate = float(cfg.get("microburst_rate", 0.05))
    burst_minute = int(cfg.get("microburst_minute", 12 * 60 + 10))

    errors = 0
    latency = 0
    microburst = 0

    for row in behavior_rows:
        if not _is_behavior_row_target(row, target_stages):
            continue

        updates: dict[str, Any] = {}
        if random.random() < error_rate:
            row["status"] = "503"
            updates.update({
                "http_status": "503",
                "system_flag": "runtime_operational_degraded",
                "anomaly_type": "operational_source_availability_distortion",
                "drift": "on",
                "affected": "1",
                "reconciliation_flag": "operational_availability_distortion",
            })
            errors += 1

        if random.random() < latency_rate:
            updates.update({
                "latency_ms": str(latency_ms),
                "event_ingestion_delay_ms": str(latency_ms),
                "timeout_multiplier": "3.0",
                "backlog_flush": "1",
                "system_flag": "runtime_operational_degraded",
                "anomaly_type": "operational_source_latency_distortion",
                "drift": "on",
                "affected": "1",
            })
            latency += 1

        if random.random() < microburst_rate:
            ts = _parse_event_time(row)
            if ts is not None:
                burst_ts = ts.replace(hour=burst_minute // 60, minute=burst_minute % 60, second=random.randint(0, 59), microsecond=0)
                _set_event_time(row, burst_ts)
                updates.update({
                    "backlog_flush": "1",
                    "system_flag": "runtime_operational_microburst",
                    "anomaly_type": "operational_source_throughput_distortion",
                    "drift": "on",
                    "affected": "1",
                    "reconciliation_flag": "operational_throughput_distortion",
                })
                microburst += 1

        if updates:
            _set_cookie(row, updates)

    return {"operational_http_error_rows": errors, "operational_latency_rows": latency, "operational_microburst_rows": microburst}


def apply_source_runtime_anomaly(
    profile: dict[str, Any],
    scenario: str,
    behavior_rows: list[dict[str, str]],
    transaction_rows: list[dict[str, Any]],
    state_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply v0.5 source-log anomaly scenarios before source files are written.

    Portfolio rule:
      - Do not mutate stage/canonical/measurement/runtime tables for anomaly tests.
      - All anomaly evidence must originate in generated source logs.

    Existing transaction/state scenarios still use the configured transaction/state
    generators. The three runtime-layer scenarios below only alter generated source
    files before persistence.
    """

    anomaly = dict(profile.get("anomaly_profiles", {}).get(scenario, {}))
    cfg = dict(anomaly.get("source_runtime_anomaly", {}) or {})
    mode = str(cfg.get("mode", "none"))

    if mode in {"", "none"}:
        return {
            "source_runtime_anomaly_applied": False,
            "mode": mode,
            "behavior_rows_before": len(behavior_rows),
            "behavior_rows_after": len(behavior_rows),
            "transaction_rows": len(transaction_rows),
            "state_rows": len(state_rows),
        }

    stats: dict[str, Any] = {
        "source_runtime_anomaly_applied": True,
        "mode": mode,
        "behavior_rows_before": len(behavior_rows),
        "transaction_rows": len(transaction_rows),
        "state_rows": len(state_rows),
    }

    if mode in {"batch_only", "batch_stream", "batch_stream_operational"}:
        stats.update(_apply_batch_distribution_distortion(behavior_rows, cfg))

    if mode in {"batch_stream", "batch_stream_operational"}:
        mutated, stream_stats = _apply_stream_source_anomaly(behavior_rows, cfg)
        behavior_rows[:] = mutated
        stats.update(stream_stats)

    if mode == "batch_stream_operational":
        stats.update(_apply_operational_source_anomaly(behavior_rows, cfg))

    stats["behavior_rows_after"] = len(behavior_rows)
    return stats
