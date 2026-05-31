#!/usr/bin/env python3
from __future__ import annotations
import sys
from pipelines.commerce.lineage.audit_v05_scenario_identity import main as audit_main

if __name__ == "__main__":
    if "--fail-on-mismatch" not in sys.argv:
        sys.argv.append("--fail-on-mismatch")
    raise SystemExit(audit_main())
