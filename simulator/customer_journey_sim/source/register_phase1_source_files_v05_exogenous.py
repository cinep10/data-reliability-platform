from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import pymysql

ROLES = [
    ("behavior", "*_behavior.w3c.log"),
    ("transaction", "*_transaction.jsonl"),
    ("state", "*_state.jsonl"),
    ("journey", "*_journey.jsonl"),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Register v0.5 Phase1 behavior/transaction/state/journey files into "
            "source_generation_run and source_file_manifest with exogenous provenance."
        )
    )
    p.add_argument("--db-host", required=True)
    p.add_argument("--db-port", type=int, required=True)
    p.add_argument("--db-user", required=True)
    p.add_argument("--db-pass", required=True)
    p.add_argument("--db-name", required=True)

    p.add_argument("--profile-id", required=True)
    p.add_argument("--target-date", required=True)
    p.add_argument("--scenario-name", default="baseline")
    p.add_argument("--scenario-id")
    p.add_argument("--experiment-id")
    p.add_argument("--input-dir", required=True)
    p.add_argument("--source-gen-run-id", type=int)

    p.add_argument("--scenario-mode", default="source_injection")
    p.add_argument("--source-mode", default="simulator_file_generate")
    p.add_argument("--exogenous-mode", default="timeline_db_v1")
    p.add_argument("--simulator-version", default="v05_phase1_journey")
    p.add_argument("--created-by", default="v05_phase1")
    p.add_argument("--note", default="registered from v0.5 Phase1 generated files")

    p.add_argument("--profile-config")
    p.add_argument("--scenario-config")
    p.add_argument("--exogenous-config")
    p.add_argument("--generator-config-hash")
    p.add_argument("--exogenous-snapshot-id", type=int)
    p.add_argument("--timeline-snapshot-id", type=int)
    p.add_argument("--strict-schema", action="store_true", help="Fail if metadata columns are missing instead of skipping them.")
    return p.parse_args()


