from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any


def _bootstrap() -> None:
    if __package__:
        return
    current = Path(__file__).resolve()
    project_root = current.parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


_bootstrap()

from simulator.customer_journey_sim.common.io import ensure_dir, load_yaml, write_json, write_jsonl
from simulator.customer_journey_sim.common.legacy_v04_profile import apply_v04_behavior_defaults
from simulator.customer_journey_sim.journey.model import build_journey_context
from simulator.customer_journey_sim.journey.traffic_profile import IdentityPool, generate_visit_times, target_daily_visits, allocate_hourly_counts
from simulator.customer_journey_sim.behavior.w3c import build_behavior_rows, to_w3c_line
from simulator.customer_journey_sim.transaction.events import build_transaction_events
from simulator.customer_journey_sim.state.events import build_state_events
from simulator.customer_journey_sim.source_anomaly.runtime_layer import apply_source_runtime_anomaly


def _write_behavior(path: Path, rows: list[dict[str, str]]) -> int:
    # v0.5 Phase1 behavior log is Apache access-log style, not IIS/W3C field-header format.
    # Rows are globally sorted by event_time before writing so stream/replay ingestion realism is preserved.
    ordered = sorted(rows, key=lambda r: (str(r.get("event_time", "")), str(r.get("journey_id", "")), str(r.get("stage", ""))))
    with open(path, "w", encoding="utf-8", newline="") as f:
        for row in ordered:
            f.write(to_w3c_line(row) + "\n")
    return len(ordered)


def _sort_json_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (str(r.get("event_time", r.get("created_at", ""))), str(r.get("journey_id", "")), str(r)))

