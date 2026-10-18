"""ViennaPS physical Bosch etch. Interface frozen M0; implementation lands in W2.

W2 uses ViennaPS 4.6.x with ViennaLS pinned to 5.8.5, physical
SF6C4F8Etching(ionFlux, etchantFlux, meanEnergy, sigmaEnergy) fed by the
plasma model's fluxes. Stretch workstream — never blocks M1-M3.
"""

from __future__ import annotations

from typing import Any

from agents.contracts import EtchResult


def run_bosch(config: dict[str, Any]) -> EtchResult:
    """Run the physical Bosch model. Raises until W2 lands."""
    raise NotImplementedError("ViennaPS Bosch model lands in W2 (stretch)")
