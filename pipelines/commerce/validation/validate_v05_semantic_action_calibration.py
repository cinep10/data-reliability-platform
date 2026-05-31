#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymysql
import yaml


def jdefault(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat(sep=" ") if isinstance(v, datetime) else v.isoformat()
    return str(v)


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=jdefault, sort_keys=True)


def parse_args():
    p = argparse.ArgumentParser(description="Validate v0.5 semantic/action calibration config and optionally persist observed review.")
    p.add_argument("--calibration-config", required=True)
    p.add_argument("--db-host")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user")
    p.add_argument("--db-pass")
    p.add_argument("--db-name")
    p.add_argument("--profile-id")
    p.add_argument("--target-date")
    p.add_argument("--run-id", type=int)
    p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--scenario-name")
    p.add_argument("--persist", action="store_true")
    p.add_argument("--truncate-target", action="store_true")
    return p.parse_args()


def load_config(path: str) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(path)
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def scenario_rules(cfg: dict[str, Any]) -> dict[str, Any]:
    if isinstance(cfg.get("scenarios"), dict):
        return cfg["scenarios"]
    if isinstance(cfg.get("scenario_expectations"), dict):
        return cfg["scenario_expectations"]
    if isinstance(cfg.get("calibration"), dict) and isinstance(cfg["calibration"].get("scenarios"), dict):
        return cfg["calibration"]["scenarios"]
    return {}


def normalize_text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def norm(v: Any) -> str:
    return normalize_text(v).lower().replace("_", " ").replace("-", " ")


def contains_expected(observed: str, expected: str) -> bool:
    if not expected:
        return True
    if not observed:
        return False
    o = norm(observed)
    e = norm(expected)
    if e in o or o in e:
        return True
    # Broad semantic family matching.
    aliases = {
        "completeness": ["completeness", "missing", "partial", "loss"],
        "consistency": ["consistency", "reconciliation", "mapping", "transaction"],
        "integrity": ["integrity", "state", "transition"],
        "timeliness": ["timeliness", "latency", "delay"],
        "availability": ["availability", "runtime", "operational", "pipeline"],
        "customer": ["customer", "experience"],
        "coupon": ["coupon", "attribution"],
    }
    for key, words in aliases.items():
        if key in e:
            return any(w in o for w in words)
    return False


def expected_values(rule: dict[str, Any]) -> tuple[str, str, str]:
    exp_sem = (
        rule.get("expected_semantic_family")
        or rule.get("expected_semantic")
        or rule.get("semantic_family")
        or rule.get("semantic")
        or ""
    )
    exp_action = (
        rule.get("expected_action")
        or rule.get("action")
        or rule.get("recommended_action")
        or ""
    )
    exp_esc = (
        rule.get("expected_escalation")
        or rule.get("escalation_expectation")
        or rule.get("expected_risk_level")
        or ""
    )
    return normalize_text(exp_sem), normalize_text(exp_action), normalize_text(exp_esc)


def connect(args):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) cnt FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return int(cur.fetchone()["cnt"]) > 0


def columns(cur, table: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s",
        (table,),
    )
    return {str(r["column_name"]) for r in cur.fetchall()}


def fetch_one(cur, table: str, args) -> dict[str, Any]:
    if not table_exists(cur, table):
        return {}
    cols = columns(cur, table)
    wh = []
    ps = []
    if "profile_id" in cols:
        wh.append("profile_id=%s"); ps.append(args.profile_id)
    if "target_date" in cols:
        wh.append("target_date=%s"); ps.append(args.target_date)
    elif "dt" in cols:
        wh.append("dt=%s"); ps.append(args.target_date)
    if "scenario_name" in cols:
        wh.append("scenario_name=%s"); ps.append(args.scenario_name)
    if "run_id" in cols and args.run_id is not None:
        wh.append("run_id=%s"); ps.append(args.run_id)
    if "source_gen_run_id" in cols and args.source_gen_run_id is not None:
        wh.append("source_gen_run_id=%s"); ps.append(args.source_gen_run_id)
    order = []
    for c in ["updated_at", "created_at", "run_id", "source_gen_run_id", "review_id", "id"]:
        if c in cols:
            order.append(f"{c} DESC")
    sql = f"SELECT * FROM `{table}` WHERE {' AND '.join(wh) if wh else '1=1'}"
    if order:
        sql += " ORDER BY " + ", ".join(order)
    sql += " LIMIT 1"
    cur.execute(sql, tuple(ps))
    return cur.fetchone() or {}


