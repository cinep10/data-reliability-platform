from __future__ import annotations

import argparse
from pathlib import Path
import sys


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path.read_text(encoding="utf-8", errors="replace")


def require_marker(path: Path, markers: list[str]) -> list[str]:
    text = read(path)
    return [m for m in markers if m not in text]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Validate v0.5 architecture reclassification markers: "
            "OBS reference, Baseline Science authority reference, Reliability "
            "Analysis authority analytics, Unified Risk authority risk, "
            "Semantic/Action knowledge base."
        )
    )
    p.add_argument("--project-root", default=".")
    p.add_argument("--contract", default="pipelines/commerce/configs/v05_authority_layer_contract.yaml")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.project_root).resolve()
    contract = Path(args.contract)
    if not contract.is_absolute():
        contract = root / contract

    checks: list[tuple[str, Path, list[str]]] = [
        (
            "contract",
            contract,
            [
                "OBS = Reference Evidence",
                "Baseline Science = Authority Reference Layer",
                "Reliability Analysis = Authority Analytics Layer",
                "Unified Risk = Authority Risk Layer",
                "Semantic/Action = Knowledge Base",
                "Risk = Likelihood x Impact",
            ],
        ),
        (
            "observability_reference_analysis",
            root / "pipelines/commerce/analytics/build_v05_observability_reliability_analysis.R",
            ["OBSERVABILITY REFERENCE EVIDENCE", "NOT the authority risk engine"],
        ),
        (
            "observability_interpretation",
            root / "pipelines/commerce/analytics/build_v05_observability_interpretation.R",
            ["OBSERVABILITY REFERENCE EVIDENCE", "Confidence is explanation confidence"],
        ),
        (
            "baseline_science",
            root / "pipelines/commerce/analytics/build_v05_baseline_science_statistical_evidence.R",
            ["BASELINE SCIENCE = AUTHORITY REFERENCE LAYER", "not an OBS feature"],
        ),
        (
            "reliability_analysis",
            root / "pipelines/commerce/analytics/build_v05_reliability_analysis.R",
            ["AUTHORITY ANALYTICS LAYER", "feed the authority risk model"],
        ),
        (
            "unified_risk",
            root / "pipelines/commerce/score/build_v05_unified_risk_score.R",
            ["AUTHORITY RISK LAYER", "Risk = Likelihood x Impact", "Confidence reported separately"],
        ),
        (
            "semantic_kb",
            root / "pipelines/commerce/semantic/build_v05_semantic_interpretation.R",
            ["KNOWLEDGE BASE", "Semantic is not the risk engine"],
        ),
        (
            "action_catalog",
            root / "pipelines/commerce/action/build_v05_action_recommendation.py",
            ["KNOWLEDGE BASE", "Action Catalog", "does not compute risk"],
        ),
        (
            "operation_shell",
            root / "deploy/run_v05_reliability_pipeline_commerce_mac_host.sh",
            [
                "OBS=reference evidence",
                "Baseline Science=authority reference",
                "Reliability Analysis=authority analytics",
                "Unified Risk=authority risk",
                "Semantic/Action=knowledge base",
            ],
        ),
    ]

    failures = []
    for name, path, markers in checks:
        try:
            missing = require_marker(path, markers)
        except Exception as exc:
            failures.append(f"{name}: cannot read {path}: {exc}")
            continue
        if missing:
            failures.append(f"{name}: missing markers {missing} in {path}")
        else:
            print(f"[PASS] {name}: architecture markers present")

    if failures:
        print("[FAIL] architecture reclassification validation failed")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("[OK] validate_v05_architecture_reclassification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