def conn(a: argparse.Namespace):
    return pymysql.connect(
        host=a.db_host,
        port=a.db_port,
        user=a.db_user,
        password=a.db_pass,
        database=a.db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def table_columns(c, table_name: str) -> set[str]:
    with c.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s
            """,
            (table_name,),
        )
        return {str(r["column_name"]) for r in cur.fetchall()}


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha_optional_file(path_value: Optional[str]) -> Optional[str]:
    if not path_value:
        return None
    p = Path(path_value)
    if not p.exists():
        return sha_text(json.dumps({"missing_path": path_value}, sort_keys=True))
    return sha_file(p)


def generator_hash(a: argparse.Namespace) -> str:
    if a.generator_config_hash:
        return a.generator_config_hash
    payload = {
        "profile_id": a.profile_id,
        "target_date": a.target_date,
        "scenario_name": a.scenario_name,
        "scenario_id": a.scenario_id or a.scenario_name,
        "experiment_id": a.experiment_id,
        "profile_config_hash": sha_optional_file(a.profile_config),
        "scenario_config_hash": sha_optional_file(a.scenario_config),
        "exogenous_config_hash": sha_optional_file(a.exogenous_config),
        "simulator_version": a.simulator_version,
    }
    return sha_text(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def count_records(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def discover_files(input_dir: Path) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for role, pattern in ROLES:
        for p in sorted(input_dir.glob(pattern)):
            files.append((role, p))
    return files


def insert_dynamic(cur, table: str, columns: set[str], values: dict[str, Any], strict: bool = False) -> int:
    insert_cols = [c for c in values if c in columns]
    skipped = [c for c in values if c not in columns and values[c] is not None]
    if strict and skipped:
        raise RuntimeError(f"{table} missing expected columns: {', '.join(skipped)}")
    if not insert_cols:
        raise RuntimeError(f"{table} has no compatible columns for insert")
    placeholders = ",".join(["%s"] * len(insert_cols))
    sql = f"INSERT INTO {table} ({','.join(insert_cols)}) VALUES ({placeholders})"
    cur.execute(sql, tuple(values[c] for c in insert_cols))
    return int(cur.lastrowid or 0)


def update_dynamic(cur, table: str, columns: set[str], pk_col: str, pk: int, values: dict[str, Any]) -> None:
    set_cols = [c for c in values if c in columns]
    if not set_cols:
        return
    assignments = ", ".join([f"{c}=%s" for c in set_cols])
    cur.execute(f"UPDATE {table} SET {assignments} WHERE {pk_col}=%s", tuple(values[c] for c in set_cols) + (pk,))


def main() -> int:
    a = parse_args()
    input_dir = Path(a.input_dir)
    if not input_dir.exists():
        raise SystemExit(f"input-dir not found: {input_dir}")
    files = discover_files(input_dir)
    if not files:
        raise SystemExit(f"no v0.5 Phase1 source files found in {input_dir}")

    scenario_id = a.scenario_id or a.scenario_name
    experiment_id = a.experiment_id or f"v05_{a.profile_id}_{a.target_date}_{scenario_id}"
    gen_hash = generator_hash(a)
    exo_hash = sha_optional_file(a.exogenous_config)

    c = conn(a)
    try:
        run_cols = table_columns(c, "source_generation_run")
        manifest_cols = table_columns(c, "source_file_manifest")
        with c.cursor() as cur:
            source_gen_run_id = a.source_gen_run_id
            if source_gen_run_id:
                update_dynamic(
                    cur,
                    "source_generation_run",
                    run_cols,
                    "source_gen_run_id",
                    source_gen_run_id,
                    {
                        "experiment_id": experiment_id,
                        "scenario_id": scenario_id,
                        "scenario_name": a.scenario_name,
                        "scenario_mode": a.scenario_mode,
                        "source_mode": a.source_mode,
                        "exogenous_mode": a.exogenous_mode,
                        "generator_config_hash": gen_hash,
                        "exogenous_config_hash": exo_hash,
                        "timeline_snapshot_id": a.timeline_snapshot_id,
                        "exogenous_snapshot_id": a.exogenous_snapshot_id,
                        "status": "completed",
                        "ended_at": None,
                        "note": a.note,
                    },
                )
            else:
                source_gen_run_id = insert_dynamic(
                    cur,
                    "source_generation_run",
                    run_cols,
                    {
                        "profile_id": a.profile_id,
                        "target_date": a.target_date,
                        "experiment_id": experiment_id,
                        "scenario_id": scenario_id,
                        "scenario_name": a.scenario_name,
                        "scenario_mode": a.scenario_mode,
                        "source_mode": a.source_mode,
                        "exogenous_mode": a.exogenous_mode,
                        "simulator_version": a.simulator_version,
                        "generator_config_hash": gen_hash,
                        "exogenous_config_hash": exo_hash,
                        "timeline_snapshot_id": a.timeline_snapshot_id,
                        "exogenous_snapshot_id": a.exogenous_snapshot_id,
                        "status": "completed",
                        "ended_at": None,
                        "created_by": a.created_by,
                        "note": a.note,
                    },
                    strict=a.strict_schema,
                )
            cur.execute("DELETE FROM source_file_manifest WHERE source_gen_run_id=%s", (source_gen_run_id,))
            inserted = 0
            for role, p in files:
                insert_dynamic(
                    cur,
                    "source_file_manifest",
                    manifest_cols,
                    {
                        "source_gen_run_id": source_gen_run_id,
                        "exogenous_snapshot_id": a.exogenous_snapshot_id,
                        "timeline_snapshot_id": a.timeline_snapshot_id,
                        "profile_id": a.profile_id,
                        "target_date": a.target_date,
                        "service_domain": role,
                        "source_role": role,
                        "file_path": str(p),
                        "file_name": p.name,
                        "file_size_bytes": p.stat().st_size,
                        "checksum": sha_file(p),
                        "record_count": count_records(p),
                        "experiment_id": experiment_id,
                        "scenario_id": scenario_id,
                        "scenario_name": a.scenario_name,
                        "generator_config_hash": gen_hash,
                        "exogenous_config_hash": exo_hash,
                    },
                    strict=False,
                )
                inserted += 1
        c.commit()
        print(f"[register_phase1_source_files_v05_exogenous] source_gen_run_id={source_gen_run_id} files={inserted} experiment_id={experiment_id} scenario_id={scenario_id}")
        print(source_gen_run_id)
        return 0
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
