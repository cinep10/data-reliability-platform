#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("PROJECT_ROOT", ".")).resolve()
R_PATH = ROOT / "pipelines/commerce/analytics/build_v05_reliability_analysis.R"
VALIDATOR_SRC = Path(__file__).resolve().parents[1] / "pipelines/commerce/validation/validate_v05_authority_evidence_layer.py"
VALIDATOR_DST = ROOT / "pipelines/commerce/validation/validate_v05_authority_evidence_layer.py"
SQL_SRC = Path(__file__).resolve().parents[1] / "sql/090_v05_evidence_v2_persistence_mariadb.sql"
SQL_DST = ROOT / "sql/090_v05_evidence_v2_persistence_mariadb.sql"

COL_ENSURES = '''
  ensure_column(con, "reliability_analysis_result_day_v05", "event_criticality_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "conversion_criticality_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "revenue_criticality_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "traffic_preservation_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "business_kpi_distortion_score", "DOUBLE NULL")
'''

INSERT_FIELDS = '''
  event_criticality_score = if (exists("event_criticality_score")) event_criticality_score else if (exists("criticality_evidence_score")) criticality_evidence_score else 0,
  conversion_criticality_score = if (exists("conversion_criticality_score")) conversion_criticality_score else if (exists("criticality_evidence_score")) criticality_evidence_score else 0,
  revenue_criticality_score = if (exists("revenue_criticality_score")) revenue_criticality_score else 0,
  traffic_preservation_score = if (exists("traffic_preservation")) traffic_preservation else if (exists("traffic_preservation_score")) traffic_preservation_score else 0,
  business_kpi_distortion_score = if (exists("business_kpi_distortion")) business_kpi_distortion else if (exists("business_kpi_distortion_score")) business_kpi_distortion_score else 0,
'''

PAYLOAD_HINT = '''
# Phase4-C evidence v2 persistence contract:
# - business_kpi_distortion and traffic_preservation are evidence values, not risk.
# - They must be persisted in reliability_analysis_result_day_v05 so validators,
#   Pattern v2, and Diagnostic Report can read the same Authority Evidence row.
'''

def patch_r() -> None:
    if not R_PATH.exists():
        raise SystemExit(f"missing {R_PATH}")
    text = R_PATH.read_text()
    changed = False
    if "business_kpi_distortion_score" not in text:
        # Insert ensure_column block near other authority interface/evidence columns if possible.
        anchor = 'ensure_column(con, "reliability_analysis_result_day_v05", "authority_input_payload_json"'
        idx = text.find(anchor)
        if idx >= 0:
            line_start = text.rfind("\n", 0, idx)
            text = text[:line_start+1] + COL_ENSURES + text[line_start+1:]
            changed = True
        else:
            # Fall back to appending a guarded ensure block after DB connection.
            anchor2 = "con <- connect_db(args)"
            pos = text.find(anchor2)
            if pos < 0:
                raise SystemExit("cannot find R insertion anchor for ensure columns")
            eol = text.find("\n", pos)
            fallback = '''
if (table_exists(con, "reliability_analysis_result_day_v05")) {
  ensure_column(con, "reliability_analysis_result_day_v05", "event_criticality_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "conversion_criticality_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "revenue_criticality_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "traffic_preservation_score", "DOUBLE NULL")
  ensure_column(con, "reliability_analysis_result_day_v05", "business_kpi_distortion_score", "DOUBLE NULL")
}
'''
            text = text[:eol+1] + fallback + text[eol+1:]
            changed = True

    if "business_kpi_distortion_score =" not in text:
        anchor = "analysis_payload_json = payload"
        idx = text.find(anchor)
        if idx < 0:
            raise SystemExit("cannot find insert_schema_aware analysis_payload_json anchor")
        line_start = text.rfind("\n", 0, idx)
        text = text[:line_start+1] + INSERT_FIELDS + text[line_start+1:]
        changed = True

    if "Phase4-C evidence v2 persistence contract" not in text:
        text = PAYLOAD_HINT + text
        changed = True

    if changed:
        R_PATH.write_text(text)
        print(f"[PATCH] updated {R_PATH}")
    else:
        print(f"[SKIP] {R_PATH} already contains evidence v2 persistence fields")


def main() -> int:
    patch_r()
    VALIDATOR_DST.parent.mkdir(parents=True, exist_ok=True)
    VALIDATOR_DST.write_text(VALIDATOR_SRC.read_text())
    print(f"[PATCH] replaced {VALIDATOR_DST}")
    SQL_DST.parent.mkdir(parents=True, exist_ok=True)
    SQL_DST.write_text(SQL_SRC.read_text())
    print(f"[PATCH] copied {SQL_DST}")
    print("[OK] Phase4-C evidence v2 persistence hotfix applied")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
