# CASE-OBS-001 Phase3-D3 Decision Support Visualization Refinement Test

## Purpose

Phase3-D2 generated the correct figure pack structure, but three figures still looked like engineer snapshots rather than decision-support evidence:

1. `fig04_journey_impact_view.png` showed stage gap ranking while the title promised journey impact.
2. `appendix02_baseline_current_gap.png` did not make baseline/control references visible enough.
3. `appendix04_risk_score_breakdown.png` showed final scores but not why Likelihood/Impact were produced.

Phase3-D3 refines the visualization layer without changing the authority chain or risk model.

```text
Executive / Analyst = decision support
Engineer Appendix = technical evidence decomposition
```

## Apply patch

```bash
cd /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
unzip -o /mnt/data/case_obs_phase3d3_decision_support_visualization_refinement_patch.zip
chmod +x deploy/run_v05_reliability_pipeline_commerce_mac_host.sh
chmod +x pipelines/commerce/visualization/build_case_obs_001_figures.R
chmod +x pipelines/commerce/validation/validate_case_obs_001_figures.py
```

## Run smoke

```bash
/opt/homebrew/bin/bash deploy/run_v05_reliability_pipeline_commerce_mac_host.sh \
  2026-06-01 source_wc_collection_missing 0
```

## Expected changes

### Figure 4

`analyst/fig04_journey_impact_view.png` should now show a propagation flow:

```text
Web Reality
-> WC Missing
-> Behavior Loss
-> Conversion Distortion
-> Decision Risk
```

It should not be a stage gap ranking chart.

### Appendix 2

`engineer_appendix/appendix02_baseline_current_gap.png` should show:

```text
Current gap
Baseline mean
Control / threshold
```

If OBS statistical baseline rows are unavailable, the semantic threshold is shown explicitly as the control reference.

### Appendix 4

`engineer_appendix/appendix04_risk_score_breakdown.png` should decompose:

```text
Likelihood drivers:
- Statistical evidence
- Baseline delta
- Propagation strength

Impact drivers:
- Customer impact
- Transaction loss
- KPI distortion
- Affected domain ratio

Final risk / confidence:
- Likelihood
- Impact
- Risk
- Root cause confidence
```

## Expected validation

```text
[CASE_OBS_001_FIGURES]
mode=decision_support layer=Phase3-D3 Decision Support Visualization Refinement Layer
[OK] validate_case_obs_001_figures passed
```

The validator now checks these manifest roles:

```text
fig04_journey_impact_view.png = propagation_flow
appendix02_baseline_current_gap.png = baseline_control_comparison
appendix04_risk_score_breakdown.png = risk_decomposition
```

## Completion criteria

- The visualization layer remains non-authoritative report/toolkit evidence.
- Executive figures remain decision-support oriented.
- Figure 4 explains propagation, not stage ranking.
- Appendix 2 makes baseline/control references visible.
- Appendix 4 decomposes risk drivers rather than showing only final scores.
