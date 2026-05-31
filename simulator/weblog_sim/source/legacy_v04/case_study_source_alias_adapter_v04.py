#!/usr/bin/env python3
"""v0.4 Case Study source alias adapter.

Purpose
-------
Inject case-study anomalies into *source log files* without changing the v0.4
cookie contract. The adapter maps business/case-study aliases to existing
v0.4 cookie keys such as schema_flag, anomaly_type, drop_probability,
latency_shift_ms, conversion_multiplier, reconciliation_flag, financial_product,
and funnel_stage.

Why this exists
---------------
Changing cookie names such as offer_channel -> offer_transport would require
rewriting every downstream parser. For v0.4 case studies, the goal is not to
break the parser. The goal is to produce measurable semantic distortion through
source-level metadata while preserving the existing pipeline contract.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

SAFE_KEYS = {
    "cc", "al", "channel", "device", "pcid", "sid", "uid", "evt", "event_type", "page_type", "product_type",
    "latency_ms", "http_status", "schema_version", "scenario_id", "scenario_name", "domain", "source_layer",
    "anomaly_type", "drift", "affected", "exo_state_id", "anomaly_contract_id", "experiment_id", "run_id",
    "exo_source", "weather_type", "campaign_flag", "system_flag", "volume_multiplier", "conversion_multiplier",
    "latency_shift_ms", "drop_probability", "timeout_multiplier", "retry_multiplier", "duplicate_multiplier",
    "event_time_skew_ms", "suppress_input", "schema_flag", "identity_flag", "pcid_stability", "session_stability",
    "customer_id_stability", "traffic_actor", "bot_flag", "user_agent_flag", "ip_concentration_flag", "recovery_flag",
    "backlog_flush", "transaction_delay_ms", "event_ingestion_delay_ms", "privacy_flag", "pii_detected",
    "sensitive_field_flag", "masking_status", "financial_product", "funnel_stage", "state_transition", "expected_state",
    "actual_state", "amount_expected", "amount_actual", "amount_delta", "approval_result", "execution_result",
    "account_status", "ledger_status", "balance_delta", "reconciliation_flag"
}

CASE_ALIASES = {
    "CASE-OFFER-001": "source_offer_schema_drift_realtime_missing",
    "source_offer_schema_drift_realtime_missing": "source_offer_schema_drift_realtime_missing",
    "CASE-REC-002": "source_recommendation_schema_drift_false_conversion",
    "source_recommendation_schema_drift_false_conversion": "source_recommendation_schema_drift_false_conversion",
}

@dataclass
class Stats:
    input_lines: int = 0
    output_lines: int = 0
    target_lines: int = 0
    changed_lines: int = 0
    dropped_lines: int = 0
    duplicated_lines: int = 0


def stable_float(*parts: object) -> float:
    s = "|".join(str(p) for p in parts)
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
    return int(h, 16) / float(16 ** 16)


def parse_kv(kv: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for token in kv.strip().split(";"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        k, v = token.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def render_kv(fields: Dict[str, str], original_order: List[str]) -> str:
    ordered: List[str] = []
    seen = set()
    for k in original_order:
        if k in fields and k in SAFE_KEYS and k not in seen:
            ordered.append(k)
            seen.add(k)
    for k in sorted(fields):
        if k in SAFE_KEYS and k not in seen:
            ordered.append(k)
            seen.add(k)
    def clean(v: str) -> str:
        return str(v).replace(";", "_").replace("\n", "_").replace("\r", "_").replace(" ", "_")
    return " ".join(f"{k}={clean(fields.get(k, 'none'))};" for k in ordered)


def extract_last_quoted(line: str) -> Tuple[List[str], str] | None:
    parts = line.rstrip("\n").split('"')
    if len(parts) < 8:
        return None
    return parts, parts[-2]


def replace_last_quoted(parts: List[str], new_value: str) -> str:
    parts = list(parts)
    parts[-2] = new_value
    return '"'.join(parts) + "\n"


def path_from_line(line: str) -> str:
    m = re.search(r'"[A-Z]+\s+([^\s"]+)\s+HTTP/', line)
    return m.group(1) if m else ""


def is_case1_target(kv: Dict[str, str], line: str) -> bool:
    path = path_from_line(line).lower()
    product = (kv.get("product_type") or kv.get("financial_product") or "").lower()
    page = (kv.get("page_type") or "").lower()
    evt = (kv.get("evt") or kv.get("event_type") or "").lower()
    return (
        product == "loan" or "loan" in page or "/loan/" in path
    ) and evt in {"view", "click", "conversion"}


def is_case2_target(kv: Dict[str, str], line: str) -> bool:
    path = path_from_line(line).lower()
    product = (kv.get("product_type") or kv.get("financial_product") or "").lower()
    page = (kv.get("page_type") or "").lower()
    evt = (kv.get("evt") or kv.get("event_type") or "").lower()
    return (
        product in {"loan", "card"} or "loan" in page or "card" in page or "/loan/" in path or "/card/" in path
    ) and evt in {"click", "view"}


def apply_case1(kv: Dict[str, str], profile_id: str, target_date: str) -> Dict[str, str]:
    kv = dict(kv)
    kv.update({
        "schema_version": "v0.4-source-anomaly-contract-drifted",
        "scenario_id": "CASE-OFFER-001",
        "scenario_name": "source_offer_schema_drift_realtime_missing",
        "domain": kv.get("product_type", "loan") or "loan",
        "source_layer": "behavior",
        "anomaly_type": "schema_drift",
        "drift": "on",
        "affected": "1",
        "schema_flag": "drift",
        "drop_probability": "0.35",
        "latency_shift_ms": "800",
        "reconciliation_flag": "offer_delivery_missing",
        "financial_product": "loan",
        "funnel_stage": "offer",
        "system_flag": "normal",
        "campaign_flag": "loan_promo",
        "exo_source": "case_study_source_adapter_v04",
    })
    try:
        latency = int(float(kv.get("latency_ms", "0") or 0))
        kv["latency_ms"] = str(latency + 800)
    except Exception:
        kv["latency_ms"] = "800"
    return kv


def apply_case2(kv: Dict[str, str], profile_id: str, target_date: str) -> Dict[str, str]:
    kv = dict(kv)
    kv.update({
        "schema_version": "v0.4-source-anomaly-contract-drifted",
        "scenario_id": "CASE-REC-002",
        "scenario_name": "source_recommendation_schema_drift_false_conversion",
        "domain": kv.get("product_type", "loan") or "loan",
        "source_layer": "behavior",
        "anomaly_type": "schema_drift",
        "drift": "on",
        "affected": "1",
        "schema_flag": "drift",
        "conversion_multiplier": "1.8",
        "duplicate_multiplier": "1.8",
        "reconciliation_flag": "kpi_semantic_mismatch",
        "financial_product": kv.get("product_type", "loan") or "loan",
        "funnel_stage": "recommendation",
        "campaign_flag": "loan_promo",
        "exo_source": "case_study_source_adapter_v04",
    })
    return kv


def process_lines(lines: Iterable[str], *, case_name: str, profile_id: str, target_date: str, seed: int,
                  case1_drop_rate: float, case2_duplicate_rate: float, max_lines: int) -> Tuple[List[str], Stats]:
    out: List[str] = []
    st = Stats()
    for idx, line in enumerate(lines):
        st.input_lines += 1
        if max_lines > 0 and st.input_lines > max_lines:
            out.append(line)
            st.output_lines += 1
            continue
        ex = extract_last_quoted(line)
        if ex is None:
            out.append(line)
            st.output_lines += 1
            continue
        parts, kv_text = ex
        original_order = [t.strip().split("=", 1)[0] for t in kv_text.split(";") if "=" in t]
        kv = parse_kv(kv_text)
        target = False
        if case_name == "source_offer_schema_drift_realtime_missing":
            target = is_case1_target(kv, line)
            if target:
                st.target_lines += 1
                r = stable_float(seed, idx, "case1_drop")
                if r < case1_drop_rate:
                    st.dropped_lines += 1
                    continue
                new_kv = render_kv(apply_case1(kv, profile_id, target_date), original_order)
                out.append(replace_last_quoted(parts, new_kv))
                st.changed_lines += 1
                st.output_lines += 1
                continue
        elif case_name == "source_recommendation_schema_drift_false_conversion":
            target = is_case2_target(kv, line)
            if target:
                st.target_lines += 1
                new_kv_dict = apply_case2(kv, profile_id, target_date)
                new_kv = render_kv(new_kv_dict, original_order)
                newline = replace_last_quoted(parts, new_kv)
                out.append(newline)
                st.changed_lines += 1
                st.output_lines += 1
                if stable_float(seed, idx, "case2_dup") < case2_duplicate_rate:
                    out.append(newline)
                    st.duplicated_lines += 1
                    st.output_lines += 1
                continue
        out.append(line)
        st.output_lines += 1
    return out, st


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-file", required=True)
    ap.add_argument("--output-file", default="")
    ap.add_argument("--case-id", required=True, choices=sorted(CASE_ALIASES))
    ap.add_argument("--profile-id", default="finance_bank")
    ap.add_argument("--target-date", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--case1-drop-rate", type=float, default=0.35)
    ap.add_argument("--case2-duplicate-rate", type=float, default=0.80)
    ap.add_argument("--max-lines", type=int, default=0)
    ap.add_argument("--in-place", action="store_true")
    ap.add_argument("--backup", action="store_true")
    args = ap.parse_args()

    case_name = CASE_ALIASES[args.case_id]
    inp = Path(args.input_file)
    outp = Path(args.output_file or args.input_file)
    if not inp.exists():
        raise FileNotFoundError(inp)
    lines = inp.read_text(encoding="utf-8", errors="replace").splitlines(True)
    new_lines, st = process_lines(
        lines,
        case_name=case_name,
        profile_id=args.profile_id,
        target_date=args.target_date,
        seed=args.seed,
        case1_drop_rate=args.case1_drop_rate,
        case2_duplicate_rate=args.case2_duplicate_rate,
        max_lines=args.max_lines,
    )
    if args.in_place and args.backup:
        backup = inp.with_suffix(inp.suffix + ".case_adapter.bak")
        shutil.copy2(inp, backup)
        print(f"[BACKUP] {backup}")
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text("".join(new_lines), encoding="utf-8")
    print(
        f"[OK] case_study_source_alias_adapter case={case_name} input_lines={st.input_lines} "
        f"output_lines={st.output_lines} target={st.target_lines} changed={st.changed_lines} "
        f"dropped={st.dropped_lines} duplicated={st.duplicated_lines} output={outp}"
    )

if __name__ == "__main__":
    main()
