#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, date
from decimal import Decimal

import pymysql


def json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def daterange(dt_from: str, dt_to: str):
    s = datetime.strptime(dt_from, "%Y-%m-%d").date()
    e = datetime.strptime(dt_to, "%Y-%m-%d").date()
    cur = s
    while cur <= e:
        yield str(cur)
        cur += timedelta(days=1)


def connect_mysql(args):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        autocommit=False,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def fetch_exogenous(cur, profile_id: str, dt: str):
    cur.execute(
        """
        SELECT
            profile_id,
            dt,
            SUBSTRING_INDEX(GROUP_CONCAT(weather_type ORDER BY hh), ',', 1) AS weather_type,
            SUBSTRING_INDEX(GROUP_CONCAT(campaign_flag ORDER BY hh), ',', 1) AS campaign_flag,
            SUBSTRING_INDEX(GROUP_CONCAT(system_flag ORDER BY hh), ',', 1) AS system_flag,
            AVG(volume_multiplier) AS volume_multiplier,
            AVG(conversion_multiplier) AS conversion_multiplier,
            AVG(timeout_multiplier) AS timeout_multiplier,
            AVG(retry_multiplier) AS retry_multiplier
        FROM exogenous_state_timeline
        WHERE profile_id=%s
          AND dt=%s
        GROUP BY profile_id, dt
        """,
        (profile_id, dt),
    )
    return cur.fetchone() or {}


def fetch_scenario_name(cur, profile_id: str, dt: str):
    cur.execute(
        """
        SELECT scenario_name
        FROM scenario_plan
        WHERE profile_id=%s
          AND active_flag=1
          AND %s BETWEEN dt_from AND dt_to
        ORDER BY dt_from DESC
        LIMIT 1
        """,
        (profile_id, dt),
    )
    row = cur.fetchone()
    return row["scenario_name"] if row else "baseline"


def delete_existing(cur, profile_id: str, dt_from: str, dt_to: str):
    cur.execute(
        """
        DELETE FROM scenario_adapter_result_log
        WHERE profile_id=%s
          AND dt BETWEEN %s AND %s
          AND adapter_name='batch_metric_adapter_v2'
        """,
        (profile_id, dt_from, dt_to),
    )


def classify_batch_plan(exo: dict):
    system_flag = str(exo.get("system_flag") or "normal")
    weather_type = str(exo.get("weather_type") or "clear")
    campaign_flag = str(exo.get("campaign_flag") or "none")

    plan = {
        "source_path": "weblog_sim.generator -> stg_webserver_log_hit -> collector_a_v3 -> analyzer_b_v4",
        "metric_direct_update": False,
        "apply_via_source_events": True,
        "expected_batch_effect": "baseline",
    }

    if system_flag == "collector_drop":
        plan["expected_batch_effect"] = "capture_rate_down"
    elif system_flag == "auth_delay":
        plan["expected_batch_effect"] = "auth_conversion_down"
    elif system_flag == "submit_partial_loss":
        plan["expected_batch_effect"] = "submit_conversion_down"
    elif system_flag == "degraded":
        plan["expected_batch_effect"] = "volume_and_conversion_soft_drop"
    elif campaign_flag != "none":
        plan["expected_batch_effect"] = "volume_spike"
    elif weather_type in ("rain", "snow"):
        plan["expected_batch_effect"] = "traffic_mix_shift"

    return plan


def main():
    ap = argparse.ArgumentParser(description="Source-first batch adapter plan logger")
    ap.add_argument("--db-host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    ap.add_argument("--db-user", default=os.getenv("DB_USER", "nethru"))
    ap.add_argument("--db-pass", default=os.getenv("DB_PASSWORD", "nethru1234"))
    ap.add_argument("--db-name", default=os.getenv("DB_NAME", "weblog"))
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    args = ap.parse_args()

    conn = connect_mysql(args)
    try:
        with conn.cursor() as cur:
            delete_existing(cur, args.profile_id, args.dt_from, args.dt_to)

            inserted = 0
            for dt in daterange(args.dt_from, args.dt_to):
                exo = fetch_exogenous(cur, args.profile_id, dt)
                scenario_name = fetch_scenario_name(cur, args.profile_id, dt)
                plan = classify_batch_plan(exo)

                detail = {
                    "mode": "log_only",
                    "why": "batch scenario must flow through source log generation and downstream parse/collector/analyzer, not direct metric mutation",
                    "batch_plan": plan,
                    "exogenous_snapshot": exo,
                }

                cur.execute(
                    """
                    INSERT INTO scenario_adapter_result_log
                    (
                        profile_id,
                        dt,
                        hh,
                        scenario_name,
                        adapter_name,
                        result_metric,
                        result_value,
                        result_status,
                        detail
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        args.profile_id,
                        dt,
                        None,
                        scenario_name,
                        "batch_metric_adapter_v2",
                        "batch_plan_ready",
                        1,
                        "ready",
                        json.dumps(detail, ensure_ascii=False, default=json_default),
                    ),
                )
                inserted += 1

        conn.commit()
        print(
            f"[OK] batch_metric_adapter_v2 completed: "
            f"profile={args.profile_id}, dates={inserted}, mode=log_only"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
