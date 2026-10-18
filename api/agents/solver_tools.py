"""PhD-facing solver tools. Every backend call covers one sweep or plan (H6)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.config import REPO_ROOT, load_config
from agents.contracts import EtchResult, PlasmaResult, SimulationPlan, SolverDiagnostics
from simtools.chemistry import load_chemistry
from simtools.etch import run_bosch
from simtools.plasma import run_sweep
from simtools.runner import get_runner

DATA_DIR = REPO_ROOT / "simtools" / "data"


def _chemistry_path(reference: str) -> Path:
    candidate = Path(reference)
    if not candidate.is_absolute():
        candidate = DATA_DIR / candidate.name
    resolved = candidate.resolve()
    data_root = DATA_DIR.resolve()
    if data_root not in resolved.parents:
        msg = f"chemistry reference must resolve inside {data_root}: {reference}"
        raise ValueError(msg)
    return resolved


def run_plasma_sweep(plan: SimulationPlan) -> PlasmaResult:
    """Run the complete bias sweep through one configured solver-backend job."""
    if plan.solver != "plasma_global_model":
        msg = f"PhD-Plasma cannot execute solver {plan.solver!r}"
        raise ValueError(msg)

    chemistry = load_chemistry(_chemistry_path(plan.chemistry_ref))
    runner = get_runner(load_config().solver.backend)
    run_id = runner.submit(
        lambda: run_sweep(chemistry, plan.operating_point, plan.operating_point.bias_sweep_V)
    )
    results = runner.await_result(run_id)
    if not results:
        msg = "plasma backend returned an empty sweep"
        raise ValueError(msg)
    first = results[0]
    return PlasmaResult(
        points=[item.points[0] for item in results],
        diagnostics=SolverDiagnostics(
            power_balance_residual_pct=first.diagnostics.power_balance_residual_pct,
            runtime_s=first.diagnostics.runtime_s,
            chemistry_id=first.diagnostics.chemistry_id,
            averaging_note=first.diagnostics.averaging_note,
        ),
    )


def _etch_config(plan: SimulationPlan) -> dict[str, Any]:
    return {
        "case_id": plan.case_id,
        "chemistry_ref": plan.chemistry_ref,
        "operating_point": plan.operating_point.model_dump(mode="json"),
        "uncertain_parameters": [
            item.model_dump(mode="json")
            for item in plan.uncertain_parameters
        ],
    }


def run_etch_plan(plan: SimulationPlan) -> EtchResult:
    """Run one Bosch plan through the configured solver-backend job."""
    if plan.solver != "viennaps_bosch":
        msg = f"PhD-Etch cannot execute solver {plan.solver!r}"
        raise ValueError(msg)
    runner = get_runner(load_config().solver.backend)
    config = _etch_config(plan)
    run_id = runner.submit(lambda: run_bosch(config))
    return runner.await_result(run_id)
