#!/usr/bin/env python3
"""Export a lightweight Collection Reliability markdown report from SQL evidence output.

This script intentionally avoids database libraries. It runs mysql CLI with the evidence SQL,
captures tab-separated output, and writes a markdown evidence appendix.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--sql-file", default="scripts/query_collection_reliability_evidence.sql")
    p.add_argument("--out", default="artifacts/collection_reliability_report.md")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", default="3306")
    p.add_argument("--db-user", default="nethru")
    p.add_argument("--db-pass", default="nethru1234")
    p.add_argument("--db-name", default="weblog")
    return p.parse_args()


def run_mysql(args: argparse.Namespace) -> str:
    sql_path = pathlib.Path(args.sql_file)
    if not sql_path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")
    cmd = [
        "mysql",
        "-h", args.db_host,
        "-P", str(args.db_port),
        "-u", args.db_user,
        f"-p{args.db_pass}",
        "--table",
        args.db_name,
    ]
    proc = subprocess.run(cmd, input=sql_path.read_text(encoding="utf-8"), text=True, capture_output=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout


def main() -> None:
    args = parse_args()
    output = run_mysql(args)
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = f"""# Collection Reliability Evidence Report

Generated at: {now}

## Scope

This report validates the v0.5 collection path as a diagnostic module:

```text
Source -> Stage -> Collector -> Raw Event -> Canonical -> Measurement
```

The report is evidence-only. Semantic risk, unified risk, transaction/state reconciliation, and operational actions are intentionally excluded.

## Evidence Output

```text
{output.rstrip()}
```

## Interpretation Guide

- `B_COUNT_CHAIN` should be non-zero from source through measurement tables for baseline.
- `C_COLLECTOR_DELTA.estimated_collector_drop_rate` should increase when `DROP_RATE` is injected.
- `C_COLLECTOR_DELTA.estimated_collector_dup_rate` or `F_STREAM_MEASUREMENT.duplicate_rate` should increase when `DUP_RATE` is injected.
- `D_CANONICAL_COVERAGE.schema_version_coverage` and `schema_flag_count` explain schema reliability.
- `D_CANONICAL_COVERAGE.uid_coverage`, `pcid_coverage`, and `identity_flag_count` explain identity reliability.
"""
    out_path.write_text(report, encoding="utf-8")
    print(f"[DONE] wrote {out_path}")


if __name__ == "__main__":
    main()
