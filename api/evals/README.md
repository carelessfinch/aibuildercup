# evals

## Case format

Cases live in `cases/*.json`. Every case validates against `FourMMetadata`
(via `simtools.fourm.parse_form`) unless a fault intentionally makes it invalid.
Fault injections are explicit dotted-path mutations applied to a clean public
synthetic baseline:

```json
{
  "case_id": "fault_bias_mv_as_v",
  "kind": "good | fault",
  "fault": {
    "site": "fourm_input | plan | plasma_result | chemistry",
    "description": "...",
    "coverage": ["wrong_unit"],
    "inject": {"path": "method.recipe.bias_sweep_V", "op": "set", "value": [0, 25000]}
  },
  "fourm_input": {"...": "FourMMetadata fields"},
  "plasma_result": {"...": "clean PlasmaResult baseline, when reviewed as physics"},
  "plan": {"...": "optional SimulationPlan baseline"},
  "chemistry": {"...": "optional simtools.chemistry/1 baseline"},
  "expect": {
    "verdict_in": ["revise", "escalate"],
    "must_catch": ["bias out of plausible range"],
    "must_not_signoff": true,
    "must_signoff_possible": false
  }
}
```

Injection operations are `set`, `add`, and `remove`. Dotted path components
that are integers address list entries (for example `points.0.te_eV`).

The harness review seam is intentionally small:

```python
ReviewFn = Callable[[ReviewRequest], ProfessorReview]
```

`ReviewRequest` carries parsed frozen contracts plus raw payload/parse errors
and optional plan/chemistry context. That extra context is needed by
chemistry and plan-site faults; a bare `(FourMMetadata, PlasmaResult, rubric)`
signature cannot express those cases. The W3 Professor adapter should convert
`ReviewRequest` into its own tool call in M2.

## KPIs (E4)

- **Catch rate** = faults where the Professor's verdict ∈ `expect.verdict_in`
  AND every `must_catch` item appears in its feedback/checks / **total faults**.
  Target ≥ 8/10 with **zero silent sign-offs** on faulted cases.
- **End-to-end time** = form submit → human sign-off, from the event log.
- **Expert minutes** = summed human-active intervals (form fill, reading,
  sign-off, escalations) from the same log.

Event names are `form_submit`, `sign_off`, `human_active_start`, and
`human_active_end`; timestamps are epoch seconds or ISO-8601. Unpaired active
intervals are ignored. KPI aggregation is a stub until W5 emits logs.

## Offline run

```bash
uv run python -m evals.harness
uv run pytest evals -q
```

The command exits non-zero when a good case fails, a fault silently signs off,
or catch rate is below the 8/10 target. It currently wraps
`simtools.validation.check_physics` plus deterministic metadata/chemistry
checks so it runs offline; the Professor agent replaces the review function in
M2.

## Status (M0)

Fault-injection suite seeded: 3 good cases and 13 fault cases with explicit
coverage. The full ~30-case suite and deployed-agent timing arrive in M2/M3.
