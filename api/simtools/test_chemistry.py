"""Chemistry schema tests: argon ready, CF4/O2 stub, ready-means-rated (K1)."""

from pathlib import Path

import pytest

from simtools.chemistry import Chemistry, load_chemistry

DATA = Path(__file__).parent / "data"


def test_argon_chemistry_loads_ready() -> None:
    chem = load_chemistry(DATA / "chemistry_ar_lieberman.yaml")
    assert chem.status == "ready"
    assert chem.id == "ar_lieberman_icp"
    assert all(r.rate is not None for r in chem.reactions)


def test_cf4o2_stub_loads_but_is_marked_stub() -> None:
    chem = load_chemistry(DATA / "chemistry_cf4o2_kimura2006.yaml")
    assert chem.status == "stub"
    assert chem.reactions == []


def test_ready_chemistry_must_have_rates() -> None:
    with pytest.raises(ValueError, match="lack rates"):
        Chemistry.model_validate(
            {
                "id": "broken",
                "status": "ready",
                "citation": "x",
                "species": [{"name": "e", "mass_amu": 0.0005486, "role": "electron", "charge": -1}],
                "reactions": [{"id": "R1", "equation": "e -> e", "type": "electron_impact"}],
            }
        )
