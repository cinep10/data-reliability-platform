#!/usr/bin/env python3
"""v0.5 source-level runtime anomaly injector.

Portfolio rule: anomaly tests must mutate source logs only, never staging,
canonical, measurement, analytics, semantic, action, ML, or AI tables.

This module edits generated Phase1 behavior W3C log files before ingestion and
writes a trace artifact next to the source files. Downstream measurement reads
normal pipeline outputs plus this source trace, not mid-table mutations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl, urlencode

REQUEST_RE = re.compile(r'"(?P<method>[A-Z]+) (?P<url>[^" ]+) (?P<proto>HTTP/[0-9.]+)"')
TS_RE = re.compile(r"\[(?P<ts>\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4})\]")
STATUS_RE = re.compile(r'(" [0-9]{3} )')

MONTHS = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

@dataclass
class MutationTrace:
    profile_id: str
    event_date: str
    scenario_name: str
    mode: str
    behavior_log: str
    original_count: int
    final_count: int
    batch_marker_count: int = 0
    stream_marker_count: int = 0
    operational_marker_count: int = 0
    shifted_hour_count: int = 0
    promo_shadow_count: int = 0
    duplicated_count: int = 0
    dropped_count: int = 0
    reordered_count: int = 0
    stream_delay_marker_count: int = 0
    operational_5xx_count: int = 0
    operational_timeout_marker_count: int = 0
    seed: int = 42
    generated_at: str = ""


def stable_ratio(text: str, salt: str = "") -> float:
    h = hashlib.sha256((salt + "|" + text).encode("utf-8", errors="ignore")).hexdigest()
    return int(h[:12], 16) / float(16 ** 12)


def find_behavior_log(input_dir: Path, profile_id: str, event_date: str, scenario_name: str) -> Path:
    preferred = input_dir / f"{profile_id}_{event_date}_{scenario_name}_behavior.w3c.log"
    if preferred.exists():
        return preferred
    matches = sorted(input_dir.glob("*_behavior.w3c.log")) + sorted(input_dir.glob("*behavior*.log"))
    if not matches:
        raise FileNotFoundError(f"No behavior W3C log found under {input_dir}")
    return matches[0]


def add_query_params(url: str, params: dict[str, str]) -> str:
    try:
        parts = urlsplit(url)
        q = dict(parse_qsl(parts.query, keep_blank_values=True))
        q.update(params)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query and urlencode(q) or urlencode(q), parts.fragment))
    except Exception:
        sep = "&" if "?" in url else "?"
        return url + sep + urlencode(params)


def replace_request_url(line: str, new_url: str) -> str:
    m = REQUEST_RE.search(line)
    if not m:
        return line
    repl = f'"{m.group("method")} {new_url} {m.group("proto")}"'
    return line[:m.start()] + repl + line[m.end():]


def update_url(line: str, params: dict[str, str], path_override: Optional[str] = None) -> str:
    m = REQUEST_RE.search(line)
    if not m:
        return line
    url = m.group("url")
    try:
        parts = urlsplit(url)
        path = path_override if path_override else parts.path
        q = dict(parse_qsl(parts.query, keep_blank_values=True))
        q.update(params)
        new_url = urlunsplit((parts.scheme, parts.netloc, path, urlencode(q), parts.fragment))
    except Exception:
        new_url = add_query_params(path_override or url, params)
    return replace_request_url(line, new_url)


def parse_apache_ts(s: str) -> Optional[Tuple[datetime, str]]:
    m = TS_RE.search(s)
    if not m:
        return None
    raw = m.group("ts")
    try:
        # 14/May/2026:00:00:04 +0900
        dt_part, tz = raw.rsplit(" ", 1)
        day = int(dt_part[0:2])
        mon = MONTHS[dt_part[3:6]]
        year = int(dt_part[7:11])
        hour = int(dt_part[12:14])
        minute = int(dt_part[15:17])
        sec = int(dt_part[18:20])
        return datetime(year, mon, day, hour, minute, sec), tz
    except Exception:
        return None


def format_apache_ts(dt: datetime, tz: str) -> str:
    mon = [k for k,v in MONTHS.items() if v == dt.month][0]
    return f"{dt.day:02d}/{mon}/{dt.year}:{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} {tz}"


def shift_to_hour(line: str, hour: int) -> str:
    parsed = parse_apache_ts(line)
    if not parsed:
        return line
    dt, tz = parsed
    new_dt = dt.replace(hour=hour)
    m = TS_RE.search(line)
    if not m:
        return line
    return line[:m.start("ts")] + format_apache_ts(new_dt, tz) + line[m.end("ts"):]


def shift_seconds(line: str, seconds: int) -> str:
    parsed = parse_apache_ts(line)
    if not parsed:
        return line
    dt, tz = parsed
    new_dt = dt + timedelta(seconds=seconds)
    m = TS_RE.search(line)
    if not m:
        return line
    return line[:m.start("ts")] + format_apache_ts(new_dt, tz) + line[m.end("ts"):]


def set_status(line: str, status: str) -> str:
    # Apache combined usually has: "GET ..." 200 1234
    m = re.search(r'("\s+)(\d{3})(\s+)', line)
    if not m:
        return line
    return line[:m.start(2)] + status + line[m.end(2):]


def mutate_lines(lines: List[str], mode: str, seed: int) -> Tuple[List[str], dict[str, int]]:
    rng = random.Random(seed)
    out: List[str] = []
    counts = {
        "batch_marker_count": 0,
        "stream_marker_count": 0,
        "operational_marker_count": 0,
        "shifted_hour_count": 0,
        "promo_shadow_count": 0,
        "duplicated_count": 0,
        "dropped_count": 0,
        "reordered_count": 0,
        "stream_delay_marker_count": 0,
        "operational_5xx_count": 0,
        "operational_timeout_marker_count": 0,
    }

    enable_stream = mode in {"batch_stream_anomaly", "batch_stream_operational_anomaly"}
    enable_oper = mode == "batch_stream_operational_anomaly"

    for idx, orig in enumerate(lines):
        if not orig.strip():
            continue
        line = orig.rstrip("\n")
        r = stable_ratio(line, f"{mode}:{idx}")
        params = {}
        path_override = None

        # Batch asset anomaly: skew hour distribution and page mix at source.
        if r < 0.35:
            line = shift_to_hour(line, 3)
            params.update({"v05_src_anomaly": mode, "v05_runtime_layer": "batch", "v05_batch_skew": "hour_03"})
            counts["shifted_hour_count"] += 1
            counts["batch_marker_count"] += 1
        if 0.35 <= r < 0.60:
            path_override = "/promo_shadow"
            params.update({"v05_src_anomaly": mode, "v05_runtime_layer": "batch", "v05_page_type": "promo_shadow"})
            counts["promo_shadow_count"] += 1
            counts["batch_marker_count"] += 1

        # Stream anomaly encoded at source: duplicate/drop/delay/reorder markers.
        if enable_stream:
            rs = stable_ratio(line, f"stream:{mode}:{idx}")
            if rs < 0.05:
                counts["dropped_count"] += 1
                counts["stream_marker_count"] += 1
                continue
            if 0.05 <= rs < 0.20:
                params.update({"v05_src_anomaly": mode, "v05_runtime_layer": "stream", "v05_stream_delay_ms": "45000"})
                line = shift_seconds(line, 45)
                counts["stream_delay_marker_count"] += 1
                counts["stream_marker_count"] += 1
            if 0.20 <= rs < 0.26:
                params.update({"v05_src_anomaly": mode, "v05_runtime_layer": "stream", "v05_stream_duplicate": "1"})
                counts["duplicated_count"] += 1
                counts["stream_marker_count"] += 1

        # Operational anomaly encoded at source: 5xx/status/timeout markers.
        if enable_oper:
            ro = stable_ratio(line, f"oper:{mode}:{idx}")
            if ro < 0.10:
                line = set_status(line, "503")
                params.update({"v05_src_anomaly": mode, "v05_runtime_layer": "operational", "v05_oper_status": "503"})
                counts["operational_5xx_count"] += 1
                counts["operational_marker_count"] += 1
            elif 0.10 <= ro < 0.16:
                params.update({"v05_src_anomaly": mode, "v05_runtime_layer": "operational", "v05_timeout": "1", "v05_retry": "1"})
                counts["operational_timeout_marker_count"] += 1
                counts["operational_marker_count"] += 1

        if params or path_override:
            line = update_url(line, params, path_override=path_override)
        out.append(line + "\n")

        # Duplicate after mutation so source-level duplicate evidence exists.
        if enable_stream and "v05_stream_duplicate" in params:
            out.append(line + "\n")

    # Deterministic local reordering to create source order/timestamp mismatch without touching tables.
    if enable_stream and len(out) > 200:
        block_size = 50
        for start in range(0, min(len(out), 1000), block_size * 2):
            a = out[start:start+block_size]
            b = out[start+block_size:start+block_size*2]
            if b:
                out[start:start+block_size*2] = b + a
                counts["reordered_count"] += len(a) + len(b)
                counts["stream_marker_count"] += len(a) + len(b)

    return out, counts


def apply_source_anomaly(profile_id: str, event_date: str, scenario_name: str, input_dir: Path, mode: Optional[str], seed: int = 42) -> Path:
    mode = mode or scenario_name
    supported = {"batch_asset_anomaly", "batch_stream_anomaly", "batch_stream_operational_anomaly"}
    if mode not in supported:
        raise ValueError(f"Unsupported source anomaly mode: {mode}. Supported={sorted(supported)}")

    behavior_log = find_behavior_log(input_dir, profile_id, event_date, scenario_name)
    original_lines = behavior_log.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    backup = behavior_log.with_suffix(behavior_log.suffix + ".original")
    if not backup.exists():
        backup.write_text("".join(original_lines), encoding="utf-8")

    mutated, counts = mutate_lines(original_lines, mode, seed)
    behavior_log.write_text("".join(mutated), encoding="utf-8")

    trace = MutationTrace(
        profile_id=profile_id,
        event_date=event_date,
        scenario_name=scenario_name,
        mode=mode,
        behavior_log=str(behavior_log),
        original_count=len(original_lines),
        final_count=len(mutated),
        seed=seed,
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        **counts,
    )
    trace_path = input_dir / f"{profile_id}_{event_date}_{scenario_name}_source_anomaly_trace.json"
    trace_path.write_text(json.dumps(asdict(trace), ensure_ascii=False, indent=2), encoding="utf-8")
    return trace_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--event-date", required=True)
    ap.add_argument("--scenario-name", required=True)
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--mode", default=None)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    trace = apply_source_anomaly(args.profile_id, args.event_date, args.scenario_name, Path(args.input_dir), args.mode, args.seed)
    print(f"[OK] source-level anomaly injected trace={trace}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
