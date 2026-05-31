# weblog_sim configs

| File | Role |
|---|---|
| scenario_baseline.yaml | Baseline generation behavior and page/event distribution |
| exogenous_static.yaml | Static fallback exogenous config |
| exogenous_timeline_db.yaml | v0.4 DB timeline provider config |
| format_meta_default.yaml | Output format metadata |

`run_source_generation_v2.py` may create temporary generated profile yaml files under the output directory `.v04_profiles/` so that the simulator CLI can run with DB timeline settings without mutating checked-in profile configs.
