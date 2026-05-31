#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, json, random, re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

REQUEST_RE = re.compile(r'(?P<prefix>^.*?\")(?P<method>[A-Z]+)\s+(?P<uri>\S+)\s+(?P<proto>HTTP/[0-9.]+)(?P<suffix>\".*$)')
TS_RE = re.compile(r'\[(?P<ts>[0-9]{2}/[A-Za-z]{3}/[0-9]{4}:[0-9]{2}:[0-9]{2}:[0-9]{2}\s+[+-][0-9]{4})\]')
COOKIE_RE = re.compile(r'"(?P<cookie>[^"\n]*(?:pcid=|sid=|uid=)[^"\n]*)"\s*$')
ALL_MODES = [
    "batch_asset_anomaly", "batch_stream_anomaly", "batch_stream_operational_anomaly",
    "source_campaign_spike", "source_weather_drop", "source_system_degraded",
    "source_partial_missing", "source_latency_degradation", "source_identity_drift", "source_schema_drift",
]

def parse_ts(line: str) -> Optional[dt.datetime]:
    m = TS_RE.search(line)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group("ts"), "%d/%b/%Y:%H:%M:%S %z")
    except Exception:
        return None

def replace_ts(line: str, new_ts: dt.datetime) -> str:
    m = TS_RE.search(line)
    if not m:
        return line
    s = new_ts.strftime("%d/%b/%Y:%H:%M:%S %z")
    return line[:m.start("ts")] + s + line[m.end("ts"):]

def find_behavior_log(input_dir: Path, profile_id: str, event_date: str, scenario_name: str, source_generation_scenario: str) -> Path:
    candidates = [
        input_dir / f"{profile_id}_{event_date}_{scenario_name}_behavior.w3c.log",
        input_dir / f"{profile_id}_{event_date}_{source_generation_scenario}_behavior.w3c.log",
    ]
    for p in candidates:
        if p.exists():
            return p
    for manifest_name in [
        f"{profile_id}_{event_date}_{scenario_name}_manifest.json",
        f"{profile_id}_{event_date}_{source_generation_scenario}_manifest.json",
    ]:
        manifest = input_dir / manifest_name
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                outs = data.get("outputs", data)
                for key in ("behavior_w3c_log", "behavior_apache_log", "behavior_log"):
                    val = outs.get(key)
                    if val and Path(val).exists():
                        return Path(val)
            except Exception:
                pass
    cands = sorted(input_dir.glob("*behavior*.log"))
    if not cands:
        raise FileNotFoundError(f"behavior log not found in {input_dir}")
    return cands[0]

def make_uri(uri: str, page_type: str, extra: Dict[str, str]) -> str:
    parts = urlsplit(uri)
    path = parts.path or "/view.do"
    if not path.endswith(".do"):
        path = "/eventView.do"
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.update(extra)
    q["v05_page_type"] = page_type
    q.setdefault("journey_stage", page_type)
    return urlunsplit(("", "", path, urlencode(q, doseq=True), ""))

def replace_uri(line: str, new_uri: str) -> str:
    m = REQUEST_RE.search(line)
    if not m:
        return line
    return f"{m.group('prefix')}{m.group('method')} {new_uri} {m.group('proto')}{m.group('suffix')}"

def mutate_status(line: str, status: str) -> str:
    return re.sub(r'(")\s+[0-9]{3}\s+', rf'\1 {status} ', line, count=1)

def cookie_pairs(cookie: str) -> Dict[str, str]:
    out = {}
    for part in cookie.split(';'):
        if '=' in part:
            k, v = part.strip().split('=', 1)
            out[k.strip()] = v.strip()
    return out

def render_cookie(pairs: Dict[str, str]) -> str:
    return '; '.join(f"{k}={v}" for k, v in pairs.items()) + ';'

