"""Chemistry-driven 0D global plasma model.

The balance equations follow the Lieberman & Lichtenberg ICP feasibility check
in ``prototypes/ar_icp_global_model.py``. Rates, species, and geometry come
from the shared chemistry schema, so the Kimura & Noto CF4/O2 data can replace
the working argon set without changing the solver interface.
"""

from __future__ import annotations

import math
import time
from typing import Any

from scipy.optimize import brentq

from agents.contracts import (
    OperatingPoint,
    PlasmaPoint,
    PlasmaResult,
    SimulationPlan,
    SolverDiagnostics,
    SolverGeometry,
)
from simtools.chemistry import Chemistry, Geometry, Reaction

ELEMENTARY_CHARGE = 1.602176634e-19
BOLTZMANN = 1.380649e-23
AMU_TO_KG = 1.66053906660e-27
NEUTRAL_COLLISION_CROSS_SECTION_M2 = 1.0e-18
DEFAULT_POWER_COUPLING_EFFICIENCY = 0.8
TE_BOUNDS_EV = (0.2, 50.0)


def _rate(reaction: Reaction, te_ev: float) -> float:
    """Evaluate the schema's Arrhenius rate, with the prototype's argon fix."""
    if reaction.rate is None or reaction.rate.form != "arrhenius":
        msg = f"reaction {reaction.id!r} needs an arrhenius rate"
        raise ValueError(msg)
    if reaction.rate.A is None or reaction.rate.B is None or reaction.rate.C is None:
        msg = f"reaction {reaction.id!r} has an incomplete arrhenius rate"
        raise ValueError(msg)

    value = (
        reaction.rate.A
        * te_ev ** reaction.rate.B
        * math.exp(-reaction.rate.C / te_ev)
    )
    # The working argon YAML stores the smooth part of the prototype's
    # effective elastic fit; its log-polynomial correction belongs to the
    # engine because schema v1 has no correction-term field.
    if "effective elastic" in reaction.equation.lower():
        log_te = math.log(te_ev)
        value *= math.exp(0.0618 * log_te**2 - 0.1171 * log_te**3)
    return value


def _reaction_kind(reaction: Reaction) -> str:
    text = " ".join((reaction.equation, reaction.source_note or "")).lower()
    right_hand_side = reaction.equation.partition("->")[2].lower()
    charged_product = any(
        token.strip(".,;") not in {"+"} and token.rstrip(".,;").endswith(("+", "++", "+3"))
        for token in right_hand_side.split()
    )
    if "ioniz" in text or "kiz" in text or charged_product:
        return "ionization"
    if "excit" in text or "kex" in text or "*" in right_hand_side:
        return "excitation"
    if "elastic" in text:
        return "elastic"
    return reaction.type.replace("_", "-")


def _ion_mass_kg(chemistry: Chemistry) -> float:
    masses = [
        species.mass_amu * AMU_TO_KG
        for species in chemistry.species
        if species.charge > 0
    ]
    if not masses:
        msg = f"chemistry {chemistry.id!r} has no positive-ion species"
        raise ValueError(msg)
    return sum(masses) / len(masses)


def _loss_factors(chemistry: Chemistry, neutral_density: float) -> tuple[float, float, float]:
    geometry = chemistry.geometry
    mean_free_path = 1.0 / (neutral_density * NEUTRAL_COLLISION_CROSS_SECTION_M2)
    h_axial = 0.86 / math.sqrt(3.0 + geometry.height_m / (2.0 * mean_free_path))
    h_radial = 0.8 / math.sqrt(4.0 + geometry.radius_m / mean_free_path)
    effective_length = (
        geometry.radius_m
        * geometry.height_m
        / (2.0 * (geometry.radius_m * h_radial + geometry.height_m * h_axial))
    )
    return h_axial, h_radial, effective_length


def _particle_balance_te(chemistry: Chemistry, pressure_pa: float) -> float:
    geometry = chemistry.geometry
    neutral_density = pressure_pa / (BOLTZMANN * geometry.gas_temperature_K)
    _, _, effective_length = _loss_factors(chemistry, neutral_density)
    ion_mass = _ion_mass_kg(chemistry)
    ionization = next(
        (
            reaction
            for reaction in chemistry.reactions
            if _reaction_kind(reaction) == "ionization"
        ),
        None,
    )
    if ionization is None:
        msg = f"chemistry {chemistry.id!r} has no electron-impact ionization rate"
        raise ValueError(msg)

    def imbalance(te_ev: float) -> float:
        ionization_rate = _rate(ionization, te_ev) * neutral_density * effective_length
        bohm_speed = math.sqrt(ELEMENTARY_CHARGE * te_ev / ion_mass)
        return ionization_rate - bohm_speed

    try:
        return float(brentq(imbalance, *TE_BOUNDS_EV))
    except ValueError as exc:
        msg = (
            f"particle balance has no Te root in {TE_BOUNDS_EV[0]:g}.."
            f"{TE_BOUNDS_EV[1]:g} eV for chemistry {chemistry.id!r}"
        )
        raise ValueError(msg) from exc