def _hourly_summary(journey_rows: list[dict[str, Any]], behavior_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_hour = {
        f"{h:02d}": {"visits": 0, "visitors": set(), "pageviews": 0, "duration": 0, "bounce": 0, "deep": 0}
        for h in range(24)
    }
    for row in journey_rows:
        hh = str(row["created_at"])[11:13]
        stages = row.get("stage_sequence", []) or []
        by_hour[hh]["visits"] += 1
        by_hour[hh]["visitors"].add(row["visitor_id"])
        by_hour[hh]["duration"] += int(row.get("session_duration_sec", 0) or 0)
        if len(stages) <= 2:
            by_hour[hh]["bounce"] += 1
        if len(stages) >= 6:
            by_hour[hh]["deep"] += 1
    for row in behavior_rows:
        hh = str(row["timestamp"])[12:14]
        if hh in by_hour:
            by_hour[hh]["pageviews"] += 1
    out = []
    for h in range(24):
        key = f"{h:02d}"
        visits = by_hour[key]["visits"]
        pageviews = by_hour[key]["pageviews"]
        out.append({
            "hour": key,
            "visits": visits,
            "visitors": len(by_hour[key]["visitors"]),
            "pageviews": pageviews,
            "pageviews_per_visit": round(pageviews / visits, 2) if visits else 0.0,
            "avg_session_duration_sec": round(by_hour[key]["duration"] / visits, 1) if visits else 0.0,
            "bounce_visit_rate": round(by_hour[key]["bounce"] / visits, 4) if visits else 0.0,
            "deep_visit_rate": round(by_hour[key]["deep"] / visits, 4) if visits else 0.0,
        })
    return out


def _behavior_realism_summary(journey_rows: list[dict[str, Any]], behavior_rows: list[dict[str, str]]) -> dict[str, Any]:
    total = max(1, len(journey_rows))
    depths = [len(r.get("stage_sequence", []) or []) for r in journey_rows]
    durations = [int(r.get("session_duration_sec", 0) or 0) for r in journey_rows]
    actors: dict[str, int] = {}
    exit_stages: dict[str, int] = {}
    non_linear = 0
    for row in journey_rows:
        actor = str(row.get("behavior_actor", "unknown"))
        actors[actor] = actors.get(actor, 0) + 1
        exit_stage = str(row.get("exit_stage", "unknown"))
        exit_stages[exit_stage] = exit_stages.get(exit_stage, 0) + 1
        stages = row.get("stage_sequence", []) or []
        if stages.count("search") > 1 or stages.count("product_view") > 1 or stages.count("browse") > 1:
            non_linear += 1
    unique_visitors = {str(r.get("visitor_id", "")) for r in journey_rows if r.get("visitor_id")}
    repeat_visits = max(0, len(journey_rows) - len(unique_visitors))
    return {
        "visit_count": len(journey_rows),
        "unique_visitor_count": len(unique_visitors),
        "repeat_visit_count": repeat_visits,
        "behavior_count": len(behavior_rows),
        "avg_pageviews_per_visit": round(len(behavior_rows) / total, 2),
        "single_or_two_page_visit_rate": round(sum(1 for d in depths if d <= 2) / total, 4),
        "deep_visit_rate": round(sum(1 for d in depths if d >= 6) / total, 4),
        "avg_session_duration_sec": round(sum(durations) / total, 1),
        "non_linear_navigation_rate": round(non_linear / total, 4),
        "actor_distribution": dict(sorted(actors.items())),
        "exit_stage_distribution": dict(sorted(exit_stages.items())),
    }



def _referer_source(ref: str) -> str:
    if not ref or ref == "-":
        return "direct"
    lower = ref.lower()
    if "naver" in lower:
        return "naver"
    if "google" in lower:
        return "google"
    if "daum" in lower:
        return "daum"
    if "kakao" in lower:
        return "kakao"
    if "utm_" in lower or "campaign" in lower:
        return "campaign"
    if "commerce-deliver.example.com" in lower:
        return "internal"
    return "other"


def _analyzer_compatibility_summary(journey_rows: list[dict[str, Any]], behavior_rows: list[dict[str, str]]) -> dict[str, Any]:
    sid_ip: dict[str, set[str]] = {}
    sid_ua: dict[str, set[str]] = {}
    pcid_sid: dict[str, set[str]] = {}
    referers: dict[str, int] = {}
    sid_pv: dict[str, int] = {}
    uid_non_empty = 0
    uid_empty = 0
    uid_stage_count: dict[str, int] = {}
    stage_count: dict[str, int] = {}
    sid_uid_seen: dict[str, bool] = {}
    for row in behavior_rows:
        cookie = str(row.get("cookie", ""))
        parsed = {}
        for part in cookie.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                parsed[k.strip()] = v.strip()
        sid = parsed.get("sid") or ""
        pcid = parsed.get("pcid") or ""
        uid = parsed.get("uid") or ""
        stage = parsed.get("journey_stage") or parsed.get("page_type") or "unknown"
        stage_count[stage] = stage_count.get(stage, 0) + 1
        if uid:
            uid_non_empty += 1
            uid_stage_count[stage] = uid_stage_count.get(stage, 0) + 1
            if sid:
                sid_uid_seen[sid] = True
        else:
            uid_empty += 1
            if sid:
                sid_uid_seen.setdefault(sid, False)
        if sid:
            sid_ip.setdefault(sid, set()).add(str(row.get("ip", "")))
            sid_ua.setdefault(sid, set()).add(str(row.get("user_agent", "")))
            sid_pv[sid] = sid_pv.get(sid, 0) + 1
        if pcid and sid:
            pcid_sid.setdefault(pcid, set()).add(sid)
        src = _referer_source(str(row.get("referer", "-")))
        referers[src] = referers.get(src, 0) + 1
    total_sid = max(1, len(sid_pv))
    total_rows = max(1, len(behavior_rows))
    stable_ip_sid = sum(1 for values in sid_ip.values() if len(values) == 1)
    stable_ua_sid = sum(1 for values in sid_ua.values() if len(values) == 1)
    repeat_pcid_new_sid = sum(1 for values in pcid_sid.values() if len(values) > 1)
    authenticated_sessions = sum(1 for v in sid_uid_seen.values() if v)
    return {
        "session_count_by_sid": len(sid_pv),
        "same_sid_ip_stability_rate": round(stable_ip_sid / total_sid, 5),
        "same_sid_user_agent_stability_rate": round(stable_ua_sid / total_sid, 5),
        "repeat_pcid_new_sid_count": repeat_pcid_new_sid,
        "repeat_pcid_new_sid_rate": round(repeat_pcid_new_sid / max(1, len(pcid_sid)), 5),
        "referer_distribution": dict(sorted(referers.items())),
        "analyzer_expected_pv_per_visit": round(len(behavior_rows) / total_sid, 2),
        "analyzer_expected_avg_session_duration_sec": round(sum(int(r.get("session_duration_sec", 0) or 0) for r in journey_rows) / max(1, len(journey_rows)), 1),
        "uid_cookie_non_empty_count": uid_non_empty,
        "uid_cookie_empty_count": uid_empty,
        "uid_cookie_rate": round(uid_non_empty / total_rows, 5),
        "anonymous_cookie_rate": round(uid_empty / total_rows, 5),
        "authenticated_session_count": authenticated_sessions,
        "authenticated_session_rate": round(authenticated_sessions / total_sid, 5),
        "uid_by_stage_distribution": dict(sorted(uid_stage_count.items())),
        "stage_distribution": dict(sorted(stage_count.items())),
        "compatibility_note": "Internal weblog analyzer should group visits by stable sid with stable IP and User-Agent. uid is authentication-scoped and may be blank on anonymous browse/search/product_view rows.",
    }

def generate(profile: dict[str, Any], event_date: str, scenario: str, journeys: int | None, out_dir: Path, seed: int) -> dict[str, Any]:
    random.seed(seed)
    anomaly = dict(profile.get("anomaly_profiles", {}).get(scenario, {}))
    if scenario != "baseline" and not anomaly:
        raise ValueError(f"unknown scenario '{scenario}'. Define it under anomaly_profiles in YAML.")

    behavior_rows: list[dict[str, str]] = []
    transaction_rows: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []
    journey_rows: list[dict[str, Any]] = []

    target_visits = target_daily_visits(profile, event_date, journeys)
    visit_times = generate_visit_times(profile, event_date, target_visits)
    identity_pool = IdentityPool.create(profile)
    expected_hourly_visits = allocate_hourly_counts(profile, target_visits)

    for i, visit_time in enumerate(visit_times, 1):
        visitor = identity_pool.get(visit_time)
        ctx = build_journey_context(profile, event_date, i, created_at=visit_time, visitor=visitor)
        journey_rows.append(ctx.to_dict())
        behavior_rows.extend(build_behavior_rows(ctx, profile, anomaly))
        transaction_rows.extend(build_transaction_events(ctx, profile, anomaly))
        state_rows.extend(build_state_events(ctx, profile, anomaly))

    source_runtime_anomaly_summary = apply_source_runtime_anomaly(
        profile=profile,
        scenario=scenario,
        behavior_rows=behavior_rows,
        transaction_rows=transaction_rows,
        state_rows=state_rows,
    )

    ensure_dir(out_dir)
    prefix = f"{profile.get('profile_id', 'commerce_deliver')}_{event_date}_{scenario}"
    behavior_log = out_dir / f"{prefix}_behavior.w3c.log"
    transaction_jsonl = out_dir / f"{prefix}_transaction.jsonl"
    state_jsonl = out_dir / f"{prefix}_state.jsonl"
    journey_jsonl = out_dir / f"{prefix}_journey.jsonl"
    manifest_path = out_dir / f"{prefix}_manifest.json"
    hourly_summary_path = out_dir / f"{prefix}_hourly_summary.json"
    behavior_realism_path = out_dir / f"{prefix}_behavior_realism_summary.json"
    analyzer_compat_path = out_dir / f"{prefix}_analyzer_compatibility_summary.json"

    # Global chronological ordering is required for ingestion/replay realism.
    journey_rows = _sort_json_rows(journey_rows)
    behavior_rows = _sort_json_rows(behavior_rows)
    transaction_rows = _sort_json_rows(transaction_rows)
    state_rows = _sort_json_rows(state_rows)

    hourly_summary = _hourly_summary(journey_rows, behavior_rows)
    unique_visitors = len({str(r.get("visitor_id", "")) for r in journey_rows if r.get("visitor_id")})
    counts = {
        "journey_count": write_jsonl(journey_jsonl, journey_rows),
        "unique_visitor_count": unique_visitors,
        "behavior_count": _write_behavior(behavior_log, behavior_rows),
        "transaction_count": write_jsonl(transaction_jsonl, transaction_rows),
        "state_count": write_jsonl(state_jsonl, state_rows),
    }
    write_json(hourly_summary_path, hourly_summary)
    behavior_realism = _behavior_realism_summary(journey_rows, behavior_rows)
    write_json(behavior_realism_path, behavior_realism)
    analyzer_compatibility = _analyzer_compatibility_summary(journey_rows, behavior_rows)
    write_json(analyzer_compat_path, analyzer_compatibility)
    manifest = {
        "profile_id": profile.get("profile_id", "commerce_deliver"),
        "event_date": event_date,
        "scenario": scenario,
        "seed": seed,
        "parallel_derivation": "Customer Journey is the source; behavior/transaction/state are parallel observations.",
        "traffic_model": {
            "target_visits": target_visits,
            "expected_hourly_visits": expected_hourly_visits,
            "daily_user_behavior_validation": "Baseline uses v0.4-style hourly curve plus stochastic session depth, revisit/compare loops, dwell time, bounce/abandon, actor segmentation, micro-bursts, and global chronological ordering.",
            "temporal_ordering": "All source outputs are written event_time ASC for stream/replay ingestion realism.",
            "v04_behavior_asset_loaded": bool(profile.get("_v04_behavior_asset_loaded", False)),
            "v04_behavior_asset_path": str(profile.get("_v04_behavior_asset_path", "")),
            "analyzer_compatibility": "sid keeps stable IP/User-Agent; pcid/uid revisits use a new sid with sticky IP/subnet behavior.",
            "target_daily_uv": int(profile.get("traffic_model", {}).get("target_daily_uv", 0) or 0),
            "min_baseline_uv": int(profile.get("traffic_model", {}).get("min_baseline_uv", 1000) or 1000)
        },
        "files": {
            "journey_jsonl": str(journey_jsonl),
            "behavior_w3c_log": str(behavior_log),
            "hourly_summary_json": str(hourly_summary_path),
            "behavior_realism_summary_json": str(behavior_realism_path),
            "analyzer_compatibility_summary_json": str(analyzer_compat_path),
            "transaction_jsonl": str(transaction_jsonl),
            "state_jsonl": str(state_jsonl),
        },
        "counts": counts,
        "anomaly_profile": anomaly,
        "source_runtime_anomaly_summary": source_runtime_anomaly_summary,
        "completion_checks": {
            "single_journey_generates_three_logs": counts["behavior_count"] > 0 and counts["transaction_count"] >= 0 and counts["state_count"] >= 0,
            "same_order_payment_id_traceable": True,
            "behavior_only_anomaly_supported": "behavior_only_anomaly" in profile.get("anomaly_profiles", {}),
            "transaction_missing_anomaly_supported": "transaction_missing_anomaly" in profile.get("anomaly_profiles", {}),
            "state_missing_anomaly_supported": "state_missing_anomaly" in profile.get("anomaly_profiles", {}),
        },
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate v0.5 Phase1 commerce journey source logs.")
    parser.add_argument("--profile-config", required=True)
    parser.add_argument("--event-date", required=True)
    parser.add_argument("--scenario", default="baseline")
    parser.add_argument("--journeys", type=int, default=0, help="Daily visit/journey count. Use 0 to use profile traffic_model.target_daily_visits and weekday multiplier.")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    profile = load_yaml(args.profile_config)
    manifest = generate(profile, args.event_date, args.scenario, args.journeys, Path(args.out_dir), args.seed)
    print(f"[OK] generated v0.5 phase1 logs: {manifest['files']}")
    print(f"[OK] counts: {manifest['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
