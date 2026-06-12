#!/usr/bin/env python3
"""Validate CASE-OBS-001 Phase4-D customer visual redesign v3.

This validator checks the figure manifest contract and generated file names. It
is intentionally manifest-driven; it does not OCR the PNGs. The R figure builder
writes the contract so CI can verify that the report is mechanism-routed and no
longer generic pattern/gap charts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--profile-id")
    p.add_argument("--target-date")
    p.add_argument("--scenario-name")
    p.add_argument("--run-id", type=int)
    p.add_argument("--source-gen-run-id", type=int)
    p.add_argument("--figure-dir", required=True)
    p.add_argument("--min-file-size", type=int, default=1024)
    p.add_argument("--require-decision-support", action="store_true")
    p.add_argument("--require-engineer-appendix", action="store_true")
    p.add_argument("--require-gap-signal", action="store_true")
    p.add_argument("--require-mobile-app-evidence", action="store_true")
    p.add_argument("--require-operational-report", action="store_true")
    p.add_argument("--require-customer-visual-redesign", action="store_true")
    p.add_argument("--require-visual-v2", action="store_true")
    p.add_argument("--require-visual-v3", action="store_true")
    p.add_argument("--require-visual-v4", action="store_true")
    p.add_argument("--require-visual-v5", action="store_true")
    p.add_argument("--require-visual-v6", action="store_true")
    p.add_argument("--require-visual-v7", action="store_true")
    return p.parse_args()


def load_manifest(figure_dir: Path) -> tuple[dict[str, Any], list[str]]:
    path = figure_dir / "figure_manifest.json"
    if not path.exists():
        return {}, [f"missing manifest: {path}"]
    try:
        return json.loads(path.read_text()), []
    except Exception as exc:
        return {}, [f"manifest parse error: {exc}"]


def require_png(figure_dir: Path, rel: str, failures: list[str], min_size: int) -> None:
    path = figure_dir / rel
    if not path.exists():
        failures.append(f"missing figure: {rel}")
        return
    if path.stat().st_size < min_size:
        failures.append(f"figure too small: {rel} size={path.stat().st_size} < {min_size}")


def fig_by_filename(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(fig.get("filename") or ""): fig for fig in manifest.get("figures") or []}


def as_list(x: Any) -> list[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def nested_get(d: dict[str, Any], *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def main() -> int:
    args = parse_args()
    figure_dir = Path(args.figure_dir)
    failures: list[str] = []
    if not figure_dir.exists():
        failures.append(f"figure_dir does not exist: {figure_dir}")
    manifest, mf = load_manifest(figure_dir)
    failures.extend(mf)

    if manifest:
        if args.profile_id and manifest.get("profile_id") not in (None, args.profile_id):
            failures.append(f"profile_id mismatch: {manifest.get('profile_id')} != {args.profile_id}")
        if args.target_date and manifest.get("target_date") not in (None, args.target_date):
            failures.append(f"target_date mismatch: {manifest.get('target_date')} != {args.target_date}")
        if args.scenario_name and manifest.get("scenario_name") not in (None, args.scenario_name):
            failures.append(f"scenario_name mismatch: {manifest.get('scenario_name')} != {args.scenario_name}")
        if args.run_id is not None and int(manifest.get("run_id") or -1) not in (-1, args.run_id):
            failures.append(f"run_id mismatch: {manifest.get('run_id')} != {args.run_id}")
        if args.source_gen_run_id is not None and int(manifest.get("source_gen_run_id") or -1) not in (-1, args.source_gen_run_id):
            failures.append(f"source_gen_run_id mismatch: {manifest.get('source_gen_run_id')} != {args.source_gen_run_id}")

    strict = args.require_operational_report or args.require_customer_visual_redesign or args.require_visual_v2 or args.require_visual_v3 or args.require_visual_v4 or args.require_visual_v5 or args.require_visual_v6 or args.require_visual_v7
    if strict:
        if manifest.get("report_type") != "operational_reliability_diagnostic_report":
            failures.append(f"report_type must be operational_reliability_diagnostic_report, got {manifest.get('report_type')!r}")
        if manifest.get("visualization_mode") != "diagnostic_report":
            failures.append(f"visualization_mode must be diagnostic_report, got {manifest.get('visualization_mode')!r}")
        for key in ("decision_reliability", "business_impact", "recommended_decision", "risk_pattern", "failure_mechanism", "mechanism_source"):
            if not manifest.get(key):
                failures.append(f"manifest missing {key}")

        mech = str(manifest.get("failure_mechanism") or "")
        pattern = str(manifest.get("risk_pattern") or "")
        if pattern == "silent_distortion" or mech == "critical_event_loss":
            if str(manifest.get("decision_reliability") or "").upper() != "LOW":
                failures.append("silent_distortion/critical_event_loss report must set decision_reliability=LOW")
            if str(manifest.get("business_impact") or "").upper() != "HIGH":
                failures.append("silent_distortion/critical_event_loss report must set business_impact=HIGH")
            if "purchase" not in str(manifest.get("recommended_decision") or "").lower() and "conversion" not in str(manifest.get("recommended_decision") or "").lower():
                failures.append("critical_event_loss recommended_decision must mention purchase or conversion")

        if manifest.get("obs_does_not_drive_risk") is not True:
            failures.append("manifest must set obs_does_not_drive_risk=true")
        if int(manifest.get("authority_action_count") or 0) < 1:
            failures.append("authority_action_count must be >= 1")
        if int(manifest.get("reference_obs_action_count") or 0) < 1:
            failures.append("reference_obs_action_count must be >= 1")
        ref_principle = str(manifest.get("reference_action_principle") or "") + " " + str((manifest.get("action_layer_summary") or {}).get("principle") or "")
        for token in ("OBS", "investigation", "do not drive risk"):
            if token not in ref_principle:
                failures.append(f"reference action principle missing token: {token}")

        report_layers = manifest.get("report_layers") or manifest.get("audience_layers") or {}
        for layer, minimum in (("business", 3), ("operational", 2), ("technical", 1)):
            if len(report_layers.get(layer) or []) < minimum:
                failures.append(f"report layer {layer} must contain at least {minimum} figures")

        required = [
            "business/fig01_can_we_trust_this_kpi.png",
            "business/fig02_how_much_data_is_missing.png",
            "business/fig03_business_kpi_impact_by_mechanism.png",
            "operational/fig04_operational_risk_vs_business_kpi_risk.png",
            "operational/fig05_recommended_action_plan.png",
            "technical/fig06_mechanism_root_cause_concentration.png",
        ]
        if args.require_engineer_appendix or args.require_visual_v2 or args.require_visual_v3 or args.require_visual_v4 or args.require_visual_v5 or args.require_visual_v6 or args.require_visual_v7:
            required += [
                "technical/appendix01_web_vs_wc_evidence.png",
                "technical/appendix02_baseline_current_delta_diagnosis.png",
                "technical/appendix03_mechanism_specific_evidence.png",
                "technical/appendix04_evidence_pattern_mechanism_risk_flow.png",
                "technical/appendix05_app_sdk_detailed_evidence.png",
            ]
        for rel in required:
            require_png(figure_dir, rel, failures, args.min_file_size)

        figs = fig_by_filename(manifest)
        expected_roles = {
            "fig01_can_we_trust_this_kpi.png": "business_decision_reliability",
            "fig03_business_kpi_impact_by_mechanism.png": "business_kpi_impact_ranking",
            "fig04_operational_risk_vs_business_kpi_risk.png": "operational_vs_business_kpi_risk",
            "fig05_recommended_action_plan.png": "primary_action_investigation_hint_card_table",
            "fig06_mechanism_root_cause_concentration.png": "mechanism_specific_root_cause_concentration",
            "appendix02_baseline_current_delta_diagnosis.png": "baseline_current_delta_interpretation",
            "appendix03_mechanism_specific_evidence.png": "mechanism_specific_supporting_evidence",
            "appendix04_evidence_pattern_mechanism_risk_flow.png": "evidence_pattern_mechanism_risk_decomposition",
        }
        for filename, role in expected_roles.items():
            if filename in figs and str(figs[filename].get("figure_role") or "") != role:
                failures.append(f"expected {filename} role={role}, got {figs[filename].get('figure_role')!r}")

    if args.require_customer_visual_redesign or args.require_visual_v2 or args.require_visual_v3 or args.require_visual_v4 or args.require_visual_v5 or args.require_visual_v6 or args.require_visual_v7:
        for key, expected in {
            "audience": "business_decision_support",
            "figure_message": "KPI trust decision support",
            "action_visualization_mode": "card_table",
        }.items():
            if manifest.get(key) != expected:
                failures.append(f"manifest {key} expected={expected!r} actual={manifest.get(key)!r}")
        for key in ("business_layer_ready", "mechanism_visible", "mechanism_source_visible", "authority_obs_separation_visible", "obs_reference_not_risk_engine"):
            if manifest.get(key) is not True:
                failures.append(f"manifest must set {key}=true")
        for key in ("failure_mechanism", "what_went_wrong", "mechanism_source", "where_to_investigate", "failure_type"):
            if not manifest.get(key):
                failures.append(f"manifest missing customer mechanism field: {key}")
        mapping = manifest.get("customer_term_mapping") or {}
        required_mapping = {
            "risk_pattern": "Failure Type",
            "failure_mechanism": "What went wrong",
            "mechanism_source": "Where to investigate",
            "authority_action": "Primary action",
            "obs_reference_action": "Investigation hint",
        }
        for k, v in required_mapping.items():
            if mapping.get(k) != v:
                failures.append(f"customer term mapping {k} expected={v!r} actual={mapping.get(k)!r}")
        if int(manifest.get("primary_action_count") or 0) < 1:
            failures.append("primary_action_count must be >= 1")
        if int(manifest.get("investigation_hint_count") or 0) < 1:
            failures.append("investigation_hint_count must be >= 1")

    if args.require_visual_v2 or args.require_visual_v3 or args.require_visual_v4 or args.require_visual_v5 or args.require_visual_v6 or args.require_visual_v7:
        fc = manifest.get("figure_contracts") or {}
        if nested_get(fc, "appendix02", "has_baseline_current_delta") is not True:
            failures.append("appendix02 must expose baseline/current/delta fields")
        fields = {str(x) for x in as_list(nested_get(fc, "appendix02", "fields"))}
        for required_field in {"Baseline", "Current", "Delta", "Control Band", "Interpretation"}:
            if required_field not in fields:
                failures.append(f"appendix02 missing field contract: {required_field}")
        if nested_get(fc, "appendix04", "has_evidence_pattern_mechanism_risk_flow") is not True:
            failures.append("appendix04 must expose Evidence -> Pattern -> Mechanism -> Risk flow")
        sections = {str(x) for x in as_list(nested_get(fc, "appendix04", "sections"))}
        for required_section in {"Evidence Primitive", "Failure Type", "Failure Mechanism", "Likelihood x Impact", "Risk", "Business Interpretation"}:
            if required_section not in sections:
                failures.append(f"appendix04 missing section: {required_section}")
        mechanism = str(manifest.get("failure_mechanism") or "")
        if args.require_visual_v6 or args.require_visual_v7:
            expected_by_scenario = {
                "baseline": ("stable", "none", "none"),
                "source_wc_collection_missing": ("localized_failure", "collection_completeness_loss", "broad_collection_gap"),
                "source_ios_app_version_collection_missing": ("localized_failure", "identity_integrity_breakage", "app_version_concentration"),
                "source_sdk_version_collection_missing": ("localized_failure", "semantic_attribution_distortion", "sdk_version_concentration"),
                "source_ios_purchase_event_collection_missing": ("silent_distortion", "critical_event_loss", "purchase_event_criticality"),
            }
            scen = str(manifest.get("scenario_name") or args.scenario_name or "")
            if scen in expected_by_scenario:
                exp_pattern, exp_mech, exp_source = expected_by_scenario[scen]
                if str(manifest.get("risk_pattern") or "") != exp_pattern:
                    failures.append(f"v6 scenario contract risk_pattern expected={exp_pattern} actual={manifest.get('risk_pattern')}")
                if str(manifest.get("failure_mechanism") or "") != exp_mech:
                    failures.append(f"v6 scenario contract failure_mechanism expected={exp_mech} actual={manifest.get('failure_mechanism')}")
                if str(manifest.get("mechanism_source") or "") != exp_source:
                    failures.append(f"v6 scenario contract mechanism_source expected={exp_source} actual={manifest.get('mechanism_source')}")
            if manifest.get("overall_risk_score") is None or manifest.get("final_risk_level") is None:
                failures.append("v6 manifest must expose overall_risk_score and final_risk_level")
        expected_view = {
            "identity_integrity_breakage": "identity_integrity_view",
            "semantic_attribution_distortion": "semantic_attribution_view",
            "critical_event_loss": "critical_event_view",
            "collection_completeness_loss": "collection_coverage_view",
            "none": "stable_view",
        }.get(mechanism)
        if expected_view and manifest.get("mechanism_view") != expected_view:
            failures.append(f"mechanism_view expected={expected_view} actual={manifest.get('mechanism_view')}")
        if expected_view and nested_get(fc, "fig06", "mechanism_specific_view") != expected_view:
            failures.append(f"fig06 mechanism_specific_view expected={expected_view} actual={nested_get(fc, 'fig06', 'mechanism_specific_view')}")
        label = str(manifest.get("mechanism_top_evidence_label") or "")
        expected_label_token = {
            "identity_integrity_breakage": "Login User Identification",
            "semantic_attribution_distortion": "Product / Category Attribution",
            "critical_event_loss": "Purchase Conversion",
            "collection_completeness_loss": "PV / Traffic",
            "none": "Stable KPI Monitoring",
        }.get(mechanism)
        if expected_label_token and expected_label_token not in label:
            failures.append(f"mechanism top evidence label expected token={expected_label_token!r} actual={label!r}")
        if nested_get(fc, "fig03", "mechanism_top_evidence_label") != manifest.get("mechanism_top_evidence_label"):
            failures.append("fig03 must use the same mechanism_top_evidence_label as manifest")
        a3 = nested_get(fc, "appendix03", "mechanism_specific_view")
        if expected_view and a3 != expected_view:
            failures.append(f"appendix03 mechanism_specific_view expected={expected_view} actual={a3}")
        if mechanism == "identity_integrity_breakage":
            if "Login" not in label and "Identification" not in label:
                failures.append("app-version mechanism must prioritize login/user identification evidence")
            if "identity" not in str(nested_get(fc, "fig06", "mechanism_specific_view")):
                failures.append("app-version fig06 must use identity-specific view")
            if "identity" not in str(nested_get(fc, "appendix03", "mechanism_specific_view")):
                failures.append("app-version appendix03 must use identity evidence, not URL evidence")
        if mechanism == "semantic_attribution_distortion":
            if "Attribution" not in label and "Category" not in label:
                failures.append("sdk-version mechanism must prioritize attribution/category evidence")
            if "semantic" not in str(nested_get(fc, "fig06", "mechanism_specific_view")):
                failures.append("sdk-version fig06 must use semantic attribution view")
            if "semantic" not in str(nested_get(fc, "appendix03", "mechanism_specific_view")):
                failures.append("sdk-version appendix03 must use semantic attribution evidence")
        if mechanism == "critical_event_loss":
            if "Purchase" not in label and "Conversion" not in label:
                failures.append("purchase-event mechanism must prioritize purchase/conversion evidence")
            if str(manifest.get("decision_reliability") or "").upper() != "LOW" or str(manifest.get("business_impact") or "").upper() != "HIGH":
                failures.append("critical_event_loss must be surfaced as LOW trust / HIGH business impact")

    if args.require_visual_v4 or args.require_visual_v5 or args.require_visual_v6 or args.require_visual_v7:
        fc = manifest.get("figure_contracts") or {}
        if nested_get(fc, "fig03", "differentiates_primary_secondary_scores") is not True:
            failures.append("fig03 must differentiate primary and secondary mechanism KPI scores")
        if nested_get(fc, "fig05", "prevents_text_clipping") is not True:
            failures.append("fig05 must declare text clipping prevention")
        if nested_get(fc, "fig05", "action_visualization_mode") != "compact_card_table":
            failures.append("fig05 must use compact_card_table mode")
        if nested_get(fc, "fig06", "numeric_labels_visible") is not True:
            failures.append("fig06 must declare visible numeric labels")
        if nested_get(fc, "appendix02", "mode") != "baseline_current_delta_table":
            failures.append("appendix02 must use baseline_current_delta_table mode")
        if nested_get(fc, "appendix04", "layout") != "vertical_flow_cards":
            failures.append("appendix04 must use vertical_flow_cards layout")
        if nested_get(fc, "appendix04", "prevents_text_clipping") is not True:
            failures.append("appendix04 must declare text clipping prevention")

        if args.require_visual_v5:
            if nested_get(fc, "fig03", "all_score_labels_identical") is True:
                failures.append("fig03 score labels must not all be identical")
            if nested_get(fc, "fig03", "score_values_distinct") is not True:
                failures.append("fig03 must expose distinct primary/secondary KPI scores")
            if nested_get(fc, "fig06", "all_score_labels_identical") is True:
                failures.append("fig06 numeric labels must not all be identical")
            if nested_get(fc, "fig06", "score_values_distinct") is not True:
                failures.append("fig06 must expose distinct mechanism evidence scores")
            if nested_get(fc, "fig05", "customer_readable_table") is not True:
                failures.append("fig05 must declare customer_readable_table=true")
            if "v5" not in str(manifest.get("visualization_layer") or "").lower() and not args.require_visual_v6:
                failures.append("visualization_layer must indicate v5 for --require-visual-v5")
        if args.require_visual_v6 or args.require_visual_v7:
            layer_name = str(manifest.get("visualization_layer") or "").lower()
            if args.require_visual_v6 and "v6" not in layer_name and not args.require_visual_v7:
                failures.append("visualization_layer must indicate v6 for --require-visual-v6")
            fc = manifest.get("figure_contracts") or {}
            # App/SDK must not collapse into the generic collection view in the customer report.
            scen = str(manifest.get("scenario_name") or args.scenario_name or "")
            if scen == "source_ios_app_version_collection_missing" and nested_get(fc, "fig03", "mechanism_view") != "identity_integrity_view":
                failures.append("v6/v7 app-version fig03 must be identity_integrity_view")
            if scen == "source_sdk_version_collection_missing" and nested_get(fc, "fig03", "mechanism_view") != "semantic_attribution_view":
                failures.append("v6/v7 sdk-version fig03 must be semantic_attribution_view")

        if args.require_visual_v7:
            layer_name = str(manifest.get("visualization_layer") or "").lower()
            if "v7" not in layer_name:
                failures.append("visualization_layer must indicate v7 for --require-visual-v7")
            fc = manifest.get("figure_contracts") or {}
            # v7 specifically fixes misleading 0%/100% app/SDK evidence charts by requiring
            # both appendix03 and fig06 to expose distinct mechanism evidence-profile scores.
            for section in ("fig06", "appendix03"):
                if nested_get(fc, section, "score_values_distinct") is not True:
                    failures.append(f"{section} must expose distinct mechanism evidence profile scores")
                if nested_get(fc, section, "all_score_labels_identical") is True:
                    failures.append(f"{section} labels must not all be identical")
                vals = nested_get(fc, section, "score_values") or []
                if isinstance(vals, (int, float)):
                    vals = [vals]
                rounded = {round(float(v), 4) for v in vals if str(v) not in {"", "None", "nan"}}
                if len(rounded) >= 2 and rounded.issubset({0.0, 1.0}):
                    failures.append(f"{section} should not be only 0/100 evidence values in v7")
            if manifest.get("failure_mechanism") == "identity_integrity_breakage":
                top = str(nested_get(fc, "fig06", "top_evidence_label") or "")
                if "App version" not in top and "UID" not in top and "Login" not in top:
                    failures.append("identity fig06 top evidence must reference app/UID/login evidence profile")
            if manifest.get("failure_mechanism") == "semantic_attribution_distortion":
                top = str(nested_get(fc, "fig06", "top_evidence_label") or "")
                if "SDK" not in top and "URL" not in top and "attribution" not in top.lower():
                    failures.append("semantic fig06 top evidence must reference SDK/URL attribution evidence profile")

        # File names must be final customer-report names, not legacy functional names.
        legacy = [
            "business/fig03_which_kpis_are_affected.png",
            "operational/fig04_why_this_is_not_critical.png",
            "technical/fig06_potential_investigation_candidates.png",
            "technical/appendix02_baseline_control_evidence.png",
            "technical/appendix04_pattern_driven_risk_decomposition.png",
        ]
        for rel in legacy:
            if (figure_dir / rel).exists():
                failures.append(f"legacy figure filename should not be generated in v4: {rel}")

    if not strict:
        figures = manifest.get("figures") or []
        if len(figures) < (9 if args.require_engineer_appendix else 5):
            failures.append(f"too few figures: {len(figures)}")
        for fig in figures:
            path = Path(str(fig.get("path") or ""))
            if path.exists() and path.stat().st_size < args.min_file_size:
                failures.append(f"manifest figure size too small: {fig.get('filename')}")

    print("[CASE_OBS_001_FIGURES]")
    print(f"figure_dir={figure_dir}")
    if manifest:
        print(f"report_type={manifest.get('report_type')} mode={manifest.get('visualization_mode')} layer={manifest.get('visualization_layer')}")
        print(f"audience={manifest.get('audience')} figure_message={manifest.get('figure_message')}")
        print(f"scenario={manifest.get('scenario_name')} run_id={manifest.get('run_id')} source_gen_run_id={manifest.get('source_gen_run_id')}")
        print(f"decision_reliability={manifest.get('decision_reliability')} business_impact={manifest.get('business_impact')} recommended_decision={manifest.get('recommended_decision')}")
        print(f"risk_pattern={manifest.get('risk_pattern')} failure_mechanism={manifest.get('failure_mechanism')} mechanism_source={manifest.get('mechanism_source')} mechanism_view={manifest.get('mechanism_view')} top_label={manifest.get('mechanism_top_evidence_label')}")
        layers = manifest.get("report_layers") or manifest.get("audience_layers") or {}
        for layer in ("business", "operational", "technical"):
            if layer in layers:
                print(f"  - layer={layer} figures={len(layers.get(layer) or [])}")
    if failures:
        print("[FAIL] " + "; ".join(failures))
        return 1
    print("[OK] validate_case_obs_001_figures passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