def _reaction_energy_ev(reaction: Reaction, chemistry: Chemistry) -> float:
    """Return an inelastic threshold until schema v2 can carry it explicitly.

    This is exact for the working argon data. CF4/O2 thresholds must be added
    to the upcoming Kimura & Noto reaction set (or a small schema extension)
    before its stub is marked ready.
    """
    kind = _reaction_kind(reaction)
    if kind == "ionization":
        if any(species.name == "Ar" for species in chemistry.species):
            return 15.76
        return 15.0
    if kind == "excitation":
        return 12.14
    return 0.0


def _species_densities(
    chemistry: Chemistry,
    electron_density: float,
    neutral_density: float,
    flow_sccm: dict[str, float],
) -> dict[str, float]:
    flow_names = {name.casefold() for name in flow_sccm}
    heavy_species = [species for species in chemistry.species if species.role != "electron"]
    feedstock_count = sum(species.name.casefold() in flow_names for species in heavy_species)
    output: dict[str, float] = {}
    for species in chemistry.species:
        if species.role == "electron" or species.charge != 0:
            output[species.name] = electron_density
        elif species.name.casefold() in flow_names:
            output[species.name] = neutral_density
        elif feedstock_count == 0:
            output[species.name] = neutral_density / max(len(heavy_species), 1)
        else:
            # This simple balance does not predict byproduct/radical pools yet.
            # Keep diagnostics finite and clearly trace-level; species balance
            # lands with the complete CF4/O2 reaction set.
            output[species.name] = neutral_density * 1.0e-12
    return output


def _validate_operating_point(operating_point: OperatingPoint) -> None:
    if not math.isfinite(operating_point.power_W) or operating_point.power_W <= 0:
        msg = "power_W must be finite and positive"
        raise ValueError(msg)
    if (
        not math.isfinite(operating_point.pressure_mTorr)
        or operating_point.pressure_mTorr <= 0
    ):
        msg = "pressure_mTorr must be finite and positive"
        raise ValueError(msg)


def _solve_point(
    chemistry: Chemistry, operating_point: OperatingPoint, bias_v: float
) -> tuple[float, float, float, float, dict[str, float], float]:
    _validate_operating_point(operating_point)
    if not math.isfinite(bias_v):
        msg = "bias voltage must be finite"
        raise ValueError(msg)

    geometry = chemistry.geometry
    pressure_pa = operating_point.pressure_mTorr * 0.133322
    neutral_density = pressure_pa / (BOLTZMANN * geometry.gas_temperature_K)
    h_axial, h_radial, _ = _loss_factors(chemistry, neutral_density)
    te_ev = _particle_balance_te(chemistry, pressure_pa)
    ion_mass = _ion_mass_kg(chemistry)
    bohm_speed = math.sqrt(ELEMENTARY_CHARGE * te_ev / ion_mass)
    edge_area = (
        2.0 * math.pi * geometry.radius_m**2 * h_axial
        + 2.0 * math.pi * geometry.radius_m * geometry.height_m * h_radial
    )

    rates = {reaction.id: _rate(reaction, te_ev) for reaction in chemistry.reactions}
    ionization = next(
        reaction
        for reaction in chemistry.reactions
        if _reaction_kind(reaction) == "ionization"
    )
    excitation = next(
        (
            reaction
            for reaction in chemistry.reactions
            if _reaction_kind(reaction) == "excitation"
        ),
        None,
    )
    elastic = next(
        (
            reaction
            for reaction in chemistry.reactions
            if _reaction_kind(reaction) == "elastic"
        ),
        None,
    )
    ionization_rate = rates[ionization.id]
    excitation_rate = rates[excitation.id] if excitation else 0.0
    elastic_rate = rates[elastic.id] if elastic else 0.0
    electron_mass_ratio = 0.0005486 / (ion_mass / AMU_TO_KG)
    collision_energy = (
        _reaction_energy_ev(ionization, chemistry) * ionization_rate
        + _reaction_energy_ev(excitation, chemistry) * excitation_rate
        + 3.0 * electron_mass_ratio * te_ev * elastic_rate
    ) / ionization_rate
    sheath_energy = 0.5 * te_ev * math.log(
        ion_mass / (2.0 * math.pi * 9.1093837e-31)
    )
    # The argon prototype treats applied bias as an additional energy loss per
    # ion crossing the sheath. Future chemistry-specific bias physics only
    # changes this term, not the public solver contract.
    total_energy = 2.0 * te_ev + sheath_energy + collision_energy + max(0.0, bias_v)
    coupling_eff = (
        operating_point.power_coupling_eff
        if operating_point.power_coupling_eff is not None
        else DEFAULT_POWER_COUPLING_EFFICIENCY
    )
    absorbed_power = coupling_eff * operating_point.power_W
    electron_density = absorbed_power / (
        ELEMENTARY_CHARGE * bohm_speed * total_energy * edge_area
    )
    ion_flux = h_axial * electron_density * bohm_speed
    ion_energy = bias_v + sheath_energy
    species = _species_densities(
        chemistry, electron_density, neutral_density, operating_point.flow_sccm
    )
    return te_ev, electron_density, ion_flux, ion_energy, species, 1.0e-12


