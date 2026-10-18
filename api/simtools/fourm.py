"""4M metadata parsing (form + spreadsheet) into the shared contract (I3)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from agents.contracts import FourMMetadata


def parse_form(data: dict[str, Any], *, enforce_ranges: bool = True) -> FourMMetadata:
    """Validate a 4M web-form payload (or plain dict) into FourMMetadata."""
    metadata = FourMMetadata.model_validate(data)
    if enforce_ranges:
        _validate_input_ranges(data)
    return metadata


def _validate_input_ranges(data: dict[str, Any]) -> None:
    """Enforce demo-safe numeric ranges without changing the frozen contract."""
    recipe = data.get("method", {}).get("recipe", {})
    checks = (
        ("power_W", recipe.get("power_W", recipe.get("coil_power_W")), 1.0, 1000.0),
        ("pressure_mTorr", recipe.get("pressure_mTorr"), 1.0, 500.0),
    )
    for field, value, minimum, maximum in checks:
        if value is not None and not minimum <= _finite_float(value) <= maximum:
            raise ValueError(
                f"method.recipe.{field} must be between {minimum:g} and {maximum:g}"
            )

    flows = dict(recipe.get("flow_sccm") or {})
    flows.update(
        {
            key: value
            for key, value in recipe.items()
            if key.endswith("_sccm") and key != "flow_sccm"
        }
    )
    for gas, value in flows.items():
        if not 0.0 <= _finite_float(value) <= 1000.0:
            raise ValueError(f"method.recipe flow {gas} must be between 0 and 1000 sccm")

    biases = recipe.get("bias_sweep_V")
    if biases is not None:
        if len(biases) > 12:
            raise ValueError("method.recipe.bias_sweep_V supports at most 12 points")
        if any(not -200.0 <= _finite_float(value) <= 200.0 for value in biases):
            raise ValueError("method.recipe.bias_sweep_V values must be between -200 and 200 V")


def parse_spreadsheet(path: str | Path) -> FourMMetadata:
    """Parse the cleaned 4M spreadsheet template (W5 implements with openpyxl)."""
    raise NotImplementedError("spreadsheet parsing lands in W5 (web + jobs)")


def _finite_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"expected a finite number, got {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError("expected a finite number")
    return number
