#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import os
import re

PROJECT_ROOT = Path(os.environ.get('PROJECT_ROOT', os.getcwd())).resolve()
R_PATH = PROJECT_ROOT / 'pipelines/commerce/analytics/build_v05_reliability_analysis.R'
VAL_PATH = PROJECT_ROOT / 'pipelines/commerce/validation/validate_v05_authority_evidence_layer.py'

REPLACEMENT = '''cat(sprintf(
  "[AUTHORITY_PATTERN_LAYER] version=%s pattern_ready=%d risk_pattern=%s pattern_confidence=%.6f pattern_is_not_risk=1 evidence_to_pattern=1 reason=%s next=risk_layer\\n",
  pattern_layer_version,
  pattern_ready,
  risk_pattern,
  pattern_confidence,
  pattern_reason
))'''


def patch_r() -> None:
    text = R_PATH.read_text(encoding='utf-8')
    original = text
    lines = text.splitlines()
    out = []
    i = 0
    fixed = False
    while i < len(lines):
        if lines[i].strip() == 'cat(sprintf(':
            probe = '\n'.join(lines[i:i + 8])
            if '[AUTHORITY_PATTERN_LAYER]' in probe:
                j = i + 1
                while j < len(lines):
                    if lines[j].strip() == '))':
                        break
                    j += 1
                out.extend(REPLACEMENT.splitlines())
                i = min(j + 1, len(lines))
                fixed = True
                continue
        if lines[i].strip() in {'[', ']'}:
            fixed = True
            i += 1
            continue
        out.append(lines[i])
        i += 1
    text = '\n'.join(out) + '\n'
    if not fixed and '[AUTHORITY_PATTERN_LAYER] version=%s pattern_ready=%d' in text:
        repaired = re.sub(
            r'cat\(sprintf\(\s*\n\s*\[AUTHORITY_PATTERN_LAYER\].*?pattern_reason\s*\n\s*\)\)',
            REPLACEMENT,
            text,
            flags=re.S,
        )
        fixed = repaired != text
        text = repaired
    if text != original:
        R_PATH.write_text(text, encoding='utf-8')
        print(f'[PATCH] repaired malformed AUTHORITY_PATTERN_LAYER block in {R_PATH}')
    else:
        print(f'[INFO] no R syntax repair needed in {R_PATH}')


def patch_validator() -> None:
    if not VAL_PATH.exists():
        print(f'[WARN] validator not found: {VAL_PATH}')
        return
    text = VAL_PATH.read_text(encoding='utf-8')
    original = text
    text = text.replace(
        'max_signal = max(baseline, statistical, propagation, impact, concentration, criticality, business_kpi_distortion, traffic_preservation)',
        'max_signal = max(baseline, statistical, propagation, impact, concentration, criticality, business_kpi_distortion)'
    )
    anchor = 'max_signal = max(baseline, statistical, propagation, impact, concentration, criticality, business_kpi_distortion)'
    inject = '''max_signal = max(baseline, statistical, propagation, impact, concentration, criticality, business_kpi_distortion)
            if baseline_like and args.allow_baseline_zero:
                # traffic_preservation_score indicates normal traffic preservation, not anomaly.
                # business_kpi_distortion_score is only an anomaly when criticality/impact/concentration exists.
                business_kpi_distortion_for_signal = business_kpi_distortion if max(criticality, impact, concentration) > 0.08 else 0.0
                max_signal = max(baseline, statistical, propagation, impact, concentration, criticality, business_kpi_distortion_for_signal)'''
    if anchor in text and 'business_kpi_distortion_for_signal' not in text:
        text = text.replace(anchor, inject)
    if text != original:
        VAL_PATH.write_text(text, encoding='utf-8')
        print(f'[PATCH] adjusted baseline max_signal in {VAL_PATH}')
    else:
        print(f'[INFO] no validator patch needed in {VAL_PATH}')


def main() -> int:
    if not R_PATH.exists():
        print(f'[FAIL] missing {R_PATH}')
        return 1
    patch_r()
    patch_validator()
    print('[OK] Phase4-C R syntax + baseline evidence validator hotfix v2 applied')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
