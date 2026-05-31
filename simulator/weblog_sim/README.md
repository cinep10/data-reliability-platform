# weblog_sim v0.4

`weblog_sim` is the v0.4 source-level reliability simulator.

Responsibilities:

```text
1. Generate deterministic Apache-like source access logs.
2. Read materialized exogenous state from DB through TimelineDbProviderV2.
3. Apply source anomaly mutation inside generator core.
4. Emit v0.4 Source Anomaly Contract directly in the cookie field.
5. Never rely on post-generation source cookie rewrite in the normal run path.
```

Main entrypoint:

```bash
python -m simulator.weblog_sim.cli \
  --profile <profile yaml> \
  --start <YYYY-MM-DDTHH:MM:SS> \
  --end <YYYY-MM-DDTHH:MM:SS> \
  --avg-rps 1 \
  --seed 42 \
  --out <source log file>
```

In production pipeline, use `pipelines.source.run_source_generation_v2` instead of calling this directly.
