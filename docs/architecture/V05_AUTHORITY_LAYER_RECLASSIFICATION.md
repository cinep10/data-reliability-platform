# v0.5 Architecture Reclassification

## Purpose

This document fixes the responsibility boundary before the next risk-modeling refactor.
The goal is to prevent Observability, Baseline Science, Risk, Semantic, and Action from being mixed.

## Final Layer Contract

```text
OBS
↓
Reference Evidence

Baseline Science
↓
Authority Reference Layer

Reliability Analysis
↓
Authority Analytics Layer

Unified Risk
↓
Authority Risk Layer

Semantic / Action
↓
Knowledge Base
```

## Layer Definitions

### OBS = Reference Evidence

OBS represents the developer/operations observability view. It answers:

```text
What was observed as broken?
```

Examples:

```text
WebServer ↔ WC gap
app_version gap
sdk_version gap
URL/client gap
root-cause candidate confidence
```

OBS must not decide final operational or marketing risk directly. It may support detection confidence, KPI distortion evidence, or root-cause narrative.

### Baseline Science = Authority Reference Layer

Baseline Science is not an OBS feature.

It replaces the real-world business/marketing historical experience missing from the portfolio dataset. It answers:

```text
Is this different from the expected normal state?
```

Examples:

```text
baseline mean
baseline sd
z-score
historical percentile
control limit
expected metric
threshold calibration
```

### Reliability Analysis = Authority Analytics Layer

Reliability Analysis is the authoritative analytics interface. It consumes measurement, baseline science, runtime evidence, and cross-domain propagation evidence.

It answers:

```text
What reliability failure evidence exists?
```

### Unified Risk = Authority Risk Layer

Unified Risk is the final risk authority. The next modeling direction is:

```text
Risk = Likelihood × Impact
```

Confidence is separated from risk. A case can have high risk and medium root-cause confidence.

### Semantic / Action = Knowledge Base

Semantic and Action are not generic risk engines.

They are knowledge-base layers:

```text
Risk → Classification → Narrative → Action Catalog
```

Semantic classifies and narrates. Action maps classification, risk level, affected domains, and root-cause context to module-specific action catalog entries.

## Implementation Guard

Run:

```bash
python -m pipelines.commerce.validation.validate_v05_architecture_reclassification \
  --project-root /Volumes/EXTERNAL_USB/dev/repo/data-reliability-platform
```

The validation checks comments, contract, and operation shell labels so the implementation stays aligned with this architecture.
