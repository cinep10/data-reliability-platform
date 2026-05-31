#!/usr/bin/env python3
"""
v0.5 Phase1~4 integrated validation.

Fix purpose
-----------
behavior_only_anomaly intentionally has:
- canonical_transaction_events = 0
- canonical_state_events = 0
- transaction_state_mapping = 0

Therefore this validator must NOT require transaction/state rows for
behavior_only_anomaly.  It must validate that zero transaction/state is
the expected source behavior, while still validating behavior/reconciliation/
semantic/risk/action artifacts.

Principle
---------
canonical/mapping = business normalization / metadata
measurement != risk
risk != action
"""

import argparse
import sys
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pymysql


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    p.add_argument("--scenario-name", default=None)
    return p.parse_args()


def conn(args: argparse.Namespace):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def table_exists(cur, table: str) -> bool:
    cur.execute("SHOW TABLES LIKE %s", (table,))
    return cur.fetchone() is not None


def columns(cur, table: str) -> List[str]:
    cur.execute(f"SHOW COLUMNS FROM `{table}`")
    return [r["Field"] for r in cur.fetchall()]


def scoped_where(cols: List[str], args: argparse.Namespace, include_run: bool = True, include_source: bool = False) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    vals: List[Any] = []

    if "profile_id" in cols:
        clauses.append("profile_id=%s")
        vals.append(args.profile_id)

    for date_col in ("target_date", "dt", "event_date", "measurement_date"):
        if date_col in cols:
            clauses.append(f"{date_col}=%s")
            vals.append(args.target_date)
            break

    if include_run and "run_id" in cols:
        clauses.append("run_id=%s")
        vals.append(args.run_id)

    if include_source and "source_gen_run_id" in cols:
        clauses.append("source_gen_run_id=%s")
        vals.append(args.source_gen_run_id)

    if args.scenario_name and "scenario_name" in cols:
        clauses.append("scenario_name=%s")
        vals.append(args.scenario_name)

    if not clauses:
        return "1=1", []
    return " AND ".join(clauses), vals


def count_rows(cur, table: str, args: argparse.Namespace, include_run: bool = True, include_source: bool = False) -> int:
    if not table_exists(cur, table):
        return -1
    cols = columns(cur, table)
    where, vals = scoped_where(cols, args, include_run=include_run, include_source=include_source)
    cur.execute(f"SELECT COUNT(*) AS c FROM `{table}` WHERE {where}", vals)
    return int(cur.fetchone()["c"] or 0)


def scalar(cur, sql: str, vals: Iterable[Any] = ()) -> Optional[Any]:
    cur.execute(sql, tuple(vals))
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def check(name: str, ok: bool, details: str = "") -> Tuple[str, bool]:
    print(f"[CHECK] {name}: {'PASS' if ok else 'FAIL'}{(' ' + details) if details else ''}")
    return name, ok


def get_scenario(args: argparse.Namespace, cur) -> str:
    if args.scenario_name:
        return args.scenario_name

    # Fallback from v05_reconciliation_measurement_day if present
    t = "v05_reconciliation_measurement_day"
    if table_exists(cur, t):
        cols = columns(cur, t)
        if "scenario_name" in cols:
            where, vals = scoped_where(cols, args, include_run=True, include_source=True)
            cur.execute(f"SELECT scenario_name FROM `{t}` WHERE {where} LIMIT 1", vals)
            row = cur.fetchone()
            if row and row.get("scenario_name"):
                return row["scenario_name"]

    return ""


def metric_row(cur, args: argparse.Namespace) -> Dict[str, Any]:
    t = "v05_reconciliation_measurement_day"
    if not table_exists(cur, t):
        return {}
    cols = columns(cur, t)
    where, vals = scoped_where(cols, args, include_run=True, include_source=True)
    cur.execute(f"SELECT * FROM `{t}` WHERE {where} LIMIT 1", vals)
    return cur.fetchone() or {}


def score_row(cur, args: argparse.Namespace) -> Dict[str, Any]:
    t = "unified_reliability_score_day_v05"
    if not table_exists(cur, t):
        return {}
    cols = columns(cur, t)
    where, vals = scoped_where(cols, args, include_run=True, include_source=True)
    cur.execute(f"SELECT * FROM `{t}` WHERE {where} LIMIT 1", vals)
    return cur.fetchone() or {}


def semantic_row(cur, args: argparse.Namespace) -> Dict[str, Any]:
    t = "semantic_interpretation_day_v05"
    if not table_exists(cur, t):
        return {}
    cols = columns(cur, t)
    where, vals = scoped_where(cols, args, include_run=True, include_source=True)
    cur.execute(f"SELECT * FROM `{t}` WHERE {where} LIMIT 1", vals)
    return cur.fetchone() or {}


