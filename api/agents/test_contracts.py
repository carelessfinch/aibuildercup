"""Contract smoke tests: the M0 interface freeze is load-bearing."""

import json

import pytest
from pydantic import ValidationError

from agents.contracts import (
    CONTRACTS_VERSION,
    CalibrationReport,
    FinalReport,
    FourMMetadata,
    GapRow,
    OperatingPoint,
    PlasmaPoint,
    PlasmaResult,
    ProfessorReview,
    RubricResult,
    SimulationPlan,
    SolverDiagnostics,
)


def test_contracts_version_frozen_at_v1() -> None:
    assert CONTRACTS_VERSION == "1.2.0"


def test_simulation_plan_roundtrip() -> None:
    plan = SimulationPlan.model_validate(
        {
            "case_id": "plasma_cf4o2_icp_v1",
            "question": "Validate ne and etch rate vs bias.",
            "solver": "plasma_global_model",
            "chemistry_ref": "chemistry_cf4o2_kimura2006.yaml",
            "operating_point": {
                "power_W": 100,
                "pressure_mTorr": 15,
                "flow_sccm": {"CF4": 40, "O2": 10},
                "bias_sweep_V": [0, 25, 50, 75, 100],
            },
            "uncertain_parameters": [{"name": "power_coupling_eff", "bounds": [0.6, 0.9]}],
            "calibration_targets": [
                {
                    "metric": "ne",
                    "source": "kimura_noto_2006_fig5",
                    "source_kind": "experiment",
                    "tolerance_pct": 20,
                }
            ],
        }
    )
    again = SimulationPlan.model_validate(json.loads(plan.model_dump_json()))
    assert again == plan
    assert again.calibration_targets[0].source_kind == "experiment"


def test_fourm_metadata_requires_the_four_ms() -> None:
    ok = FourMMetadata.model_validate(
        {
            "case_id": "c1",
            "question": "q",
            "machine": {"diagnostics": ["langmuir_probe"]},
            "material": {"wafer": "Si"},
            "method": {"recipe": {"power_W": 100}},
            "source": "form",
        }
    )
    assert ok.man is None  # Man is optional (I3)


def test_power_coupling_eff_is_optional_and_bounded() -> None:
    base = {
        "power_W": 100,
        "pressure_mTorr": 15,
        "flow_sccm": {"CF4": 40, "O2": 10},
    }
    assert OperatingPoint.model_validate(base).power_coupling_eff is None
    point = OperatingPoint.model_validate({**base, "power_coupling_eff": 0.75})
    assert point.power_coupling_eff == 0.75
    with pytest.raises(ValidationError):
        OperatingPoint.model_validate({**base, "power_coupling_eff": 1.5})


def test_v1_2_optional_etch_rate_and_geometry() -> None:
    point = PlasmaPoint(
        bias_V=0, te_eV=2.5, ne_m3=1.6e17, ion_flux_m2s=7.7e19, ion_energy_eV=5.0
    )
    assert point.etch_rate_nm_per_min is None
    updated = point.model_copy(update={"etch_rate_nm_per_min": 220.0})
    assert updated.etch_rate_nm_per_min == 220.0

    plan = SimulationPlan.model_validate(
        {
            "case_id": "c1",
            "question": "q",
            "solver": "plasma_global_model",
            "chemistry_ref": "x.yaml",
            "operating_point": {"power_W": 100, "pressure_mTorr": 15},
            "geometry": {"radius_m": 0.4, "height_m": 0.7, "gas_temperature_K": 350.0},
        }
    )
    assert plan.geometry is not None
    assert plan.geometry.radius_m == 0.4
    again = SimulationPlan.model_validate(json.loads(plan.model_dump_json()))
    assert again.geometry == plan.geometry


def test_plasma_result_and_professor_review_shapes() -> None:
    result = PlasmaResult(
        points=[
            PlasmaPoint(
                bias_V=0,
                te_eV=2.5,
                ne_m3=1.6e17,
                ion_flux_m2s=7.7e19,
                ion_energy_eV=5.0,
            )
        ],
        diagnostics=SolverDiagnostics(
            power_balance_residual_pct=3.2,
            runtime_s=0.8,
            chemistry_id="ar_lieberman_icp",
        ),
    )
    review = ProfessorReview(
        verdict="revise",
        round=1,
        rubric_results=[
            RubricResult(item_id="te_range", status="pass", value="2.5", expected="1..10 eV")
        ],
        feedback=["Recompute Bohm flux with the updated sheath model."],
    )
    calibration = CalibrationReport(
        gaps=[
            GapRow(
                metric="ne",
                source_kind="experiment",
                measured=1.5e17,
                simulated=1.6e17,
                unit="m^-3",
                gap_pct=6.7,
                within_tolerance=True,
            )
        ],
        converged=False,
    )
    report = FinalReport(
        case_id="c1",
        summary="s",
        calibration=calibration,
        reviews=[review],
        sign_off="pending",
    )
    assert report.sign_off == "pending"
    assert result.diagnostics.chemistry_id == "ar_lieberman_icp"
