"""A demo research-group progression behind the production RunFlow interface.

This file exists only so W5 can demo and test UI plumbing before W3's ADK graph
lands. It uses the frozen role contracts; replacing `build_flow` is the only
change required to attach the real flow.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from agents.contracts import (
    CalibrationReport,
    FinalReport,
    FourMMetadata,
    GapRow,
    PlasmaPoint,
    PlasmaResult,
    ProfessorReview,
    RubricResult,
    SimulationPlan,
    SolverDiagnostics,
)

from .plots import create_demo_plots
from .settings import WebSettings
from .store import EventSink, RunStore


def _rubric(item_id: str, status: str, value: str, expected: str) -> RubricResult:
    return RubricResult(item_id=item_id, status=status, value=value, expected=expected)


def _bohm_check() -> dict[str, str]:
    return {
        "name": "Bohm flux",
        "status": "pass",
        "detail": "Ion flux uses the Bohm edge criterion.",
    }


class MockResearchFlow:
    def __init__(
        self,
        store: RunStore,
        settings: WebSettings,
        fault_spec: dict[str, Any] | None = None,
    ):
        self.store = store
        self.settings = settings
        self.fault_spec = fault_spec

    async def execute(self, metadata: FourMMetadata, sink: EventSink) -> dict[str, Any]:
        plan = self._plan(metadata)
        await sink.emit(
            "plan_created",
            "Postdoc",
            "Simulation plan is ready: one global-model sweep across the requested bias range.",
            {"plan": plan.model_dump(mode="json")},
        )
        await self._pause()

        await sink.emit(
            "solver_started",
            "PhD",
            "Running the whole bias sweep as one solver job.",
            {"granularity": "one job per sweep", "backend": "local"},
        )
        result = self._result(plan)
        if self.fault_spec is not None:
            from .presets import apply_plasma_fault

            result = apply_plasma_fault(result, self.fault_spec)
            await sink.emit(
                "fault_injected_demo",
                "web",
                f"Fault-injected demo: {self.fault_spec.get('description', 'seeded fault')}.",
                {"fault": self.fault_spec},
            )
        await self._pause()
        await sink.emit(
            "result_received",
            "PhD",
            "Plasma sweep complete; the calibration table is being assembled.",
            {"result": result.model_dump(mode="json")},
        )

        for filename, (content_type, content) in create_demo_plots(result.points).items():
            url = await sink.add_plot(filename, content_type, content)
            await sink.emit("plot_ready", "Postdoc", f"Plot prepared: {filename}.", {"url": url})

        review = ProfessorReview(
            verdict="revise",
            round=1,
            rubric_results=[
                _rubric("te_range", "pass", "2.8–3.2 eV", "1–10 eV"),
                RubricResult(item_id="power_balance", status="pass", value="2.4%", expected="< 5%"),
                _rubric("calibration_gap", "fail", "17.8%", "< 15%"),
            ],
            physics_checks=[
                _bohm_check()
            ],
            feedback=(
                [self.fault_spec.get("description", "The seeded fault must be fixed.")]
                if self.fault_spec is not None
                else ["Retune the coupling efficiency toward the upper bound before sign-off."]
            ),
            citations=["Kimura & Noto, J. Appl. Phys. 100, 063303 (2006)"],
        )
        await sink.emit(
            "review_received",
            "Professor",
            "Round 1 needs another calibration pass before it can be trusted.",
            {"review": review.model_dump(mode="json")},
        )
        await self._pause()

        if self.fault_spec is None:
            final_review = review.model_copy(
                update={
                    "verdict": "approve",
                    "round": min(2, self.settings.review_max_rounds),
                    "rubric_results": [
                        _rubric("te_range", "pass", "2.8–3.2 eV", "1–10 eV"),
                        _rubric("power_balance", "pass", "1.6%", "< 5%"),
                        _rubric("calibration_gap", "pass", "6.1%", "< 15%"),
                    ],
                    "feedback": [],
                }
            )
        else:
            final_review = review.model_copy(
                update={
                    "verdict": "escalate",
                    "round": min(2, self.settings.review_max_rounds),
                    "feedback": [
                        self.fault_spec.get("description", "The seeded fault was not resolved.")
                    ],
                }
            )
        calibration = self._calibration()
        await sink.emit(
            "review_received",
            "Professor",
            "Round 2 passes the rubric and physics checks; human sign-off is required.",
            {"review": final_review.model_dump(mode="json")},
        )
        report = FinalReport(
            case_id=plan.case_id,
            summary=(
                "The CF4/O2 ICP sweep is physically consistent and "
                "calibrated within tolerance."
            ),
            figures=[Path(filename) for filename in create_demo_plots(result.points)],
            calibration=calibration,
            reviews=[review, final_review],
            open_issues=[] if self.fault_spec is None else list(final_review.feedback),
            sign_off="pending" if self.fault_spec is None else "escalated",
        )
        await sink.emit(
            "awaiting_signoff" if self.fault_spec is None else "escalated",
            "Professor",
            "The recommendation is approved; a human still owns the final sign-off."
            if self.fault_spec is None
            else "The fault remains unresolved; the result is NOT signed off.",
            {"report": report.model_dump(mode="json")},
        )
        plot_urls = [
            f"/runs/{sink.run_id}/plots/{filename}"
            for filename in sorted(create_demo_plots(result.points))
        ]
        return {"report": report.model_dump(mode="json"), "plots": plot_urls}

    async def _pause(self) -> None:
        await asyncio.sleep(self.settings.run_task_delay_s)

    def _plan(self, metadata: FourMMetadata) -> SimulationPlan:
        recipe = metadata.method.recipe
        return SimulationPlan(
            case_id=metadata.case_id,
            question=metadata.question,
            solver="plasma_global_model",
            chemistry_ref="chemistry_cf4o2_kimura2006.yaml",
            operating_point={
                "power_W": float(recipe.get("power_W", 100)),
                "pressure_mTorr": float(recipe.get("pressure_mTorr", 15)),
                "flow_sccm": {
                    "CF4": float(recipe.get("CF4_sccm", 40)),
                    "O2": float(recipe.get("O2_sccm", 10)),
                },
                "bias_sweep_V": [0, 25, 50, 75, 100],
            },
            uncertain_parameters=[{"name": "power_coupling_eff", "bounds": (0.6, 0.9)}],
            calibration_targets=[
                {
                    "metric": "ne",
                    "source": "Kimura & Noto 2006",
                    "source_kind": "experiment",
                    "tolerance_pct": 15,
                }
            ],
            acceptance_criteria_proposal=[
                "Electron temperature remains in the published range.",
                "Power-balance residual stays below 5%.",
                "Calibrated electron density agrees with experiment within 15%.",
            ],
            literature_refs=["Kimura & Noto, J. Appl. Phys. 100, 063303 (2006)"],
        )

    def _result(self, plan: SimulationPlan) -> PlasmaResult:
        biases = plan.operating_point.bias_sweep_V
        points = [
            PlasmaPoint(
                bias_V=bias,
                te_eV=2.8 + 0.4 * index / max(1, len(biases) - 1),
                ne_m3=1.42e17 + 8.2e15 * index,
                ion_flux_m2s=6.4e19 + 1.3e18 * index,
                ion_energy_eV=5 + bias * 0.9,
                species_m3={"CF3+": 9.8e16, "O+": 2.4e16, "F": 3.2e20},
                etchant_fluxes_m2s={"F": 2.8e20, "O": 7.4e19},
            )
            for index, bias in enumerate(biases)
        ]
        return PlasmaResult(
            points=points,
            diagnostics=SolverDiagnostics(
                power_balance_residual_pct=1.6,
                runtime_s=0.38,
                chemistry_id="cf4o2_kimura2006-demo",
                averaging_note="Mock sweep; 0D wafer-averaged values.",
            ),
        )

    def _calibration(self) -> CalibrationReport:
        return CalibrationReport(
            gaps=[
                GapRow(
                    metric="ne",
                    source_kind="experiment",
                    measured=1.5e17,
                    simulated=1.59e17,
                    unit="m^-3",
                    gap_pct=6.1,
                    within_tolerance=True,
                )
            ],
            tuned_parameters={"power_coupling_eff": 0.84},
            converged=True,
        )


def build_flow(
    store: RunStore, settings: WebSettings, fault_spec: dict[str, Any] | None = None
):
    if settings.flow_backend == "adk":
        from .adk_flow import AdkResearchFlow

        return AdkResearchFlow(store, settings, fault_spec=fault_spec)
    if settings.flow_backend != "mock":
        raise ValueError(f"unknown flow backend: {settings.flow_backend!r}")
    return MockResearchFlow(store, settings, fault_spec=fault_spec)
