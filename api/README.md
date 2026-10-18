# plasma-etch-agents

AI Builder Cup 2026 entry (theme: Manufacturing — Intelligent Operations &
Industrial Efficiency). A deployed multi-agent "research group" built with
Google ADK on Google Cloud that turns **4M experiment metadata** (Machine,
Material, Method, optional Man) into a validated plasma simulation — and,
time allowing, a Bosch etch profile — ending in a **human sign-off**.

**Headline KPI: ~2 hours of expert simulation set-up down to 20 minutes**,
shown live with a timer (form submit → sign-off), against a documented
~560-GUI-step COMSOL baseline.

## The research group

| Role | Job |
|---|---|
| **Professor** | Sets acceptance criteria from a fixed rubric + literature-derived checks; reviews physics (Te range, Bohm flux, power balance, etch-rate magnitude); sends work back; never auto-passes — a human signs off |
| **Postdoc** | Turns 4M metadata into a simulation plan; calibrates against Kimura & Noto (2006) experimental data |
| **PhD** | Executes the 0D global plasma model. `FLOW_INCLUDE_ETCH=true` restores the optional PhD-Etch role for ViennaPS Bosch work |

COMSOL and Sentaurus are licence-locked, so agents call a clean
**solver tool interface** (`simtools`, plain importable Python). The demo
binds it to open-source solvers; the lab later binds the same interface to
COMSOL (Java API) and Sentaurus (command files).

## Stack

Google ADK (Python) on Agent Platform Agent Runtime · Gemini 3.8 Flash (one
config value) · Cloud Run web UI + solver jobs · litrag literature search
with Gemini embeddings · optional Gemma 4 31B LoRA for 4M extraction, served
via vLLM on a scale-to-zero GPU · region asia-southeast1.

## Repo layout

```
agents/     ADK agents, frozen role contracts (agents/contracts), rubrics
simtools/   framework-free solver tools + chemistry/validation data schemas
litrag/     literature search (private corpus/index stay out of the repo)
web/        FastAPI + React UI (W5)
jobs/       Cloud Run Job entrypoints (W5)
infra/      deploy scripts, budgets, IAM (W5)
evals/      ~30 good + 8-10 fault-injected cases, KPI harness (W6)
training/   Gemma LoRA code only — never data or weights
docs/       diagrams
```

## Develop

```bash
uv sync
uv run pytest -q
uv run ruff check .
bash scripts/check_private_files.sh
```

## Research API demo contract

`web.backend.app` exposes `GET /health`, authenticated `GET /presets`,
`POST /runs`, `GET /runs/{id}`, fetch-streamed SSE at
`GET /runs/{id}/events`, authenticated plots, and `POST /runs/{id}/signoff`.
When `AUTH_SECRET` is set, every route except `/health` requires
`Authorization: Bearer <token>`; the token's `sub` is the immutable sign-off
reviewer. Unset `AUTH_SECRET` disables auth locally and logs a warning.

The default demo team is Postdoc + one plasma PhD + Professor. Custom run
inputs enforce power 1–1000 W, pressure 1–500 mTorr, flows 0–1000 sccm,
bias −200–200 V, and at most 12 bias points. The preset allow-list is:
`good_cf4o2_baseline`, `good_argon_baseline`, `fault_te_impossible`,
`fault_power_balance_violation`, and `fault_bohm_flux_inconsistent`.

The container is `Dockerfile` (Python 3.13 slim, frozen `uv` dependencies). It
copies only the runtime packages, config, five public preset cases, and the
litrag package; the private corpus/index and web frontend stay outside the
image. Set `LITRAG_API_URL` and `SERVICE_KEY` to call the already-deployed
rag-api over HTTP instead of loading a private index in-process.


## Licence

GPL-3.0-only (ViennaPS ≥ 4.3 is GPL-3.0 and `simtools` etch code imports it).