def get_observed(cur, args) -> dict[str, Any]:
    sem = fetch_one(cur, "semantic_interpretation_day_v05", args)
    risk = fetch_one(cur, "unified_reliability_score_day_v05", args)
    act = fetch_one(cur, "action_recommendation_day_v05", args)

    # Some action tables can have multiple actions. Prefer highest rank/priority if columns exist.
    if table_exists(cur, "action_recommendation_day_v05"):
        cols = columns(cur, "action_recommendation_day_v05")
        wh = ["profile_id=%s", "target_date=%s", "scenario_name=%s"]
        ps = [args.profile_id, args.target_date, args.scenario_name]
        if "run_id" in cols and args.run_id is not None:
            wh.append("run_id=%s"); ps.append(args.run_id)
        if "source_gen_run_id" in cols and args.source_gen_run_id is not None:
            wh.append("source_gen_run_id=%s"); ps.append(args.source_gen_run_id)
        order_cols = [c for c in ["action_priority", "action_rank", "created_at"] if c in cols]
        order = " ORDER BY " + ", ".join(f"{c} DESC" for c in order_cols) if order_cols else ""
        cur.execute(
            f"SELECT * FROM action_recommendation_day_v05 WHERE {' AND '.join(wh)}{order} LIMIT 1",
            tuple(ps),
        )
        act = cur.fetchone() or act

    return {
        "semantic": sem,
        "risk": risk,
        "action": act,
        "observed_semantic_risk": (
            sem.get("dominant_semantic_risk")
            or sem.get("semantic_risk_family")
            or sem.get("dominant_risk")
            or "None"
        ),
        "observed_action": (
            act.get("recommended_action")
            or act.get("action_name")
            or act.get("action_type")
            or "no action"
        ),
        "observed_risk_level": (
            risk.get("final_risk_level")
            or risk.get("risk_level")
            or "unknown"
        ),
        "observed_risk_score": (
            risk.get("overall_risk_score")
            or risk.get("risk_score")
            or 0
        ),
    }


def schema_insert(cur, row: dict[str, Any]) -> None:
    table = "v05_semantic_action_calibration_review_day"
    cols = columns(cur, table)

    # Add compatibility aliases only when the actual table has those columns.
    if "calibration_result" in cols and "calibration_result" not in row:
        row["calibration_result"] = row.get("review_status", "REVIEW")
    if "calibration_status" in cols and "calibration_status" not in row:
        row["calibration_status"] = row.get("review_status", "REVIEW")

    row = {k: v for k, v in row.items() if k in cols}

    if "created_at" in cols and "created_at" not in row:
        pass
    if not row:
        raise RuntimeError("no insertable columns for calibration review table")

    # delete first rather than relying on unknown unique key shape
    wh = []
    ps = []
    for key in ["profile_id", "target_date", "scenario_name", "run_id", "source_gen_run_id"]:
        if key in cols and key in row:
            wh.append(f"{key}=%s")
            ps.append(row[key])
    if wh:
        cur.execute(f"DELETE FROM `{table}` WHERE {' AND '.join(wh)}", tuple(ps))

    keys = list(row.keys())
    vals = [row[k] for k in keys]
    cur.execute(
        f"INSERT INTO `{table}` (" + ",".join(f"`{k}`" for k in keys) + ") VALUES (" + ",".join(["%s"] * len(keys)) + ")",
        tuple(vals),
    )


