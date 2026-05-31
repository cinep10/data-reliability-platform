from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _weighted_pairs_to_items(pairs: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(pairs, list):
        return out
    for item in pairs:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append({"name": str(item[0]), "weight": float(item[1])})
        elif isinstance(item, dict):
            name = item.get("name") or item.get("value") or item.get("device")
            if name is not None:
                out.append({"name": str(name), "weight": float(item.get("weight", 1.0))})
    return out


def _candidate_paths(project_root: Path, explicit: str | None = None) -> list[Path]:
    paths: list[Path] = []
    if explicit:
        paths.append(Path(explicit).expanduser())
    paths.extend([
        project_root / "simulator" / "weblog_sim" / "configs" / "legacy_v04" / "profiles" / "finance_bank.yaml",
        project_root / "simulator" / "weblog_sim" / "configs" / "profiles" / "finance_bank.yaml",
        project_root / "configs" / "profiles" / "finance_bank.yaml",
    ])
    return paths


def apply_v04_behavior_defaults(profile: dict[str, Any], profile_config_path: str | Path) -> dict[str, Any]:
    """Apply v0.4 weblog simulator behavior realism settings to v0.5 commerce profile.

    v0.5 keeps commerce URL/query/cookie semantics, but the human behavior model must reuse
    the v0.4 simulator assets for UA pools, device mix, visit/revisit ratio, session/PV model,
    traffic curve, and identity stickiness. This bridge makes that dependency explicit and
    records the loaded source path in the manifest.
    """
    cfg = dict(profile)
    bridge = cfg.get("v04_behavior_asset_bridge", {}) or {}
    if not bridge.get("enabled", True):
        cfg["_v04_behavior_asset_loaded"] = False
        return cfg

    root = Path(profile_config_path).resolve().parents[3]
    explicit = bridge.get("profile_path")
    legacy_profile: dict[str, Any] | None = None
    loaded_path: Path | None = None
    for path in _candidate_paths(root, explicit):
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                legacy_profile = yaml.safe_load(f) or {}
            loaded_path = path
            break
    if not legacy_profile:
        cfg["_v04_behavior_asset_loaded"] = False
        return cfg

    scenario = legacy_profile.get("scenario", legacy_profile) or {}
    traffic = dict(cfg.get("traffic_model", {}) or {})

    # v0.4 traffic/user behavior calibration knobs reused directly.
    for key in [
        "new_visit_ratio_by_hh",
        "revisit_ratio_by_hh",
        "session_event_rate_by_hh",
        "target_pv_per_visit_mean",
        "target_pv_per_visit_std",
        "max_pageviews_per_session",
        "session_event_rate",
        "revisit_ratio_daily",
        "pcid_reuse",
        "pcid_uid_stickiness",
        "uid_rate",
        "uid_acquire_half_life_sessions",
    ]:
        if key in scenario:
            traffic[key] = scenario[key]
    if "weekday_multiplier" in scenario:
        traffic["weekday_multiplier"] = scenario["weekday_multiplier"]
    # Prefer explicit v0.5 hourly weights if set, otherwise derive from v0.4 traffic_curve.
    if bridge.get("use_v04_hourly_curve", True) and "traffic_curve" in scenario:
        hh = (scenario.get("traffic_curve") or {}).get("hh_multiplier")
        if isinstance(hh, list) and len(hh) == 24 and sum(float(x) for x in hh) > 0:
            total = sum(float(x) for x in hh)
            traffic["hourly_visit_weights"] = [round(float(x) / total, 8) for x in hh]
    cfg["traffic_model"] = traffic

    # Device and UA pools are v0.4 assets. Commerce uses them with commerce pages.
    device_items = _weighted_pairs_to_items(scenario.get("device_weights"))
    if device_items:
        cfg["device_types"] = device_items
    if scenario.get("uas_mobile"):
        cfg["uas_mobile"] = [str(x[0]) if isinstance(x, (list, tuple)) else str(x) for x in scenario["uas_mobile"]]
    if scenario.get("uas_desktop"):
        cfg["uas_desktop"] = [str(x[0]) if isinstance(x, (list, tuple)) else str(x) for x in scenario["uas_desktop"]]
    if scenario.get("countries"):
        cfg["countries"] = scenario["countries"]
    if scenario.get("accept_lang_by_country"):
        cfg["accept_lang_by_country"] = scenario["accept_lang_by_country"]
    if scenario.get("event_mix_default"):
        cfg["event_mix_default"] = scenario["event_mix_default"]
    if scenario.get("event_mix_by_page_type"):
        cfg["event_mix_by_page_type"] = scenario["event_mix_by_page_type"]

    cfg["_v04_behavior_asset_loaded"] = True
    cfg["_v04_behavior_asset_path"] = str(loaded_path)
    return cfg
