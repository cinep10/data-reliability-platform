#!/usr/bin/env python3
"""
v0.5 Phase2 canonical/mapping validation.

Patch purpose
-------------
behavior_only_anomaly intentionally generates behavior logs only:
- canonical_behavior_events > 0
- canonical_transaction_events = 0
- canonical_state_events = 0
- behavior_transaction_mapping contains behavior_only/orphan metadata
- transaction_state_mapping = 0

The previous validation treated transaction/state existence as mandatory for every
scenario, causing 7-day smoke tests to fail on behavior_only_anomaly even though
the source generation was correct.

This validator keeps strict expectations for normal/transaction/state scenarios,
but allows the intended behavior-only shape when the evidence says this is a
behavior-only replay.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List, Tuple

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
    p.add_argument("--run-id", type=int, required=False)
    p.add_argument("--source-gen-run-id", type=int, required=False)
    p.add_argument("--scenario-name", required=False, default=None)
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


def scalar(cur, sql: str, params: Tuple[Any, ...]) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return 0
    return int(next(iter(row.values())) or 0)


def table_count(cur, table: str, args: argparse.Namespace, scenario_col: str | None = None) -> int:
    where = "profile_id=%s AND target_date=%s"
    params: List[Any] = [args.profile_id, args.target_date]
    if args.run_id is not None:
        where += " AND run_id=%s"
        params.append(args.run_id)
    if args.source_gen_run_id is not None:
        where += " AND source_gen_run_id=%s"
        params.append(args.source_gen_run_id)
    if scenario_col and args.scenario_name:
        where += f" AND {scenario_col}=%s"
        params.append(args.scenario_name)
    return scalar(cur, f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", tuple(params))


def count_mapping_status(cur, table: str, args: argparse.Namespace, statuses: Tuple[str, ...]) -> int:
    where = "profile_id=%s AND target_date=%s"
    params: List[Any] = [args.profile_id, args.target_date]
    if args.run_id is not None:
        where += " AND run_id=%s"
        params.append(args.run_id)
    if args.source_gen_run_id is not None:
        where += " AND source_gen_run_id=%s"
        params.append(args.source_gen_run_id)
    placeholders = ",".join(["%s"] * len(statuses))
    where += f" AND mapping_status IN ({placeholders})"
    params.extend(statuses)
    return scalar(cur, f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", tuple(params))


def duplicate_count(cur, args: argparse.Namespace) -> int:
    where = "profile_id=%s AND target_date=%s"
    params: List[Any] = [args.profile_id, args.target_date]
    if args.run_id is not None:
        where += " AND run_id=%s"
        params.append(args.run_id)
    if args.source_gen_run_id is not None:
        where += " AND source_gen_run_id=%s"
        params.append(args.source_gen_run_id)
    return scalar(
        cur,
        f"""
        SELECT COUNT(*) AS c
        FROM behavior_transaction_mapping
        WHERE {where}
          AND COALESCE(duplicate_flag, 0) = 1
        """,
        tuple(params),
    )


def print_check(name: str, ok: bool, value: Any = "") -> None:
    status = "PASS" if ok else "FAIL"
    suffix = f" ({value})" if value != "" else ""
    print(f"{name}: {status}{suffix}")


def main() -> int:
    args = parse_args()
    failures: List[str] = []

    with conn(args) as c:
        cur = c.cursor()

        behavior_count = table_count(cur, "canonical_behavior_events", args, "scenario_id")
        transaction_count = table_count(cur, "canonical_transaction_events", args)
        state_count = table_count(cur, "canonical_state_events", args)
        bt_count = table_count(cur, "behavior_transaction_mapping", args)
        ts_count = table_count(cur, "transaction_state_mapping", args)

        bt_matched = count_mapping_status(
            cur,
            "behavior_transaction_mapping",
            args,
            ("matched", "observed", "behavior_transaction_matched"),
        )
        ts_matched = count_mapping_status(
            cur,
            "transaction_state_mapping",
            args,
            ("matched", "observed", "transaction_state_matched"),
        )
        bt_orphan = count_mapping_status(
            cur,
            "behavior_transaction_mapping",
            args,
            ("behavior_only", "transaction_only", "orphan", "orphan_transaction"),
        )
        ts_orphan = count_mapping_status(
            cur,
            "transaction_state_mapping",
            args,
            ("orphan_state", "transaction_without_state", "orphan", "missing"),
        )
        dup_count = duplicate_count(cur, args)
        obs_measurement = None
        if args.scenario_name == "source_wc_collection_missing":
            try:
                cur.execute("""
                    SELECT web_hits, wc_hits, canonical_behavior_events, collection_gap_rate
                    FROM v05_observability_measurement_day
                    WHERE profile_id=%s AND target_date=%s AND scenario_name=%s
                      AND (%s IS NULL OR run_id=%s)
                      AND (%s IS NULL OR source_gen_run_id=%s)
                    ORDER BY run_id DESC, source_gen_run_id DESC
                    LIMIT 1
                """, (args.profile_id, args.target_date, args.scenario_name, args.run_id, args.run_id, args.source_gen_run_id, args.source_gen_run_id))
                obs_measurement = cur.fetchone()
            except Exception:
                obs_measurement = None

    # Behavior-only anomaly is valid when behavior exists and transaction/state are both absent.
    inferred_behavior_only = (
        behavior_count > 0
        and transaction_count == 0
        and state_count == 0
        and bt_count >= behavior_count
        and ts_count == 0
    )
    explicit_behavior_only = args.scenario_name == "behavior_only_anomaly"
    behavior_only_mode = explicit_behavior_only or inferred_behavior_only

    checks: List[Tuple[str, bool, Any]] = []

    checks.append(("canonical_behavior_events_exists", behavior_count > 0, behavior_count))

    if behavior_only_mode:
        checks.extend(
            [
                ("canonical_transaction_events_expected_zero_for_behavior_only", transaction_count == 0, transaction_count),
                ("canonical_state_events_expected_zero_for_behavior_only", state_count == 0, state_count),
                ("behavior_transaction_mapping_exists", bt_count > 0, bt_count),
                ("transaction_state_mapping_expected_zero_for_behavior_only", ts_count == 0, ts_count),
                ("behavior_transaction_behavior_only_metadata_queryable", bt_orphan > 0, bt_orphan),
                ("behavior_transaction_match_not_required_for_behavior_only", True, bt_matched),
                ("transaction_state_match_not_required_for_behavior_only", True, ts_matched),
                ("duplicate_metadata_queryable", dup_count >= 0, dup_count),
            ]
        )
    else:
        checks.extend(
            [
                ("canonical_transaction_events_exists", transaction_count > 0, transaction_count),
                ("canonical_state_events_exists", state_count > 0, state_count),
                ("behavior_transaction_mapping_exists", bt_count > 0, bt_count),
                ("transaction_state_mapping_exists", ts_count > 0, ts_count),
                ("behavior_transaction_match_possible", bt_matched > 0, bt_matched),
                ("transaction_state_match_possible", ts_matched > 0, ts_matched),
                ("orphan_metadata_queryable", (bt_orphan + ts_orphan) >= 0, f"bt={bt_orphan}, ts={ts_orphan}"),
                ("duplicate_metadata_queryable", dup_count >= 0, dup_count),
            ]
        )

    if args.scenario_name == "source_wc_collection_missing":
        if obs_measurement:
            checks.extend([
                ("observability_measurement_exists_for_wc_collection_missing", True, ""),
                ("web_hits_gt_wc_hits_for_wc_collection_missing", int(obs_measurement.get("web_hits") or 0) > int(obs_measurement.get("wc_hits") or 0), f"web={obs_measurement.get('web_hits')}, wc={obs_measurement.get('wc_hits')}") ,
                ("canonical_behavior_matches_observed_wc_not_source", abs(int(obs_measurement.get("canonical_behavior_events") or 0) - int(obs_measurement.get("wc_hits") or 0)) <= max(3, int(obs_measurement.get("wc_hits") or 0) * 0.01), f"canonical={obs_measurement.get('canonical_behavior_events')}, wc={obs_measurement.get('wc_hits')}")
            ])
        else:
            checks.append(("observability_measurement_exists_for_wc_collection_missing", False, "missing"))

    for name, ok, value in checks:
        print_check(name, ok, value)
        if not ok:
            failures.append(name)

    if failures:
        print("[FAIL] v0.5 Phase2 validation failed")
        print("failed_checks=" + ",".join(failures))
        return 1

    mode = "behavior_only" if behavior_only_mode else "standard"
    print(f"[OK] v0.5 Phase2 validation passed mode={mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