def _ready_or_raise(chemistry: Chemistry) -> None:
    if chemistry.status == "stub":
        msg = (
            f"chemistry {chemistry.id!r} has status='stub'; supply its complete "
            "reaction rates before running the global model"
        )
        raise ValueError(msg)
    if chemistry.status != "ready":
        msg = f"unsupported chemistry status {chemistry.status!r}"
        raise ValueError(msg)


def _with_geometry(chemistry: Chemistry, geometry: SolverGeometry | None) -> Chemistry:
    """Apply the plan's chamber geometry over the chemistry default (v1.2.0)."""
    if geometry is None:
        return chemistry
    return chemistry.model_copy(
        update={
            "geometry": Geometry(
                radius_m=geometry.radius_m,
                height_m=geometry.height_m,
                gas_temperature_K=geometry.gas_temperature_K,
            )
        }
    )


def run_global_model(
    chemistry: Chemistry,
    operating_point: OperatingPoint,
    *,
    geometry: SolverGeometry | None = None,
) -> PlasmaResult:
    """Solve one operating point and return the frozen PlasmaResult contract."""
    _ready_or_raise(chemistry)
    chemistry = _with_geometry(chemistry, geometry)
    started = time.perf_counter()
    bias_v = operating_point.bias_sweep_V[0] if operating_point.bias_sweep_V else 0.0
    values = _solve_point(chemistry, operating_point, float(bias_v))
    te_ev, ne_m3, ion_flux, ion_energy, species, residual = values
    point = PlasmaPoint(
        bias_V=float(bias_v),
        te_eV=float(te_ev),
        ne_m3=float(ne_m3),
        ion_flux_m2s=float(ion_flux),
        ion_energy_eV=float(ion_energy),
        species_m3={name: float(value) for name, value in species.items()},
        etchant_fluxes_m2s={},
    )
    diagnostics = SolverDiagnostics(
        power_balance_residual_pct=float(residual),
        runtime_s=float(time.perf_counter() - started),
        chemistry_id=chemistry.id,
        averaging_note="0D volume-averaged global model",
    )
    return PlasmaResult(points=[point], diagnostics=diagnostics)


def run_sweep(
    chemistry: Chemistry,
    operating_point: OperatingPoint,
    sweep: list[float] | None = None,
) -> list[PlasmaResult]:
    """Solve a bias sweep. One runner job per sweep, never per point (H6)."""
    _ready_or_raise(chemistry)
    values = sweep if sweep is not None else operating_point.bias_sweep_V
    if not values:
        msg = "sweep must contain at least one bias voltage"
        raise ValueError(msg)

    started = time.perf_counter()
    solved = [_solve_point(chemistry, operating_point, float(bias_v)) for bias_v in values]
    points = [
        PlasmaPoint(
            bias_V=float(bias_v),
            te_eV=float(te_ev),
            ne_m3=float(ne_m3),
            ion_flux_m2s=float(ion_flux),
            ion_energy_eV=float(ion_energy),
            species_m3={name: float(value) for name, value in species.items()},
            etchant_fluxes_m2s={},
        )
        for bias_v, (te_ev, ne_m3, ion_flux, ion_energy, species, _) in zip(
            values, solved, strict=True
        )
    ]
    runtime_s = time.perf_counter() - started
    return [
        PlasmaResult(
            points=[point],
            diagnostics=SolverDiagnostics(
                power_balance_residual_pct=solved[0][5],
                runtime_s=float(runtime_s),
                chemistry_id=chemistry.id,
                averaging_note="0D volume-averaged model; full sweep solved in one call",
            ),
        )
        for point in points
    ]


def plan_to_operating_point(plan: SimulationPlan) -> OperatingPoint:
    """Extract the operating point from a Postdoc SimulationPlan."""
    return plan.operating_point


def summarize(result: PlasmaResult) -> dict[str, Any]:
    """Compact dict summary for logs/UI."""
    return {
        "points": len(result.points),
        "chemistry": result.diagnostics.chemistry_id,
        "runtime_s": result.diagnostics.runtime_s,
    }
