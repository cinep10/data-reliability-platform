#!/usr/bin/env python3
from pathlib import Path
import os
import re

ROOT = Path(os.environ.get('PROJECT_ROOT', '.')).resolve()

r_path = ROOT / 'pipelines/commerce/analytics/build_v05_reliability_analysis.R'
if not r_path.exists():
    raise SystemExit(f'missing {r_path}')
text = r_path.read_text()
orig = text
marker = '# Phase4-C baseline evidence v2 guard: traffic preservation is normal, not anomaly evidence.'
# Remove the earlier inserted guard block. It can break parsing if it landed inside a list/function call.
# The guard is no longer needed because the validator now treats traffic_preservation as normality evidence
# and ignores business_kpi_distortion when no criticality/conversion signal exists.
if marker in text:
    start = text.find(marker)
    # Prefer removing until the next known runtime log marker or authority pattern section.
    candidates = []
    for pat in ['cat(sprintf("[GENERIC_EVIDENCE_V2]', "cat(sprintf('[GENERIC_EVIDENCE_V2]", '[AUTHORITY_PATTERN_LAYER]', 'pattern_layer_version']:
        idx = text.find(pat, start)
        if idx > start:
            candidates.append(idx)
    if candidates:
        end = min(candidates)
        # Preserve the marker/line found as the next section.
        text = text[:start].rstrip() + '\n\n' + text[end:].lstrip()
    else:
        # Fallback: remove through the first complete if block after business_kpi_distortion_score guard.
        m = re.search(r'\n# Phase4-C baseline evidence v2 guard:.*?\nif \(exists\("business_kpi_distortion_score".*?\n\}\n', text[start:], flags=re.S)
        if m:
            text = text[:start] + text[start + m.end():]
        else:
            raise SystemExit('found guard marker but could not identify removable block')
    print(f'[PATCH] removed misplaced Phase4-C baseline evidence v2 guard from {r_path}')
else:
    print(f'[SKIP] no misplaced Phase4-C baseline evidence v2 guard marker in {r_path}')

# Add a parse-safe comment marker only, not executable guard code.
safe_marker = '# Phase4-C baseline evidence v2 guard handled in validate_v05_authority_evidence_layer.py; no inline R guard required.'
if safe_marker not in text:
    # Add near GENERIC_EVIDENCE_V2 log if present, otherwise append comment.
    idx = text.find('[GENERIC_EVIDENCE_V2]')
    if idx >= 0:
        line_start = text.rfind('\n', 0, idx)
        text = text[:line_start+1] + safe_marker + '\n' + text[line_start+1:]
    else:
        text = text.rstrip() + '\n' + safe_marker + '\n'

if text != orig:
    r_path.write_text(text)

# Patch validator to make baseline-zero semantics robust if prior patch did not land.
val_path = ROOT / 'pipelines/commerce/validation/validate_v05_authority_evidence_layer.py'
if val_path.exists():
    vtxt = val_path.read_text()
    vorig = vtxt
    old = 'max_signal = max(baseline, statistical, propagation, impact, concentration, criticality, business_kpi_distortion, traffic_preservation)'
    new = '''# traffic_preservation is normality/preservation evidence, not anomaly evidence.
            # business_kpi_distortion should count as anomaly evidence only when criticality exists.
            event_criticality = fval(row, "event_criticality_score")
            conversion_criticality = fval(row, "conversion_criticality_score")
            revenue_criticality = fval(row, "revenue_criticality_score")
            business_kpi_distortion_for_signal = business_kpi_distortion if max(criticality, event_criticality, conversion_criticality, revenue_criticality) >= 0.05 else 0.0
            max_signal = max(
                baseline,
                statistical,
                propagation,
                impact,
                concentration,
                criticality,
                event_criticality,
                conversion_criticality,
                revenue_criticality,
                business_kpi_distortion_for_signal,
            )'''
    if old in vtxt:
        vtxt = vtxt.replace(old, new)
        print(f'[PATCH] validator max_signal excludes traffic_preservation baseline normality in {val_path}')
    elif 'business_kpi_distortion_for_signal' in vtxt:
        print(f'[SKIP] validator baseline-zero semantics already patched in {val_path}')
    else:
        print(f'[WARN] validator max_signal pattern not found; please inspect {val_path}')
    if vtxt != vorig:
        val_path.write_text(vtxt)
else:
    print(f'[WARN] missing validator {val_path}')

print('[OK] Phase4-C reliability-analysis R syntax guard hotfix applied')
