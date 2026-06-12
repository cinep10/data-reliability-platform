#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get('PROJECT_ROOT', os.getcwd())).resolve()
REGISTRY = ROOT / 'simulator/customer_journey_sim/configs/v05_scenario_registry.yaml'
SHELL = ROOT / 'deploy/run_v05_reliability_pipeline_commerce_mac_host.sh'
COLLECTOR = ROOT / 'pipelines/collect/collector_wc_log_hit_v04.py'

NEW_SCENARIO = '''  source_sdk_version_collection_missing:
    family: source_observability_anomaly
    source_generation_scenario: baseline
    use_exogenous: false
    runtime_apply: false
    runtime_apply_mode: wc_collection_missing
    expected_risk_family: observability_sdk_version_collection
    run_v04_evidence_measurement: true
    run_v04_legacy_decision: false
    run_v05_phase3_phase4: true
    run_integrated_validation: true
'''


def require(p: Path) -> None:
    if not p.exists():
        raise SystemExit(f'missing file: {p}')


def patch_registry() -> bool:
    require(REGISTRY)
    text = REGISTRY.read_text()
    if 'source_sdk_version_collection_missing:' in text:
        return False
    anchor = '  source_ios_purchase_event_collection_missing:'
    idx = text.find(anchor)
    if idx < 0:
        # fallback: insert after iOS SDK block by finding next known scenario after it
        anchor = '  source_ios_sdk_version_collection_missing:'
        idx0 = text.find(anchor)
        if idx0 < 0:
            raise SystemExit('registry anchor not found: source_ios_sdk_version_collection_missing')
        idx = text.find('\n  source_', idx0 + len(anchor))
        if idx < 0:
            idx = len(text)
    text = text[:idx] + NEW_SCENARIO + text[idx:]
    REGISTRY.write_text(text)
    return True


def patch_collector_match_token() -> bool:
    require(COLLECTOR)
    text = COLLECTOR.read_text()
    old = '''def _match_token(value: Any, expected: str) -> bool:
    expected = str(expected or "*").strip().lower()
    if not expected or expected == "*":
        return True
    return str(value or "").strip().lower() == expected
'''
    new = '''def _match_token(value: Any, expected: str) -> bool:
    expected = str(expected or "*").strip().lower()
    if not expected or expected == "*":
        return True
    actual = str(value or "").strip().lower()
    # Phase4-C: allow comma-separated target values so generic SDK scenarios can
    # target both iOS and Android SDK tags without creating case-specific risk logic.
    choices = {x.strip() for x in expected.split(",") if x.strip()}
    return actual in choices
'''
    if new in text:
        return False
    if old not in text:
        print('[WARN] collector _match_token anchor not found; leaving collector unchanged')
        return False
    COLLECTOR.write_text(text.replace(old, new))
    return True


def patch_shell() -> bool:
    require(SHELL)
    text = SHELL.read_text()
    original = text

    # Make existing iOS SDK case arms accept canonical generic scenario name.
    text = text.replace('source_ios_sdk_version_collection_missing)', 'source_ios_sdk_version_collection_missing|source_sdk_version_collection_missing)')
    text = text.replace('source_ios_app_version_collection_missing|source_ios_sdk_version_collection_missing)', 'source_ios_app_version_collection_missing|source_ios_sdk_version_collection_missing|source_sdk_version_collection_missing')

    # Convert generic SDK override values in the shared iOS/generic case arm.
    # Keep legacy source_ios_sdk_version_collection_missing compatible, but make
    # source_sdk_version_collection_missing a mobile SDK issue across app platforms.
    text = text.replace('WC_MISSING_TARGET_RULE_ID="ios_sdk_3_2_1_collection_missing"', 'WC_MISSING_TARGET_RULE_ID="sdk_version_collection_missing"')
    text = text.replace('WC_MISSING_TARGET_REASON="ios_sdk_version_collection_missing"', 'WC_MISSING_TARGET_REASON="sdk version WC tagging issue across mobile apps"')
    text = text.replace('WC_MISSING_TARGET_RULE_ID="IOS_SDK_VERSION_COLLECTION_MISSING_V1"', 'WC_MISSING_TARGET_RULE_ID="SDK_VERSION_COLLECTION_MISSING_V1"')
    text = text.replace('WC_MISSING_TARGET_REASON="iOS SDK beacon dispatch failure"', 'WC_MISSING_TARGET_REASON="Mobile SDK beacon dispatch/tagging failure"')
    text = text.replace('WC_MISSING_TARGET_REASON="ios SDK beacon dispatch missing"', 'WC_MISSING_TARGET_REASON="mobile SDK beacon dispatch/tagging missing"')

    # In generic SDK arms, support iOS and Android app platforms and SDK values.
    # _match_token now supports comma-separated values.
    text = text.replace('WC_MISSING_TARGET_APP_PLATFORM="ios_app"\n    WC_MISSING_TARGET_APP_VERSION="*"\n    WC_MISSING_TARGET_SDK_VERSION="wc-ios-3.2.1"',
                        'WC_MISSING_TARGET_APP_PLATFORM="ios_app,android_app"\n    WC_MISSING_TARGET_APP_VERSION="*"\n    WC_MISSING_TARGET_SDK_VERSION="${SDK_TARGET_VERSION:-wc-ios-3.2.1,wc-android-3.2.1}"')
    text = text.replace('WC_MISSING_TARGET_APP_PLATFORM="ios_app"\n    WC_MISSING_TARGET_APP_VERSION="*"\n    WC_MISSING_TARGET_SDK_VERSION="${IOS_TARGET_SDK_VERSION:-wc-ios-3.2.1}"',
                        'WC_MISSING_TARGET_APP_PLATFORM="ios_app,android_app"\n    WC_MISSING_TARGET_APP_VERSION="*"\n    WC_MISSING_TARGET_SDK_VERSION="${SDK_TARGET_VERSION:-wc-ios-3.2.1,wc-android-3.2.1}"')

    # Validation: canonical source_sdk_version_collection_missing should call sdk_version validator.
    text = text.replace('--expected-sdk-version "${IOS_TARGET_SDK_VERSION:-wc-ios-3.2.1}"', '--expected-sdk-version "${SDK_TARGET_VERSION_FOR_VALIDATION:-wc-ios-3.2.1}"')
    text = text.replace('--min-sdk-missing-rate "${MIN_IOS_SDK_MISSING_RATE:-0.20}"', '--min-sdk-missing-rate "${MIN_SDK_MISSING_RATE:-0.20}"')

    # Ensure required minimum broad mode stays compatible.
    text = text.replace('WC_MISSING_RULE_MODE="${WC_MISSING_RULE_MODE:-legacy_rate}"', 'WC_MISSING_RULE_MODE="${WC_MISSING_RULE_MODE:-broad}"')

    if text != original:
        SHELL.write_text(text)
        return True
    return False


def main() -> int:
    changed = []
    if patch_registry():
        changed.append('registry')
    if patch_collector_match_token():
        changed.append('collector')
    if patch_shell():
        changed.append('shell')
    print('[OK] phase4c sdk scenario registry/shell hotfix applied; changed=' + ','.join(changed or ['none']))
    print(f'[INFO] registry={REGISTRY}')
    print(f'[INFO] shell={SHELL}')
    print(f'[INFO] collector={COLLECTOR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
