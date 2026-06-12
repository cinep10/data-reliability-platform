from __future__ import annotations

from pathlib import Path
import csv
import hashlib
from typing import Iterable


def infer_service_domain(file_name: str) -> str:
    s = file_name.lower()
    if "auth" in s or "login" in s:
        return "auth"
    if "loan" in s:
        return "loan"
    if "card" in s:
        return "card"
    if "account" in s:
        return "account"
    if "transfer" in s:
        return "transfer"
    return "all"


def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_records(path: Path) -> int:
    if path.suffix.lower() in {".csv", ".tsv"}:
        with path.open("r", encoding="utf-8") as f:
            return max(sum(1 for _ in f) - 1, 0)
    return 0


def build_source_file_manifests(
    source_gen_run_id: int,
    exogenous_snapshot_id: int | None,
    profile_id: str,
    target_date: str,
    generated_files: Iterable[Path],
) -> list[dict]:
    out = []
    for path in generated_files:
        out.append(
            {
                "source_gen_run_id": source_gen_run_id,
                "exogenous_snapshot_id": exogenous_snapshot_id,
                "profile_id": profile_id,
                "target_date": target_date,
                "service_domain": infer_service_domain(path.name),
                "file_path": str(path),
                "file_name": path.name,
                "file_size_bytes": path.stat().st_size if path.exists() else 0,
                "checksum": sha256sum(path) if path.exists() else None,
                "record_count": count_records(path) if path.exists() else None,
            }
        )
    return out
