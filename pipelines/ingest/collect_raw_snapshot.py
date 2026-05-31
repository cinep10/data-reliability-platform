from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pymysql


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile-id", required=True)
    ap.add_argument("--target-date", required=True)
    ap.add_argument("--source-gen-run-id", required=True, type=int)
    ap.add_argument("--input-dir", required=True)

    ap.add_argument("--db-host", required=True)
    ap.add_argument("--db-port", required=True, type=int)
    ap.add_argument("--db-user", required=True)
    ap.add_argument("--db-pass", required=True)
    ap.add_argument("--db-name", required=True)

    ap.add_argument("--source-mode", default="simulator_file_generate")
    ap.add_argument("--source-system", default="weblog_sim")
    return ap.parse_args()


def get_connection(args):
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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def fetch_source_files(conn, source_gen_run_id: int) -> list[dict]:
    sql = """
    SELECT source_file_id, file_name, file_path, exogenous_snapshot_id
    FROM source_file_manifest
    WHERE source_gen_run_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (source_gen_run_id,))
        return cur.fetchall()


def insert_raw_snapshot(conn, row: dict):
    sql = """
    INSERT INTO raw_snapshot_manifest (
        source_gen_run_id,
        exogenous_snapshot_id,
        source_file_id,
        profile_id,
        target_date,
        source_mode,
        source_system,
        raw_file_path,
        raw_file_name,
        checksum,
        record_count,
        collected_at,
        load_status,
        note
    ) VALUES (
        %(source_gen_run_id)s,
        %(exogenous_snapshot_id)s,
        %(source_file_id)s,
        %(profile_id)s,
        %(target_date)s,
        %(source_mode)s,
        %(source_system)s,
        %(raw_file_path)s,
        %(raw_file_name)s,
        %(checksum)s,
        %(record_count)s,
        NOW(),
        'collected',
        %(note)s
    )
    """
    with conn.cursor() as cur:
        cur.execute(sql, row)


def main():
    args = parse_args()
    conn = get_connection(args)

    try:
        source_files = fetch_source_files(conn, args.source_gen_run_id)
        inserted = 0

        for sf in source_files:
            path = Path(sf["file_path"])
            if not path.exists():
                continue

            row = {
                "source_gen_run_id": args.source_gen_run_id,
                "exogenous_snapshot_id": sf["exogenous_snapshot_id"],
                "source_file_id": sf["source_file_id"],
                "profile_id": args.profile_id,
                "target_date": args.target_date,
                "source_mode": args.source_mode,
                "source_system": args.source_system,
                "raw_file_path": str(path),
                "raw_file_name": path.name,
                "checksum": sha256_file(path),
                "record_count": count_lines(path),
                "note": "collected from source_file_manifest",
            }
            insert_raw_snapshot(conn, row)
            inserted += 1

        conn.commit()
        print(f"[OK] inserted {inserted} rows into raw_snapshot_manifest")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
