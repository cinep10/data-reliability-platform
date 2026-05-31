from __future__ import annotations

import argparse
import inspect
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def _bootstrap_imports() -> None:
    """
    Support both:
      1) python -m simulator.weblog_sim.cli
      2) python simulator/weblog_sim/cli.py
    """
    if __package__:
        return

    current = Path(__file__).resolve()
    project_root = current.parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


_bootstrap_imports()

from simulator.weblog_sim.core.generator import WeblogGenerator
from simulator.weblog_sim.core.scenario import ScenarioConfig, PageSpec
from simulator.weblog_sim.core.traffic import WeatherDrift
from simulator.weblog_sim.core.timeutil import KST
from simulator.weblog_sim.meta.store_base import LogFormatMeta


DEFAULT_TEMPLATE = '{ip} - - [{ts}] "{method} {path} {httpv}" {status} {bytes} "{ref}" "{ua}" "{kv}"'


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML must load as dict: {path}")
    return data


def normalize_profile(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    Support both profile formats:

    1) Wrapper style
       site_key: ...
       scenario:
         site_host: ...
         pages: ...

    2) Flat style
       site_key: ...
       site_host: ...
       pages: ...
    """
    if isinstance(raw.get("scenario"), dict):
        scenario_data = dict(raw["scenario"])
        site_key = str(
            raw.get("site_key")
            or scenario_data.get("site_key")
            or scenario_data.get("site_host")
            or "default"
        )
        if "site_key" not in scenario_data:
            scenario_data["site_key"] = site_key
        return site_key, scenario_data

    scenario_data = dict(raw)
    site_key = str(
        scenario_data.get("site_key")
        or scenario_data.get("site_host")
        or raw.get("site_key")
        or "default"
    )
    if "site_key" not in scenario_data:
        scenario_data["site_key"] = site_key
    return site_key, scenario_data


def build_scenario(scenario_data: dict[str, Any]):
    """
    Important:
    - If ScenarioConfig.from_dict exists, pass RAW dict 그대로 넘긴다.
      (from_dict 내부에서 pages -> PageSpec 변환을 수행하는 경우가 많음)
    - from_dict가 없을 때만 로컬에서 PageSpec 변환
    """
    if hasattr(ScenarioConfig, "from_dict"):
        return ScenarioConfig.from_dict(dict(scenario_data))  # type: ignore[attr-defined]

    data = dict(scenario_data)
    pages = data.get("pages")
    if isinstance(pages, list):
        converted = []
        for item in pages:
            if isinstance(item, dict):
                converted.append(PageSpec(**item))
            else:
                converted.append(item)
        data["pages"] = converted

    if hasattr(ScenarioConfig, "parse_obj"):
        return ScenarioConfig.parse_obj(data)  # type: ignore[attr-defined]

    return ScenarioConfig(**data)


def build_drift(scenario_data: dict[str, Any]):
    """
    Build WeatherDrift conservatively from available config.
    """
    exo = scenario_data.get("exogenous", {}) if isinstance(scenario_data.get("exogenous"), dict) else {}
    weather = exo.get("weather_type", scenario_data.get("weather", "none"))
    enabled = bool(exo.get("enabled", scenario_data.get("drift_enabled", weather != "none")))

    attempts = [
        {"weather": weather, "enabled": enabled},
        {"weather": weather},
        {"enabled": enabled},
        {},
    ]
    for kwargs in attempts:
        try:
            return WeatherDrift(**kwargs)
        except TypeError:
            continue
    return WeatherDrift()


def _instantiate_log_meta(site_key: str, scenario_data: dict[str, Any]):
    """
    Build LogFormatMeta defensively because constructor signature may vary by version.
    """
    kwargs = {}
    sig = inspect.signature(LogFormatMeta)

    for name in sig.parameters:
        if name in ("site_key", "key", "name"):
            kwargs[name] = site_key
        elif name in ("template", "line_template", "fmt_template"):
            kwargs[name] = DEFAULT_TEMPLATE
        elif name == "tz":
            kwargs[name] = KST
        elif name in ("http_version", "httpv"):
            kwargs[name] = "HTTP/1.1"
        elif name in ("site_host", "host"):
            kwargs[name] = scenario_data.get("site_host", "www.finance-bank.example.com")

    return LogFormatMeta(**kwargs)


class SimpleMetaStore:
    def __init__(self, site_key: str, scenario_data: dict[str, Any]):
        self._meta = _instantiate_log_meta(site_key, scenario_data)

    def get(self, site_key: str):
        return self._meta


def build_meta_store(site_key: str, scenario_data: dict[str, Any], format_meta_path: str | None):
    """
    Try file-based meta store first if project has one.
    Fallback to a simple in-memory meta store.
    """
    try:
        from simulator.weblog_sim.meta import store_file as sf  # type: ignore

        for cls_name in ("FileMetaStore", "YamlMetaStore", "LocalFileMetaStore"):
            cls = getattr(sf, cls_name, None)
            if cls is None:
                continue

            if format_meta_path:
                try:
                    return cls(format_meta_path)
                except TypeError:
                    pass

                for meth in ("from_yaml", "from_file", "load"):
                    fn = getattr(cls, meth, None)
                    if callable(fn):
                        try:
                            return fn(format_meta_path)
                        except TypeError:
                            continue
    except Exception:
        pass

    return SimpleMetaStore(site_key, scenario_data)


def parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


def generate_logs(
    profile: dict[str, Any],
    start: str,
    end: str,
    avg_rps: float,
    seed: int,
    out_path: str,
    format_meta_path: str | None = None,
) -> int:
    site_key, scenario_data = normalize_profile(profile)
    scenario = build_scenario(scenario_data)
    drift = build_drift(scenario_data)
    meta_store = build_meta_store(site_key, scenario_data, format_meta_path)

    gen = WeblogGenerator(
        scenario=scenario,
        meta_store=meta_store,
        drift=drift,
        seed=seed,
    )

    start_dt = parse_dt(start)
    end_dt = parse_dt(end)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out.open("w", encoding="utf-8") as f:
        for line in gen.generate(start_dt, end_dt, avg_rps=avg_rps, site_key=site_key):
            f.write(line.rstrip("\n") + "\n")
            count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description="Synthetic weblog simulator CLI")
    ap.add_argument("--profile", required=True, help="Path to profile yaml")
    ap.add_argument("--start", required=True, help="Start datetime, e.g. 2026-02-23T00:00:00")
    ap.add_argument("--end", required=True, help="End datetime, e.g. 2026-03-09T23:59:59")
    ap.add_argument("--avg-rps", type=float, default=1.0, help="Average requests per second")
    ap.add_argument("--seed", type=int, default=42, help="Random seed")
    ap.add_argument("--out", required=True, help="Output log path")
    ap.add_argument("--format-meta", default="", help="Optional format meta yaml path")
    args = ap.parse_args()

    profile = load_yaml(args.profile)

    written = generate_logs(
        profile=profile,
        start=args.start,
        end=args.end,
        avg_rps=args.avg_rps,
        seed=args.seed,
        out_path=args.out,
        format_meta_path=(args.format_meta or None),
    )

    print(
        f"[weblog_sim] done profile={Path(args.profile).name} "
        f"start={args.start} end={args.end} avg_rps={args.avg_rps} "
        f"out={args.out} rows={written}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