def add_cookie_flags(line: str, flags: Dict[str, str]) -> str:
    raw = line.rstrip('\n')
    newline = '\n' if line.endswith('\n') else ''
    m = COOKIE_RE.search(raw)
    if not m:
        m2 = REQUEST_RE.search(raw)
        uri = m2.group("uri") if m2 else "/view.do"
        return replace_uri(line, make_uri(uri, "sourceAnomaly", flags))
    pairs = cookie_pairs(m.group('cookie'))
    pairs.update(flags)
    new_cookie = render_cookie(pairs)
    return raw[:m.start('cookie')] + new_cookie + raw[m.end('cookie'):] + newline

def pick_indices(n: int, ratio: float, rng: random.Random) -> set[int]:
    if n <= 0 or ratio <= 0:
        return set()
    k = min(n, max(1, int(n * ratio)))
    return set(rng.sample(range(n), k))

def mutation_plan(mode: str):
    plans = {
        "batch_asset_anomaly": {"tag_ratio": 0.28, "duplicate_ratio": 0.0, "drop_ratio": 0.0, "delay_ms": 0, "status_ratio": 0.0, "flags": {"v05_src_anomaly":"batch_asset_anomaly", "source_anomaly":"batch_asset_distribution"}},
        "batch_stream_anomaly": {"tag_ratio": 0.14, "duplicate_ratio": 0.10, "drop_ratio": 0.0, "delay_ms": 45000, "status_ratio": 0.0, "flags": {"v05_src_anomaly":"batch_stream_anomaly", "source_anomaly":"stream_duplicate_delay"}},
        "batch_stream_operational_anomaly": {"tag_ratio": 0.12, "duplicate_ratio": 0.08, "drop_ratio": 0.0, "delay_ms": 45000, "status_ratio": 0.06, "flags": {"v05_src_anomaly":"batch_stream_operational_anomaly", "source_anomaly":"operational_503_latency"}},
        "source_campaign_spike": {"tag_ratio": 0.35, "duplicate_ratio": 0.18, "drop_ratio": 0.0, "delay_ms": 0, "status_ratio": 0.0, "flags": {"exo_source":"source_campaign_spike", "campaign_flag":"commerce_promo", "traffic_actor":"human", "source_anomaly":"campaign_spike"}},
        "source_weather_drop": {"tag_ratio": 0.30, "duplicate_ratio": 0.0, "drop_ratio": 0.08, "delay_ms": 250, "status_ratio": 0.0, "flags": {"exo_source":"source_weather_drop", "weather_type":"rain", "source_anomaly":"weather_drop"}},
        "source_system_degraded": {"tag_ratio": 0.30, "duplicate_ratio": 0.06, "drop_ratio": 0.04, "delay_ms": 900, "status_ratio": 0.05, "flags": {"exo_source":"source_system_degraded", "system_flag":"degraded", "source_anomaly":"system_degraded"}},
        "source_partial_missing": {"tag_ratio": 0.20, "duplicate_ratio": 0.0, "drop_ratio": 0.12, "delay_ms": 0, "status_ratio": 0.0, "flags": {"exo_source":"source_partial_missing", "anomaly_type":"partial_missing", "source_anomaly":"partial_missing"}},
        "source_latency_degradation": {"tag_ratio": 0.22, "duplicate_ratio": 0.0, "drop_ratio": 0.0, "delay_ms": 1200, "status_ratio": 0.0, "flags": {"exo_source":"source_latency_degradation", "anomaly_type":"latency_degradation", "source_anomaly":"latency_degradation"}},
        "source_identity_drift": {"tag_ratio": 0.25, "duplicate_ratio": 0.0, "drop_ratio": 0.0, "delay_ms": 0, "status_ratio": 0.0, "identity_drift": True, "flags": {"exo_source":"source_identity_drift", "identity_flag":"drift", "pcid_stability":"unstable", "source_anomaly":"identity_drift"}},
        "source_schema_drift": {"tag_ratio": 0.25, "duplicate_ratio": 0.0, "drop_ratio": 0.0, "delay_ms": 0, "status_ratio": 0.0, "flags": {"exo_source":"source_schema_drift", "schema_flag":"drift", "schema_version":"v05-commerce-source-contract-drifted", "source_anomaly":"schema_drift"}},
    }
    return plans[mode]

