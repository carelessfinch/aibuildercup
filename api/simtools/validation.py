"""Rubric-driven validation of solver results (Professor's fixed checks, D5)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

from agents.contracts import PlasmaPoint, PlasmaResult, RubricResult

ELEMENTARY_CHARGE = 1.602176634e-19
AMU_TO_KG = 1.66053906660e-27
ELEMENTAL_MASS_AMU = {
    "H": 1.008,
    "C": 12.011,
    "N": 14.007,
    "O": 15.999,
    "F": 18.998,
    "Ar": 39.948,
    "Cl": 35.45,
    "Si": 28.085,
}


def load_rubric(path: str | Path) -> dict[str, Any]:
    """Load a rubric YAML file (agents/rubrics/*.yaml)."""
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict) or data.get("schema") != "agents.rubric/1":
        msg = f"{path}: expected schema agents.rubric/1"
        raise ValueError(msg)
    return data


def _dotted(data: dict[str, Any], dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        node = node[part]
    return node


def _dominant_ion_mass_kg(point: PlasmaPoint) -> float:
    """Infer the dominant positive ion's molecular mass from its name."""
    ions = [
        (name, density)
        for name, density in point.species_m3.items()
        if name.endswith(("+", "++", "+3")) and math.isfinite(density) and density > 0
    ]
    if not ions:
        return 39.948 * AMU_TO_KG

    formula = max(ions, key=lambda item: item[1])[0].rstrip("+")
    mass_amu = 0.0
    index = 0
    while index < len(formula):
        symbol = formula[index]
        index += 1
        if index < len(formula) and formula[index].islower():
            symbol += formula[index]
            index += 1
        count_text = ""
        while index < len(formula) and formula[index].isdigit():
            count_text += formula[index]
            index += 1
        count = int(count_text) if count_text else 1
        mass_amu += ELEMENTAL_MASS_AMU.get(symbol, 39.948) * count
    return mass_amu * AMU_TO_KG


def check_bohm_flux_consistency(
    result: PlasmaResult,
    tolerance_pct: float = 20.0,
    h_bounds: tuple[float, float] = (0.05, 0.9),
) -> list[RubricResult]:
    """Check the reported ion flux against the Bohm flux from the point's own ne and Te.

    The wall flux is Gamma = h * n0 * u_B, where n0 is the bulk density and h is the
    edge-to-centre density ratio (Lieberman & Lichtenberg ch. 10: about 0.61 for a
    collisionless presheath, and below 0.5 for h_l/h_R once ion collisions matter).
    A global model reports bulk ne, so the implied h = Gamma / (n0 * u_B) must fall
    inside ``h_bounds`` (widened by ``tolerance_pct``); a fixed 0.61 would flag
    every correct collisional run.
    """
    low = h_bounds[0] * (1.0 - tolerance_pct / 100.0)
    high = h_bounds[1] * (1.0 + tolerance_pct / 100.0)
    out: list[RubricResult] = []
    for point in result.points:
        ion_mass_kg = _dominant_ion_mass_kg(point)
        bohm_speed = math.sqrt(ELEMENTARY_CHARGE * max(point.te_eV, 0.0) / ion_mass_kg)
        denominator = point.ne_m3 * bohm_speed
        implied_h = point.ion_flux_m2s / denominator if denominator > 0 else math.nan
        valid = all(
            math.isfinite(value)
            for value in (point.te_eV, point.ne_m3, point.ion_flux_m2s, implied_h)
        )
        out.append(
            RubricResult(
                item_id="bohm_flux_consistency",
                status="pass" if valid and low <= implied_h <= high else "fail",
                value=(
                    f"reported={point.ion_flux_m2s:.3g}, n0*u_B={denominator:.3g}, "
                    f"h={implied_h:.3g}"
                ),
                expected=f"h = Gamma/(n0*u_B) within {low:.3g}-{high:.3g}",
            )
        )
    return out


def check_species_densities_positive(result: PlasmaResult) -> list[RubricResult]:
    """Require a non-empty, finite, strictly positive density map at each point."""
    return [
        RubricResult(
            item_id="species_densities_positive",
            status="pass"
            if point.species_m3
            and all(
                math.isfinite(value) and value > 0 for value in point.species_m3.values()
            )
            else "fail",
            value=f"{len(point.species_m3)} species"
            if point.species_m3
            else "none",
            expected="non-empty; all densities > 0 and finite",
        )
        for point in result.points
    ]


def check_physics(result: PlasmaResult, rubric: dict[str, Any]) -> list[RubricResult]:
    """Evaluate the rubric's fixed_checks against a PlasmaResult.

    Point-level quantities must hold at EVERY sweep point. `special` checks
    (Bohm flux recomputation, species positivity) are wired by W1.
    """
    dumped = result.model_dump()
    out: list[RubricResult] = []
    for item in rubric["fixed_checks"]:
        op = item["op"]
        if op == "special":
            if item["id"] == "bohm_flux_consistency":
                out.extend(
                    check_bohm_flux_consistency(
                        result,
                        item.get("tolerance_pct", 20.0),
                        tuple(item.get("h_bounds", (0.05, 0.9))),
                    )
                )
            elif item["id"] == "species_densities_positive":
                out.extend(check_species_densities_positive(result))
            else:
                out.append(
                    RubricResult(
                        item_id=item["id"],
                        status="warn",
                        value="not wired yet",
                        expected=item.get("description", item["id"]),
                    )
                )
            continue
        try:
            if item["quantity"].startswith("diagnostics."):
                values = [_dotted(dumped, item["quantity"])]
            else:
                values = [_dotted(p, item["quantity"]) for p in dumped["points"]]
        except (KeyError, TypeError):
            out.append(
                RubricResult(
                    item_id=item["id"], status="warn", value="absent", expected=str(item)
                )
            )
            continue
        if any(value is None for value in values):
            # Optional v1.2.0 quantities (e.g. etch_rate_nm_per_min) that the
            # current chemistry cannot yet populate stay non-blocking warns.
            out.append(
                RubricResult(
                    item_id=item["id"],
                    status="warn",
                    value="absent",
                    expected=str(item.get("description", item["id"])),
                )
            )
            continue
        if op == "between":
            lo, hi = item["bounds"]
            ok = all(lo <= v <= hi for v in values)
            expected = f"{lo:.3g} .. {hi:.3g} {item.get('unit', '')}".strip()
        elif op == "abs_at_most":
            ok = all(abs(v) <= item["bound"] for v in values)
            expected = f"|x| <= {item['bound']:g} {item.get('unit', '')}".strip()
        else:
            msg = f"unknown rubric op {op!r}"
            raise ValueError(msg)
        value = f"min={min(values):.3g} max={max(values):.3g}"
        out.append(
            RubricResult(
                item_id=item["id"], status="pass" if ok else "fail", value=value, expected=expected
            )
        )
    return out
