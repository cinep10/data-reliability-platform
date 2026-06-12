#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shlex, sys
from pathlib import Path
import yaml

BOOL_TRUE = {"1", "true", "yes", "y", "on"}

def as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in BOOL_TRUE

def shell_export(key: str, value) -> str:
    if isinstance(value, bool):
        value = "true" if value else "false"
    elif value is None:
        value = ""
    else:
        value = str(value)
    return f"export {key}={shlex.quote(value)}"

def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve v0.5 commerce scenario registry into shell/json contract.")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--scenario-id", required=True)
    ap.add_argument("--format", choices=["shell", "json"], default="shell")
    args = ap.parse_args()
    registry_path = Path(args.registry)
    if not registry_path.exists():
        raise SystemExit(f"registry not found: {registry_path}")
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    scenarios = raw.get("scenarios") or {}
    if args.scenario_id not in scenarios:
        known = ", ".join(sorted(scenarios))
        raise SystemExit(f"unknown scenario_id={args.scenario_id}; known=[{known}]")
    s = dict(scenarios[args.scenario_id] or {})
    family = s.get("family", "journey_native")
    source_generation = s.get("source_generation_scenario") or args.scenario_id
    use_exo = as_bool(s.get("use_exogenous"), False)
    runtime_apply = as_bool(s.get("runtime_apply"), False)
    exo_id = s.get("exogenous_scenario_id") or (args.scenario_id if use_exo else "")
    runtime_mode = s.get("runtime_apply_mode") or (args.scenario_id if runtime_apply else "")
    out = {
        "SCENARIO_ID": args.scenario_id,
        "SCENARIO_FAMILY": family,
        "SOURCE_GENERATION_SCENARIO": source_generation,
        "USE_EXOGENOUS_SCENARIO": use_exo,
        "EXOGENOUS_SCENARIO_ID": exo_id,
        "APPLY_SOURCE_RUNTIME_ANOMALY": runtime_apply,
        "SOURCE_RUNTIME_MODE": runtime_mode,
        "EXPECTED_RISK_FAMILY": s.get("expected_risk_family", "unknown"),
        "RUN_V04_EVIDENCE_MEASUREMENT_RESOLVED": as_bool(s.get("run_v04_evidence_measurement"), True),
        "RUN_V04_LEGACY_DECISION_RESOLVED": as_bool(s.get("run_v04_legacy_decision"), False),
        "RUN_V05_PHASE3_PHASE4_RESOLVED": as_bool(s.get("run_v05_phase3_phase4"), True),
        "RUN_INTEGRATED_VALIDATION_RESOLVED": as_bool(s.get("run_integrated_validation"), True),
        "AUTHORITATIVE_CHAIN": "v05_commerce_measurement_semantic_risk_action",
    }
    if args.format == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for k, v in out.items():
            print(shell_export(k, v))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