def main() -> int:
    ap = argparse.ArgumentParser(description="Apply v0.5 source-only anomaly mutation to behavior W3C log. No DB table mutation.")
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--event-date", required=True)
    ap.add_argument("--scenario-name", required=True)
    ap.add_argument("--source-generation-scenario", default="baseline")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--mode", required=True, choices=ALL_MODES)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    input_dir = Path(args.input_dir)
    behavior_path = find_behavior_log(input_dir, args.profile_id, args.event_date, args.scenario_name, args.source_generation_scenario)
    lines = [ln for ln in behavior_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if not lines:
        raise SystemExit(f"empty behavior log: {behavior_path}")
    rng = random.Random(args.seed)
    plan = mutation_plan(args.mode)
    n = len(lines)
    dropped = pick_indices(n, float(plan.get("drop_ratio", 0.0)), rng)
    tagged = pick_indices(n, float(plan.get("tag_ratio", 0.0)), rng)
    statuses = pick_indices(n, float(plan.get("status_ratio", 0.0)), rng)
    duplicates = pick_indices(n, float(plan.get("duplicate_ratio", 0.0)), rng)
    mutated: List[str] = []
    dup_lines: List[str] = []
    for i, line in enumerate(lines):
        if i in dropped:
            continue
        new_line = line
        flags = dict(plan["flags"])
        if i in tagged or i in statuses:
            flags["v05_runtime_layer"] = "source"
            flags["v05_source_scenario"] = args.mode
            if plan.get("identity_drift"):
                flags["pcid"] = f"drift_pcid_{i % 997}"
                flags["sid"] = f"drift_sid_{rng.randint(1, 999999)}"
            new_line = add_cookie_flags(new_line, flags)
            m = REQUEST_RE.search(new_line)
            uri = m.group("uri") if m else "/view.do"
            new_line = replace_uri(new_line, make_uri(uri, "sourceAnomaly", flags))
        if i in statuses:
            new_line = mutate_status(new_line, "503")
        delay_ms = int(plan.get("delay_ms", 0) or 0)
        if delay_ms and i in tagged:
            ts = parse_ts(new_line)
            if ts:
                new_line = replace_ts(new_line, ts + dt.timedelta(milliseconds=delay_ms))
        mutated.append(new_line)
        if i in duplicates:
            dup = add_cookie_flags(new_line, {**plan["flags"], "source_duplicate":"1"})
            ts = parse_ts(dup)
            if ts:
                dup = replace_ts(dup, ts + dt.timedelta(seconds=45))
            dup_lines.append(dup)
    mutated.extend(dup_lines)
    mutated.sort(key=lambda ln: parse_ts(ln) or dt.datetime.max.replace(tzinfo=dt.timezone.utc))
    backup = behavior_path.with_suffix(behavior_path.suffix + ".pre_source_anomaly.bak")
    if not backup.exists():
        backup.write_text("\n".join(lines) + "\n", encoding="utf-8")
    behavior_path.write_text("\n".join(mutated) + "\n", encoding="utf-8")
    trace = {
        "profile_id": args.profile_id,
        "target_date": args.event_date,
        "scenario_name": args.scenario_name,
        "source_generation_scenario": args.source_generation_scenario,
        "anomaly_mode": args.mode,
        "source_file": str(behavior_path),
        "source_line_count_before": n,
        "source_line_count_after": len(mutated),
        "dropped_count": len(dropped),
        "tagged_count": len(tagged),
        "duplicated_count": len(dup_lines),
        "status_mutated_count": len(statuses),
        "invariant": "source_log_only_no_mid_table_mutation",
    }
    trace_path = input_dir / f"{args.profile_id}_{args.event_date}_{args.scenario_name}_source_anomaly_trace.json"
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] source-level anomaly injected mode={args.mode} rows_before={n} rows_after={len(mutated)} trace={trace_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
