#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pymysql


def parse_args():
    p = argparse.ArgumentParser(description="Ensure and patch v05_semantic_action_calibration_review_day schema.")
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)
    return p.parse_args()


BASE_DDL = """
CREATE TABLE IF NOT EXISTS v05_semantic_action_calibration_review_day (
  review_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_id BIGINT NOT NULL,
  profile_id VARCHAR(128) NOT NULL,
  source_gen_run_id BIGINT NULL,
  target_date DATE NOT NULL,
  scenario_name VARCHAR(128) NOT NULL,
  expected_semantic_family VARCHAR(255) NULL,
  observed_semantic_risk VARCHAR(255) NULL,
  expected_action VARCHAR(255) NULL,
  observed_action VARCHAR(255) NULL,
  expected_escalation VARCHAR(64) NULL,
  observed_risk_level VARCHAR(64) NULL,
  observed_risk_score DOUBLE NULL,
  semantic_match_flag TINYINT(1) NOT NULL DEFAULT 0,
  action_match_flag TINYINT(1) NOT NULL DEFAULT 0,
  escalation_match_flag TINYINT(1) NOT NULL DEFAULT 0,
  calibration_result VARCHAR(64) NOT NULL DEFAULT 'REVIEW',
  calibration_status VARCHAR(64) NOT NULL DEFAULT 'REVIEW',
  review_status VARCHAR(64) NOT NULL DEFAULT 'REVIEW',
  review_reason TEXT NULL,
  review_payload_json LONGTEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_v05_semantic_action_review (profile_id, target_date, scenario_name, run_id, source_gen_run_id),
  KEY idx_v05_semantic_action_review_day (profile_id, target_date, scenario_name),
  KEY idx_v05_semantic_action_review_status (review_status, calibration_result)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


REQUIRED_COLUMNS = {
    "review_id": "BIGINT AUTO_INCREMENT PRIMARY KEY",
    "run_id": "BIGINT NOT NULL",
    "profile_id": "VARCHAR(128) NOT NULL",
    "source_gen_run_id": "BIGINT NULL",
    "target_date": "DATE NOT NULL",
    "scenario_name": "VARCHAR(128) NOT NULL",
    "expected_semantic_family": "VARCHAR(255) NULL",
    "observed_semantic_risk": "VARCHAR(255) NULL",
    "expected_action": "VARCHAR(255) NULL",
    "observed_action": "VARCHAR(255) NULL",
    "expected_escalation": "VARCHAR(64) NULL",
    "observed_risk_level": "VARCHAR(64) NULL",
    "observed_risk_score": "DOUBLE NULL",
    "semantic_match_flag": "TINYINT(1) NOT NULL DEFAULT 0",
    "action_match_flag": "TINYINT(1) NOT NULL DEFAULT 0",
    "escalation_match_flag": "TINYINT(1) NOT NULL DEFAULT 0",
    "calibration_result": "VARCHAR(64) NOT NULL DEFAULT 'REVIEW'",
    "calibration_status": "VARCHAR(64) NOT NULL DEFAULT 'REVIEW'",
    "review_status": "VARCHAR(64) NOT NULL DEFAULT 'REVIEW'",
    "review_reason": "TEXT NULL",
    "review_payload_json": "LONGTEXT NULL",
    "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "updated_at": "DATETIME NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP",
}


def col_map(cur):
    cur.execute(
        """
        SELECT column_name, is_nullable, column_default, data_type, column_type
        FROM information_schema.columns
        WHERE table_schema=DATABASE()
          AND table_name='v05_semantic_action_calibration_review_day'
        """
    )
    return {r[0]: {"nullable": r[1], "default": r[2], "data_type": r[3], "column_type": r[4]} for r in cur.fetchall()}


def has_index(cur, name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema=DATABASE()
          AND table_name='v05_semantic_action_calibration_review_day'
          AND index_name=%s
        """,
        (name,),
    )
    return int(cur.fetchone()[0]) > 0


def main() -> int:
    a = parse_args()
    con = pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with con.cursor() as cur:
            cur.execute(BASE_DDL)
            cols = col_map(cur)

            for name, spec in REQUIRED_COLUMNS.items():
                if name == "review_id":
                    continue
                if name not in cols:
                    cur.execute(f"ALTER TABLE v05_semantic_action_calibration_review_day ADD COLUMN `{name}` {spec}")
                    print(f"[ALTER] added column {name}")

            # Existing strict tables may have NOT NULL columns with no default.
            # Patch the columns that are commonly present from previous versions.
            cols = col_map(cur)
            if "calibration_result" in cols:
                cur.execute(
                    "ALTER TABLE v05_semantic_action_calibration_review_day "
                    "MODIFY COLUMN calibration_result VARCHAR(64) NOT NULL DEFAULT 'REVIEW'"
                )
                print("[ALTER] calibration_result default REVIEW")
            if "calibration_status" in cols:
                cur.execute(
                    "ALTER TABLE v05_semantic_action_calibration_review_day "
                    "MODIFY COLUMN calibration_status VARCHAR(64) NOT NULL DEFAULT 'REVIEW'"
                )
                print("[ALTER] calibration_status default REVIEW")
            if "review_status" in cols:
                cur.execute(
                    "ALTER TABLE v05_semantic_action_calibration_review_day "
                    "MODIFY COLUMN review_status VARCHAR(64) NOT NULL DEFAULT 'REVIEW'"
                )
                print("[ALTER] review_status default REVIEW")
            if "semantic_match_flag" in cols:
                cur.execute(
                    "ALTER TABLE v05_semantic_action_calibration_review_day "
                    "MODIFY COLUMN semantic_match_flag TINYINT(1) NOT NULL DEFAULT 0"
                )
            if "action_match_flag" in cols:
                cur.execute(
                    "ALTER TABLE v05_semantic_action_calibration_review_day "
                    "MODIFY COLUMN action_match_flag TINYINT(1) NOT NULL DEFAULT 0"
                )
            if "escalation_match_flag" in cols:
                cur.execute(
                    "ALTER TABLE v05_semantic_action_calibration_review_day "
                    "MODIFY COLUMN escalation_match_flag TINYINT(1) NOT NULL DEFAULT 0"
                )

            if not has_index(cur, "idx_v05_semantic_action_review_day"):
                cur.execute(
                    "CREATE INDEX idx_v05_semantic_action_review_day "
                    "ON v05_semantic_action_calibration_review_day(profile_id, target_date, scenario_name)"
                )
            if not has_index(cur, "idx_v05_semantic_action_review_status"):
                cur.execute(
                    "CREATE INDEX idx_v05_semantic_action_review_status "
                    "ON v05_semantic_action_calibration_review_day(review_status, calibration_result)"
                )
    finally:
        con.close()

    print("[OK] ensured v05_semantic_action_calibration_review_day schema/defaults")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