def main() -> int:
    args = parse_args()
    cfg = load_config(args.calibration_config)
    rules = scenario_rules(cfg)

    if not isinstance(rules, dict) or not rules:
        raise RuntimeError("calibration config has no scenarios/scenario_expectations mapping")

    print(f"[OK] calibration config valid scenarios={len(rules)} path={args.calibration_config}")

    if not args.persist:
        return 0

    required = [args.db_host, args.db_user, args.db_pass, args.db_name, args.profile_id, args.target_date, args.scenario_name]
    if any(v is None for v in required):
        raise RuntimeError("--persist requires DB args, profile-id, target-date, scenario-name")

    rule = rules.get(args.scenario_name, {})
    exp_sem, exp_action, exp_esc = expected_values(rule if isinstance(rule, dict) else {})

    con = connect(args)
    try:
        with con.cursor() as cur:
            obs = get_observed(cur, args)
            observed_sem = normalize_text(obs["observed_semantic_risk"])
            observed_action = normalize_text(obs["observed_action"])
            observed_level = normalize_text(obs["observed_risk_level"])
            observed_score = float(obs["observed_risk_score"] or 0)

            semantic_match = 1 if contains_expected(observed_sem, exp_sem) else 0
            action_match = 1 if contains_expected(observed_action, exp_action) else 0

            if not exp_action:
                action_match = 1
            if not exp_sem:
                semantic_match = 1

            escalation_match = 1
            if exp_esc:
                escalation_match = 1 if contains_expected(observed_level, exp_esc) else 0

            baseline_like = args.scenario_name.lower() in {"baseline", "normal", "stable"}
            if baseline_like:
                baseline_sem_ok = observed_sem in {"", "none", "null", "None"}
                baseline_action_ok = "no action" in observed_action.lower() or observed_action == ""
                baseline_level_ok = observed_level.lower() in {"stable", "normal", "low"}
                semantic_match = 1 if baseline_sem_ok else 0
                action_match = 1 if baseline_action_ok else 0
                escalation_match = 1 if baseline_level_ok else 0

            if semantic_match and action_match and escalation_match:
                status = "PASS"
            elif baseline_like:
                status = "MISMATCH"
            else:
                status = "REVIEW"

            reasons = []
            if not semantic_match:
                reasons.append(f"semantic expected={exp_sem or '*'} observed={observed_sem}")
            if not action_match:
                reasons.append(f"action expected={exp_action or '*'} observed={observed_action}")
            if not escalation_match:
                reasons.append(f"escalation expected={exp_esc or '*'} observed={observed_level}")

            payload = {
                "expected": {
                    "semantic_family": exp_sem,
                    "action": exp_action,
                    "escalation": exp_esc,
                },
                "observed": {
                    "semantic_risk": observed_sem,
                    "action": observed_action,
                    "risk_level": observed_level,
                    "risk_score": observed_score,
                },
                "rule": rule,
                "matches": {
                    "semantic": semantic_match,
                    "action": action_match,
                    "escalation": escalation_match,
                },
            }

            row = {
                "run_id": args.run_id or 0,
                "profile_id": args.profile_id,
                "source_gen_run_id": args.source_gen_run_id,
                "target_date": args.target_date,
                "scenario_name": args.scenario_name,
                "expected_semantic_family": exp_sem,
                "observed_semantic_risk": observed_sem,
                "expected_action": exp_action,
                "observed_action": observed_action,
                "expected_escalation": exp_esc,
                "observed_risk_level": observed_level,
                "observed_risk_score": observed_score,
                "semantic_match_flag": semantic_match,
                "action_match_flag": action_match,
                "escalation_match_flag": escalation_match,
                "review_status": status,
                "calibration_result": status,
                "calibration_status": status,
                "review_reason": "; ".join(reasons) if reasons else "expected and observed are aligned",
                "review_payload_json": json_dumps(payload),
            }

            schema_insert(cur, row)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    print(f"[OK] calibration review persisted scenario={args.scenario_name} status={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
