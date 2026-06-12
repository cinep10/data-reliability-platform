#!/usr/bin/env python3
from pathlib import Path
import os

ROOT = Path(os.environ.get('PROJECT_ROOT', '.')).resolve()

# 1) Patch R reliability analysis with a generic baseline/normal guard for business KPI distortion.
r_path = ROOT / 'pipelines/commerce/analytics/build_v05_reliability_analysis.R'
if r_path.exists():
    txt = r_path.read_text()
    marker = '# Phase4-C baseline evidence v2 guard: traffic preservation is normal, not anomaly evidence.'
    guard = r'''
# Phase4-C baseline evidence v2 guard: traffic preservation is normal, not anomaly evidence.
# business_kpi_distortion_score must not have a positive floor when no critical event/conversion anomaly exists.
.safe_exists_num <- function(name, default=0) {
  if (exists(name, inherits=FALSE)) {
    v <- get(name, inherits=FALSE)
    suppressWarnings(as.numeric(ifelse(is.na(v), default, v)))
  } else {
    default
  }
}
.phase4c_conversion_gap_for_guard <- max(
  .safe_exists_num("conversion_gap", 0),
  .safe_exists_num("conversion_gap_rate", 0),
  .safe_exists_num("max_conversion_gap", 0),
  na.rm=TRUE
)
.phase4c_critical_signal_for_guard <- max(
  .safe_exists_num("criticality_evidence_score", 0),
  .safe_exists_num("event_criticality_score", 0),
  .safe_exists_num("conversion_criticality_score", 0),
  .safe_exists_num("revenue_criticality_score", 0),
  na.rm=TRUE
)
if (exists("business_kpi_distortion_score", inherits=FALSE)) {
  if (.phase4c_conversion_gap_for_guard < 0.05 && .phase4c_critical_signal_for_guard < 0.05) {
    business_kpi_distortion_score <- 0
  }
}
'''
    if marker not in txt:
        idx = txt.find('[GENERIC_EVIDENCE_V2]')
        if idx >= 0:
            # insert before the line that contains the log marker
            line_start = txt.rfind('\n', 0, idx)
            txt = txt[:line_start+1] + guard + '\n' + txt[line_start+1:]
        else:
            # fallback: append near the end; this is still safe for scripts that compute before insert/log earlier only if sourced late.
            txt += '\n' + guard + '\n'
        r_path.write_text(txt)
        print(f'[PATCH] inserted baseline evidence v2 guard into {r_path}')
    else:
        print(f'[SKIP] baseline evidence v2 guard already present in {r_path}')
else:
    print(f'[WARN] missing {r_path}')

# 2) Replace validator with safer baseline-zero semantics.
val_path = ROOT / 'pipelines/commerce/validation/validate_v05_authority_evidence_layer.py'
if val_path.exists():
    txt = val_path.read_text()
    # Replace max_signal calculation block robustly.
    old = 'max_signal = max(baseline, statistical, propagation, impact, concentration, criticality, business_kpi_distortion, traffic_preservation)'
    new = '''# traffic_preservation is a normality/preservation indicator, not an anomaly signal.
            # For baseline-zero validation, include only anomaly-direction evidence.
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
    if old in txt:
        txt = txt.replace(old, new)
    elif 'traffic_preservation)' in txt and 'business_kpi_distortion_for_signal' not in txt:
        txt = txt.replace('max_signal = max(baseline, statistical, propagation, impact, concentration, criticality, business_kpi_distortion, traffic_preservation)', new)
    # Ensure printed v2 fields exist in output if not already.
    if 'event_criticality_score=' not in txt:
        txt = txt.replace('print(f"criticality_evidence_score={criticality:.6f}")', 'print(f"criticality_evidence_score={criticality:.6f}")\n            print(f"event_criticality_score={fval(row, \'event_criticality_score\'):.6f}")\n            print(f"conversion_criticality_score={fval(row, \'conversion_criticality_score\'):.6f}")\n            print(f"revenue_criticality_score={fval(row, \'revenue_criticality_score\'):.6f}")')
    val_path.write_text(txt)
    print(f'[PATCH] updated validator baseline-zero semantics in {val_path}')
else:
    print(f'[WARN] missing {val_path}')
