"""Rubric evaluation tests (D5 fixed checks; specials wire up in W1)."""

from pathlib import Path

from agents.contracts import PlasmaPoint, PlasmaResult, SolverDiagnostics
from simtools.validation import check_physics, load_rubric

RUBRIC = Path(__file__).parent.parent / "agents" / "rubrics" / "plasma.yaml"


def make(
    te: float,
    residual: float = 3.0,
    ne: float = 1.6e17,
    ion_flux: float = 7.7e19,
    species: dict[str, float] | None = None,
) -> PlasmaResult:
    return PlasmaResult(
        points=[
            PlasmaPoint(
                bias_V=0,
                te_eV=te,
                ne_m3=ne,
                ion_flux_m2s=ion_flux,
                ion_energy_eV=5.0,
                species_m3=species or {},
            )
        ],
        diagnostics=SolverDiagnostics(
            power_balance_residual_pct=residual,
            runtime_s=0.1,
            chemistry_id="ar_lieberman_icp",
        ),
    )


def test_rubric_loads() -> None:
    rubric = load_rubric(RUBRIC)
    ids = [c["id"] for c in rubric["fixed_checks"]]
    assert {"te_range", "ne_range", "power_balance_residual"} <= set(ids)


def test_good_result_passes_point_checks() -> None:
    results = {r.item_id: r for r in check_physics(make(2.5), load_rubric(RUBRIC))}
    assert results["te_range"].status == "pass"
    assert results["ne_range"].status == "pass"
    assert results["power_balance_residual"].status == "pass"


def test_impossible_te_fails() -> None:
    results = {r.item_id: r for r in check_physics(make(250.0), load_rubric(RUBRIC))}
    assert results["te_range"].status == "fail"


def test_power_balance_violation_fails() -> None:
    results = {r.item_id: r for r in check_physics(make(2.5, residual=55.0), load_rubric(RUBRIC))}
    assert results["power_balance_residual"].status == "fail"


def test_bohm_flux_consistency_passes_and_fails() -> None:
    rubric = load_rubric(RUBRIC)
    bohm_flux = 0.61 * 1.0e17 * 2.0e3  # c_s = 2,000 m/s for this constructed point
    passing = {
        r.item_id: r
        for r in check_physics(
            make(2.0, ne=1.0e17, ion_flux=bohm_flux, species={"Ar+": 1.0e17}), rubric
        )
    }
    failing = {
        r.item_id: r
        for r in check_physics(
            make(
                2.0,
                ne=1.0e17,
                ion_flux=2.0 * bohm_flux,
                species={"Ar+": 1.0e17},
            ),
            rubric,
        )
    }
    assert passing["bohm_flux_consistency"].status == "pass"
    assert failing["bohm_flux_consistency"].status == "fail"


def test_species_densities_positive_passes_and_fails() -> None:
    rubric = load_rubric(RUBRIC)
    passing = {
        r.item_id: r
        for r in check_physics(
            make(2.5, species={"e": 1.0e17, "Ar+": 1.0e17}), rubric
        )
    }
    failing = {
        r.item_id: r
        for r in check_physics(
            make(2.5, species={"e": 1.0e17, "Ar+": -1.0}), rubric
        )
    }
    assert passing["species_densities_positive"].status == "pass"
    assert failing["species_densities_positive"].status == "fail"


def test_no_species_densities_does_not_vacuously_pass() -> None:
    results = {r.item_id: r for r in check_physics(make(2.5), load_rubric(RUBRIC))}
    assert results["species_densities_positive"].status == "fail"


def test_optional_etch_rate_warns_absent_then_checks_bounds() -> None:
    rubric = load_rubric(RUBRIC)
    without = {r.item_id: r for r in check_physics(make(2.5), rubric)}
    assert without["etch_rate_magnitude"].status == "warn"
    assert without["etch_rate_magnitude"].value == "absent"

    result = make(2.5)
    result.points[0] = result.points[0].model_copy(update={"etch_rate_nm_per_min": 250.0})
    inside = {r.item_id: r for r in check_physics(result, rubric)}
    assert inside["etch_rate_magnitude"].status == "pass"

    bad = make(2.5)
    bad.points[0] = bad.points[0].model_copy(update={"etch_rate_nm_per_min": 5.0})
    outside = {r.item_id: r for r in check_physics(bad, rubric)}
    assert outside["etch_rate_magnitude"].status == "fail"
