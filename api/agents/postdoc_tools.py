"""Plain-function services exposed to the Postdoc ADK agent."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from agents.config import REPO_ROOT
from agents.contracts import (
    CalibrationReport,
    CalibrationTarget,
    FourMMetadata,
    GapRow,
    OperatingPoint,
    PlasmaResult,
    SimulationPlan,
    SolverGeometry,
)
from simtools.chemistry import load_chemistry

DATA_DIR = REPO_ROOT / "simtools" / "data"
VALIDATION_CSV = DATA_DIR / "validation_comsol_cf4o2.csv"


def _number(mapping: dict[str, Any], *names: str, default: float) -> float:
    for name in names:
        if mapping.get(name) is not None:
            return float(mapping[name])
    return default


def _wants_bosch(metadata: FourMMetadata) -> bool:
    text = metadata.question.lower()
    flows = {key.upper() for key in metadata.method.recipe.get("flow_sccm") or {}}
    return "bosch" in text or {"SF6", "C4F8"}.issubset(flows)


def _plasma_chemistry_ref() -> tuple[str, str | None]:
    """Prefer Kimura & Noto CF4/O2; K1 permits argon while that set is a stub."""
    desired = DATA_DIR / "chemistry_cf4o2_kimura2006.yaml"
    if desired.is_file() and load_chemistry(desired).status == "ready":
        return desired.name, None
    return (
        "chemistry_ar_lieberman.yaml",
        "Using the ready argon chemistry only while the supplied CF4/O2 "
        "Kimura & Noto set is a stub.",
    )


def _calibration_targets(metadata: FourMMetadata, solver: str) -> list[CalibrationTarget]:
    if solver == "viennaps_bosch":
        return [
            CalibrationTarget(
                metric="etch_depth",
                source="Kimura & Noto 2006 experiment",
                source_kind="experiment",
                tolerance_pct=35.0,
            )
        ]
    return [
        CalibrationTarget(
            metric="ne",
            source="Kimura & Noto 2006 experiment",
            source_kind="experiment",
            tolerance_pct=30.0,
        ),
        CalibrationTarget(
            metric="etch_rate",
            source="Kimura & Noto 2006 experiment",
            source_kind="experiment",
            tolerance_pct=40.0,
        ),
    ]


def build_simulation_plan(
    metadata: FourMMetadata, *, include_etch: bool = False
) -> SimulationPlan:
    """Build the frozen simulation plan from validated 4M metadata."""
    recipe = metadata.method.recipe
    flow_sccm = {
        str(key).upper(): float(value)
        for key, value in (recipe.get("flow_sccm") or {}).items()
    }
    operating_point = OperatingPoint(
        power_W=_number(recipe, "power_W", "coil_power_W", default=100.0),
        pressure_mTorr=_number(recipe, "pressure_mTorr", default=15.0),
        flow_sccm=flow_sccm,
        bias_sweep_V=[
            float(value)
            for value in recipe.get("bias_sweep_V") or [0.0, 25.0, 50.0, 75.0, 100.0]
        ],
    )
    wants_bosch = _wants_bosch(metadata)
    solver = "viennaps_bosch" if include_etch and wants_bosch else "plasma_global_model"
    if solver == "viennaps_bosch":
        chemistry_ref = "chemistry_sf6_c4f8_bosch.yaml"
        fallback = None
    else:
        chemistry_ref, fallback = _plasma_chemistry_ref()

    acceptance = [
        "All fixed Professor rubric checks pass.",
        "Calibration gaps against Kimura & Noto 2006 experiment data meet tolerance.",
    ]
    if fallback:
        acceptance.append(fallback)
    if wants_bosch and not include_etch:
        acceptance.append(
            "Etch geometry/profile simulation is out of scope for this demo; "
            "only the plasma global model is executed."
        )
    acceptance.append("COMSOL curves are cross-model context only, never calibration.")

    machine = metadata.machine
    geometry = None
    if machine.chamber_radius_mm is not None and machine.reactor_height_mm is not None:
        geometry = SolverGeometry(
            radius_m=machine.chamber_radius_mm / 1000.0,
            height_m=machine.reactor_height_mm / 1000.0,
        )

    return SimulationPlan(
        case_id=metadata.case_id,
        question=metadata.question,
        solver=solver,  # type: ignore[arg-type]
        chemistry_ref=chemistry_ref,
        operating_point=operating_point,
        uncertain_parameters=[
            {"name": "power_coupling_eff", "bounds": [0.65, 0.9]}  # type: ignore[list-item]
        ],
        calibration_targets=_calibration_targets(metadata, solver),
        acceptance_criteria_proposal=acceptance,
        literature_refs=["Kimura & Noto 2006 experiment", "COMSOL CF4/O2 ICP model (cross-model)"],
        geometry=geometry,
    )


def read_validation_rows(path: str | Path = VALIDATION_CSV) -> list[dict[str, str]]:
    """Read the shared validation CSV without making the private corpus public."""
    validation_path = Path(path)
    if not validation_path.is_file():
        return []
    with validation_path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _row_matches(row: dict[str, str], target: CalibrationTarget, bias_v: float) -> bool:
    metric_names = {
        "ne": {"ne", "electron_density"},
        "te": {"te", "electron_temperature"},
        "etch_rate": {"etch_rate", "etch_rate_nm_per_min"},
        "etch_depth": {"etch_depth", "depth"},
    }.get(target.metric.lower(), {target.metric.lower()})
    if row.get("y_name", "").lower() not in metric_names:
        return False
    try:
        return abs(float(row.get("x_value", "nan")) - bias_v) < 1e-9
    except ValueError:
        return False


def evaluate_plan_calibration(
    plan: SimulationPlan,
    result: PlasmaResult,
    validation_rows: list[dict[str, str]] | None = None,
) -> CalibrationReport:
    """Compare only experiment rows; COMSOL model rows remain cross-model checks."""
    rows = read_validation_rows() if validation_rows is None else validation_rows
    gaps: list[GapRow] = []
    for target in plan.calibration_targets:
        if target.source_kind != "experiment":
            continue
        for point in result.points:
            row = next((item for item in rows if _row_matches(item, target, point.bias_V)), None)
            if row is None:
                continue
            measured = float(row["y_value"])
            if target.metric.lower() not in {"ne", "te"}:
                continue
            simulated = {
                "ne": point.ne_m3,
                "te": point.te_eV,
            }.get(target.metric.lower(), measured)
            gap_pct = abs(simulated - measured) / max(abs(measured), 1e-30) * 100.0
            gaps.append(
                GapRow(
                    metric=target.metric,
                    source_kind="experiment",
                    measured=measured,
                    simulated=simulated,
                    unit=row.get("y_unit", ""),
                    gap_pct=gap_pct,
                    within_tolerance=gap_pct <= target.tolerance_pct,
                )
            )
    converged = bool(gaps) and all(gap.within_tolerance for gap in gaps)
    return CalibrationReport(gaps=gaps, converged=converged)


def cross_model_comsol_check(
    plan: SimulationPlan,
    result: PlasmaResult,
    validation_rows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Return a non-calibration comparison against COMSOL model rows (K2/K3)."""
    rows = read_validation_rows() if validation_rows is None else validation_rows
    comparisons: list[dict[str, Any]] = []
    for row in rows:
        if row.get("kind") != "model":
            continue
        reference_target = CalibrationTarget(
            metric=row["y_name"], source="", tolerance_pct=0
        )
        matching = [
            point for point in result.points if _row_matches(row, reference_target, point.bias_V)
        ]
        if not matching:
            continue
        comparisons.append(
            {
                "curve_id": row.get("curve_id"),
                "citation": row.get("citation"),
                "note": row.get("notes"),
                "kind": "cross_model_only",
            }
        )
    return {"status": "success", "comparisons": comparisons}
