#!/usr/bin/env python3
"""Materialize collector-layer observability anomaly provenance.

Uses v05_source_anomaly_trace_day when available, schema-aware. This keeps
collector-layer anomaly provenance visible without mutating runtime evidence.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict

import pymysql

TABLE = "v05_source_anomaly_trace_day"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", type=int, default=3306)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", default="")
    p.add_argument("--db-name", required=True)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--source-gen-run-id", type=int, required=True)
    return p.parse_args()


def connect(a):
    return pymysql.connect(host=a.db_host, port=a.db_port, user=a.db_user, password=a.db_pass, database=a.db_name, charset="utf8mb4", autocommit=False, cursorclass=pymysql.cursors.DictCursor)


def table_exists(cur, table):
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return int(cur.fetchone()["n"] or 0) > 0


def table_cols(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s", (table,))
    return {r["column_name"] for r in cur.fetchall()}


def fetch_measurement(cur, a):
    cur.execute(
        """
        SELECT * FROM v05_observability_measurement_day
        WHERE profile_id=%s AND target_date=%s AND scenario_name=%s AND run_id=%s AND source_gen_run_id=%s
        LIMIT 1
        """,
        (a.profile_id, a.target_date, a.scenario_name, a.run_id, a.source_gen_run_id),
    )
    return cur.fetchone()


def main():
    a = parse_args()
    cn = connect(a)
    try:
        with cn.cursor() as cur:
            if not table_exists(cur, TABLE):
                print(f"[INFO] skip materialize_v05_observability_anomaly_trace missing table={TABLE}")
                return 0
            m = fetch_measurement(cur, a)
            if not m:
                print("[INFO] skip materialize_v05_observability_anomaly_trace no measurement row")
                return 0
            cols = table_cols(cur, TABLE)
            row: Dict[str, Any] = {
                "profile_id": a.profile_id,
                "target_date": a.target_date,
                "dt": a.target_date,
                "run_id": a.run_id,
                "source_gen_run_id": a.source_gen_run_id,
                "scenario_name": a.scenario_name,
                "trace_id": f"{a.profile_id}-{a.target_date}-{a.run_id}-{a.source_gen_run_id}-observability",
                "anomaly_seq": 1,
                "anomaly_mode": "wc_collection_missing",
                "runtime_layer": "collection",
                "source_layer": "wc_collector",
                "anomaly_type": "wc_collection_missing",
                "affected_count": int(m.get("collection_gap_count") or 0),
                "total_count": int(m.get("web_hits") or 0),
                "affected_ratio": float(m.get("collection_gap_rate") or 0.0),
                "evidence_key": "web_wc_collection_gap",
                "evidence_value": f"web_hits={m.get('web_hits')};wc_hits={m.get('wc_hits')};gap={m.get('collection_gap_rate')}",
                "trace_json": json.dumps({"measurement": m}, default=str, ensure_ascii=False),
                "original_count": int(m.get("web_hits") or 0),
                "final_count": int(m.get("wc_hits") or 0),
            }
            insert_cols = [c for c in row if c in cols]
            if not insert_cols:
                print(f"[INFO] skip materialize_v05_observability_anomaly_trace no compatible columns in {TABLE}")
                return 0
            # Best effort idempotency.
            where = "profile_id=%s AND target_date=%s AND run_id=%s"
            params = [a.profile_id, a.target_date, a.run_id]
            if "source_gen_run_id" in cols:
                where += " AND source_gen_run_id=%s"; params.append(a.source_gen_run_id)
            if "anomaly_type" in cols:
                where += " AND anomaly_type=%s"; params.append("wc_collection_missing")
            cur.execute(f"DELETE FROM {TABLE} WHERE {where}", tuple(params))
            cur.execute(f"INSERT INTO {TABLE} ({','.join(insert_cols)}) VALUES ({','.join(['%s']*len(insert_cols))})", tuple(row[c] for c in insert_cols))
        cn.commit()
    except Exception:
        cn.rollback(); raise
    finally:
        cn.close()
    print(f"[OK] materialize_v05_observability_anomaly_trace affected={row['affected_count']} ratio={row['affected_ratio']:.6f}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
