# ADK agent layer

This package implements the Professor / Postdoc / PhD-Plasma / PhD-Etch layer on
Google ADK **2.11.0**. The role I/O types in `agents/contracts/models.py` are
frozen; all agents use those exact Pydantic models as `LlmAgent.output_schema`.

## What is wired

- `flow.py::build_graph_flow` uses the installed ADK `Workflow` graph API and a
  custom `Node` for the bounded revision cycle. Its static graph is:
  `START -> capture_input -> postdoc -> review_loop`. The review loop invokes the
  role agents through the public `Context.run_node` API and enforces
  `review.max_rounds`. At the cap it writes `ESCALATED — NOT SIGNED OFF` and
  returns `FinalReport(sign_off="escalated")`; it never auto-passes.
- `flow.py::build_coordinator_flow` is the minimal `FLOW_MODE=coordinator`
  alternative and contains the same four role agents/contracts.
- The Professor's evidence tool runs `simtools.validation.check_physics` against
  `agents/rubrics/plasma.yaml` and derives 2–4 literature-based checks.
- The three litrag wrappers are failure-isolated. With no private index, they
  return `status: "unavailable"`; they do not crash agent construction.
- PhD-Plasma calls `simtools.plasma.run_sweep` through `simtools.runner` once per
  sweep. PhD-Etch has the corresponding plan-level seam for W2.
- Postdoc calibration targets are explicitly `source_kind="experiment"` from
  Kimura & Noto (2006). COMSOL is available only through the cross-model check.

## Offline checks

From the repository root:

```bash
uv run pytest -q agents
uv run ruff check agents
```

No test calls Gemini. They construct agents, inspect ADK's compiled graph,
exercise the local solver backend, and verify escalation/fallback behavior.

## Local `adk web` run

1. Install the project: `uv sync`.
2. Provide Google Cloud values in your shell or a local untracked `.env`:

   ```bash
   export GOOGLE_GENAI_USE_VERTEXAI=TRUE
   export GOOGLE_CLOUD_PROJECT=<project-a-id>
   export GOOGLE_CLOUD_LOCATION=global
   export AGENT_MODEL=gemini-3.8-flash
   export FLOW_MODE=graph
   export REVIEW_MAX_ROUNDS=3
   export LITRAG_INDEX_DIR=/absolute/private/index/dir   # optional
   ```

3. Start ADK Dev UI:

   ```bash
   uv run adk web agents/adk_app
   ```

4. Open the displayed URL, select `plasma_research_group`, and paste one JSON
   object matching `FourMMetadata`. Example:

   ```json
   {
     "case_id": "plasma_demo",
     "question": "Validate ne and ion flux versus substrate bias.",
     "machine": {},
     "material": {"wafer": "Si"},
     "method": {
       "recipe": {
         "power_W": 300,
         "pressure_mTorr": 10,
         "flow_sccm": {"Ar": 50},
         "bias_sweep_V": [0, 25, 50, 75, 100]
       }
     },
     "source": "form"
   }
   ```

The UI will call Gemini and the local simtools backend. It is not an offline
test; do not run it without the intended paid Vertex AI project.

## API notes

`SequentialAgent` and `LoopAgent` are deprecated in ADK 2.11.0 source. This
layer therefore uses `Workflow`, `START`, `FunctionNode`, `Node`, and
`Context.run_node`. `LlmAgent.output_schema` supports Pydantic models and may be
combined with tools; ADK enforces the structure on the final response.
