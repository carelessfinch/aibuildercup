"""Physics and contract tests for the chemistry-driven 0D plasma engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.contracts import OperatingPoint, SolverGeometry
from simtools.chemistry import load_chemistry
from simtools.plasma import run_global_model, run_sweep

DATA = Path(__file__).parent / "data"


@pytest.fixture
def argon():
    return load_chemistry(DATA / "chemistry_ar_lieberman.yaml")


def operating_point(power_w: float = 300.0, sweep: list[float] | None = None) -> OperatingPoint:
    return OperatingPoint(
        power_W=power_w,
        pressure_mTorr=10.0,
        flow_sccm={"Ar": 50.0},
        bias_sweep_V=sweep if sweep is not None else [0.0],
    )


def test_argon_matches_prototype_reference_point(argon) -> None:
    # The prototype's ne=1.6e17 and Gamma=7.7e19 reference values are its
    # 300 W case. The W1 brief labels those values "100 W"; that mismatch is
    # reported and this test follows the physics reference.
    result = run_global_model(argon, operating_point(300.0))
    point = result.points[0]
    assert point.te_eV == pytest.approx(2.5, rel=0.15)
    assert point.ne_m3 == pytest.approx(1.6e17, rel=0.15)
    assert point.ion_flux_m2s == pytest.approx(7.7e19, rel=0.15)
    assert result.diagnostics.power_balance_residual_pct == pytest.approx(0.0, abs=1e-9)


def test_argon_power_scales_density_and_preserves_te(argon) -> None:
    low = run_global_model(argon, operating_point(100.0)).points[0]
    high = run_global_model(argon, operating_point(300.0)).points[0]
    assert low.te_eV == pytest.approx(high.te_eV, rel=0.01)
    assert low.ne_m3 == pytest.approx(high.ne_m3 / 3.0, rel=0.01)
    assert low.ion_flux_m2s == pytest.approx(high.ion_flux_m2s / 3.0, rel=0.01)


def test_power_coupling_eff_scales_density(argon) -> None:
    default = run_global_model(argon, operating_point(300.0)).points[0]
    tuned = run_global_model(
        argon,
        OperatingPoint(
            power_W=300.0,
            pressure_mTorr=10.0,
            flow_sccm={"Ar": 50.0},
            bias_sweep_V=[0.0],
            power_coupling_eff=0.4,
        ),
    ).points[0]
    assert tuned.ne_m3 == pytest.approx(default.ne_m3 * 0.5, rel=1e-9)


def test_plan_geometry_overrides_chemistry_default(argon) -> None:
    default = run_global_model(argon, operating_point(300.0)).points[0]
    bigger = run_global_model(
        argon,
        operating_point(300.0),
        geometry=SolverGeometry(radius_m=0.3, height_m=0.2),
    ).points[0]
    assert bigger.ne_m3 < default.ne_m3  # larger wall area dilutes density
    assert bigger.te_eV > 0


def test_sweep_is_one_solved_sequence(argon) -> None:
    results = run_sweep(argon, operating_point(), sweep=[0, 25, 50, 75, 100])
    points = [result.points[0] for result in results]
    assert [point.bias_V for point in points] == [0, 25, 50, 75, 100]
    assert len({id(point) for point in points}) == 5
    assert all(point.te_eV > 0 for point in points)
    assert all(point.ion_energy_eV >= point.bias_V for point in points)


def test_stub_chemistry_is_refused() -> None:
    chemistry = load_chemistry(DATA / "chemistry_cf4o2_kimura2006.yaml")
    with pytest.raises(ValueError, match="status='stub'"):
        run_global_model(chemistry, operating_point())


def test_empty_sweep_is_rejected(argon) -> None:
    with pytest.raises(ValueError, match="sweep"):
        run_sweep(argon, operating_point(), sweep=[])
