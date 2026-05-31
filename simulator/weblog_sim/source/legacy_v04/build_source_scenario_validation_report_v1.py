from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Optional

import pymysql


@dataclass
class DbArgs:
    host: str
    port: int
    user: str
    password: str
    db: str


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--baseline-date", required=True)
    ap.add_argument("--dt-from", required=True)
    ap.add_argument("--dt-to", required=True)
    ap.add_argument("--db-host", required=True)
    ap.add_argument("--db-port", required=True, type=int)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", required=True)
    ap.add_argument("--db-name", required=True)
    return ap.parse_args()


def connect(args: argparse.Namespace):
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


def execute(conn, sql: str, params: Optional[tuple[Any, ...]] = None) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())


def fetch_one(conn, sql: str, params: Optional[tuple[Any, ...]] = None) -> Optional[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def fetch_all(conn, sql: str, params: Optional[tuple[Any, ...]] = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return list(cur.fetchall())


def ensure_table(conn) -> None:
    execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS source_scenario_validation_report_v1 (
            report_id BIGINT AUTO_INCREMENT PRIMARY KEY,
            profile_id VARCHAR(100) NOT NULL,
            baseline_target_date DATE NOT NULL,
            target_date DATE NOT NULL,
            scenario_id VARCHAR(100) NOT NULL,
            expected_effect VARCHAR(255) NOT NULL,
            observed_effect VARCHAR(255) NOT NULL,
            validation_status VARCHAR(40) NOT NULL,
            baseline_row_count BIGINT NULL,
            scenario_row_count BIGINT NULL,
            row_delta BIGINT NULL,
            row_ratio DECIMAL(18,6) NULL,
            affected_row_count BIGINT NULL,
            affected_ratio DECIMAL(18,6) NULL,
            checksum VARCHAR(128) NULL,
            reason_json JSON NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_source_scenario_validation
              (profile_id, baseline_target_date, target_date, scenario_id),
            KEY idx_ssvr_profile_target (profile_id, target_date),
            KEY idx_ssvr_status (validation_status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """,
    )
    conn.commit()


def expected_effect(scenario_id: str) -> str:
    mapping = {
        "source_campaign_spike": "row_count should increase versus baseline and affected rows should exist",
        "source_weather_drop": "row_count should decrease or affected rows should exist due to weather effect",
        "source_system_degraded": "affected rows should exist with system degradation timeline",
        "source_no_data": "row_count should decrease versus baseline or affected rows should exist due to suppressed input",
    }
    return mapping.get(scenario_id, "scenario should produce source generation summary")


def validate_row(scenario: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    scenario_id = scenario["scenario_id"]
    baseline_rows = int(baseline["row_count"] or 0)
    scenario_rows = int(scenario["row_count"] or 0)
    affected = int(scenario.get("affected_row_count") or 0)
    row_delta = scenario_rows - baseline_rows
    row_ratio = (scenario_rows / baseline_rows) if baseline_rows else None
    affected_ratio = (affected / scenario_rows) if scenario_rows else None

    status = "NEEDS_MORE_EVIDENCE"
    observed = f"baseline={baseline_rows}, scenario={scenario_rows}, affected={affected}"

    if scenario_id == "source_campaign_spike":
        status = "PASS" if scenario_rows > baseline_rows and affected > 0 else "FAIL"
    elif scenario_id == "source_weather_drop":
        status = "PASS" if affected > 0 and scenario_rows <= baseline_rows else "NEEDS_MORE_EVIDENCE"
    elif scenario_id == "source_system_degraded":
        status = "PASS" if affected > 0 else "FAIL"
    elif scenario_id == "source_no_data":
        status = "PASS" if affected > 0 and scenario_rows < baseline_rows else "NEEDS_MORE_EVIDENCE"
    else:
        status = "PASS" if scenario_rows > 0 else "FAIL"

    return {
        "profile_id": scenario["profile_id"],
        "baseline_target_date": baseline["target_date"],
        "target_date": scenario["target_date"],
        "scenario_id": scenario_id,
        "expected_effect": expected_effect(scenario_id),
        "observed_effect": observed,
        "validation_status": status,
        "baseline_row_count": baseline_rows,
        "scenario_row_count": scenario_rows,
        "row_delta": row_delta,
        "row_ratio": row_ratio,
        "affected_row_count": affected,
        "affected_ratio": affected_ratio,
        "checksum": scenario.get("output_file_checksum"),
        "reason_json": '{"rule_version":"v04_phase1_source_validation_v1"}',
    }


def upsert_report(conn, report: dict[str, Any]) -> None:
    execute(
        conn,
        """
        INSERT INTO source_scenario_validation_report_v1
        (profile_id, baseline_target_date, target_date, scenario_id,
         expected_effect, observed_effect, validation_status,
         baseline_row_count, scenario_row_count, row_delta, row_ratio,
         affected_row_count, affected_ratio, checksum, reason_json, created_at)
        VALUES
        (%(profile_id)s, %(baseline_target_date)s, %(target_date)s, %(scenario_id)s,
         %(expected_effect)s, %(observed_effect)s, %(validation_status)s,
         %(baseline_row_count)s, %(scenario_row_count)s, %(row_delta)s, %(row_ratio)s,
         %(affected_row_count)s, %(affected_ratio)s, %(checksum)s, %(reason_json)s, NOW())
        ON DUPLICATE KEY UPDATE
          expected_effect=VALUES(expected_effect),
          observed_effect=VALUES(observed_effect),
          validation_status=VALUES(validation_status),
          baseline_row_count=VALUES(baseline_row_count),
          scenario_row_count=VALUES(scenario_row_count),
          row_delta=VALUES(row_delta),
          row_ratio=VALUES(row_ratio),
          affected_row_count=VALUES(affected_row_count),
          affected_ratio=VALUES(affected_ratio),
          checksum=VALUES(checksum),
          reason_json=VALUES(reason_json),
          created_at=NOW()
        """,
        report,
    )


def main() -> None:
    args = parse_args()
    conn = connect(args)
    try:
        ensure_table(conn)
        baseline = fetch_one(
            conn,
            """
            SELECT *
            FROM source_generation_result_summary
            WHERE profile_id=%s AND target_date=%s AND scenario_id='baseline'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (args.profile_id, args.baseline_date),
        )
        if not baseline:
            raise RuntimeError(f"baseline summary not found: profile={args.profile_id} date={args.baseline_date}")

        scenarios = fetch_all(
            conn,
            """
            SELECT *
            FROM source_generation_result_summary
            WHERE profile_id=%s
              AND target_date BETWEEN %s AND %s
              AND scenario_id IN ('source_campaign_spike','source_weather_drop','source_system_degraded','source_no_data')
            ORDER BY target_date, scenario_id, created_at DESC
            """,
            (args.profile_id, args.dt_from, args.dt_to),
        )

        # Keep latest row per scenario/date.
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for row in scenarios:
            key = (str(row["target_date"]), row["scenario_id"])
            if key not in latest:
                latest[key] = row

        reports = [validate_row(row, baseline) for row in latest.values()]
        for report in reports:
            upsert_report(conn, report)
        conn.commit()

        print("[OK] source_scenario_validation_report_v1 rows", len(reports))
        for report in reports:
            print(
                "[REPORT]",
                report["target_date"],
                report["scenario_id"],
                report["validation_status"],
                "row_ratio=", report["row_ratio"],
                "affected_ratio=", report["affected_ratio"],
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
