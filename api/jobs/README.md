# jobs — Cloud Run Job entrypoints (W5)

One job per sweep or plan, never per point (decision H6).

## Local smoke

```bash
uv run python -m jobs.run_plan --spec <path/to/plan.json> --output /tmp/result.json
```

The entrypoint reads either a `SimulationPlan` or `{"plan": ...}`, emits
structured NDJSON progress to stdout, and writes its final state atomically.
Cloud Run uses `RUN_SPEC_PATH`/`RUN_OUTPUT_PATH`; M2 wires
`simtools.runner`'s `cloud_run_job` backend to submit this command.