def action_rows(cur, args: argparse.Namespace) -> List[Dict[str, Any]]:
    t = "action_recommendation_day_v05"
    if not table_exists(cur, t):
        return []
    cols = columns(cur, t)
    where, vals = scoped_where(cols, args, include_run=True, include_source=True)
    cur.execute(f"SELECT * FROM `{t}` WHERE {where}", vals)
    return list(cur.fetchall())


def main() -> int:
    args = parse_args()
    c = conn(args)
    failures: List[str] = []

    with c.cursor() as cur:
        scenario = get_scenario(args, cur)
        behavior_only_mode = scenario == "behavior_only_anomaly"

        checks: List[Tuple[str, bool]] = []

        b_cnt = count_rows(cur, "canonical_behavior_events", args, include_run=True, include_source=True)
        tx_cnt = count_rows(cur, "canonical_transaction_events", args, include_run=True, include_source=True)
        st_cnt = count_rows(cur, "canonical_state_events", args, include_run=True, include_source=True)
        bt_cnt = count_rows(cur, "behavior_transaction_mapping", args, include_run=True, include_source=True)
        ts_cnt = count_rows(cur, "transaction_state_mapping", args, include_run=True, include_source=True)

        checks.append(check("canonical_behavior_events", b_cnt > 0, f"({b_cnt})"))

        if behavior_only_mode:
            checks.append(check("canonical_transaction_events_expected_zero_for_behavior_only", tx_cnt == 0, f"({tx_cnt})"))
            checks.append(check("canonical_state_events_expected_zero_for_behavior_only", st_cnt == 0, f"({st_cnt})"))
            checks.append(check("transaction_state_mapping_expected_zero_for_behavior_only", ts_cnt == 0, f"({ts_cnt})"))
        else:
            checks.append(check("canonical_transaction_events", tx_cnt > 0, f"({tx_cnt})"))
            # state_missing_anomaly may have only a tiny number of state rows, but should not be zero.
            checks.append(check("canonical_state_events", st_cnt > 0, f"({st_cnt})"))
            checks.append(check("transaction_state_mapping", ts_cnt > 0, f"({ts_cnt})"))

        checks.append(check("behavior_transaction_mapping", bt_cnt > 0, f"({bt_cnt})"))

        for table in [
            "v05_reconciliation_measurement_day",
            "reliability_analysis_result_day_v05",
            "semantic_interpretation_day_v05",
            "unified_reliability_score_day_v05",
            "action_recommendation_day_v05",
        ]:
            cnt = count_rows(cur, table, args, include_run=True, include_source=True)
            checks.append(check(table, cnt > 0, f"({cnt})"))

        m = metric_row(cur, args)
        if m:
            bt_rate = m.get("behavior_transaction_match_rate", Decimal("0"))
            ts_rate = m.get("transaction_state_match_rate", Decimal("0"))
            checks.append(check(f"behavior_transaction_match_rate={bt_rate}", bt_rate is not None))
            checks.append(check(f"transaction_state_match_rate={ts_rate}", ts_rate is not None))

        score = score_row(cur, args)
        sem = semantic_row(cur, args)
        actions = action_rows(cur, args)

        if score:
            overall = score.get("overall_risk_score")
            checks.append(check(f"overall_risk_score={overall}", overall is not None))

        # Baseline-specific gate: low residual must not be promoted to dominant risk/action.
        if scenario == "baseline":
            dominant = sem.get("dominant_semantic_risk")
            level = (score.get("final_risk_level") or "").lower() if score else ""
            overall = score.get("overall_risk_score") if score else None
            action_count = len(actions)
            first_action = actions[0].get("recommended_action") if actions else None

            stable_or_low = level in ("stable", "low")
            no_dominant = dominant in (None, "", "None", "Baseline Normal Variation")
            no_action = action_count == 1 and str(first_action).lower() == "no action"

            checks.append(check(
                f"baseline_calibration score={overall} level={level} dominant={dominant}",
                stable_or_low and no_dominant,
            ))
            checks.append(check(
                f"baseline_no_false_action action_count={action_count} action={first_action}",
                no_action,
            ))

        # behavior_only_anomaly-specific gate:
        # The transaction/state absence is the scenario signal, not a validation failure.
        if behavior_only_mode:
            checks.append(check(
                "behavior_only_source_contract",
                tx_cnt == 0 and st_cnt == 0 and ts_cnt == 0 and bt_cnt > 0,
                f"(tx={tx_cnt}, state={st_cnt}, ts_mapping={ts_cnt}, bt_mapping={bt_cnt})",
            ))

        failures = [name for name, ok in checks if not ok]

    c.close()

    if failures:
        print("[FAIL] " + ", ".join(failures))
        return 1

    print(f"[OK] v0.5 Phase1~4 validation passed mode={'behavior_only' if behavior_only_mode else 'standard'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
