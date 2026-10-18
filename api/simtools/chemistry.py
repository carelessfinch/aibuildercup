"""Chemistry data loading for the `simtools.chemistry/1` YAML schema."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

RateForm = Literal["arrhenius", "cross_section_table"]


class Rate(BaseModel):
    """Arrhenius form: k(Te) = A * Te^B * exp(-C / Te)  [m^3/s, Te in eV]."""

    form: RateForm
    A: float | None = None
    B: float | None = None
    C: float | None = None
    ref: str | None = None  # cross-section table reference id


class Reaction(BaseModel):
    id: str
    equation: str
    type: Literal["electron_impact", "ion", "neutral", "surface"]
    rate: Rate | None = None
    source_note: str | None = None


class Species(BaseModel):
    name: str
    charge: int = 0
    mass_amu: float
    role: Literal["electron", "ion", "neutral", "radical"]


class CrossSection(BaseModel):
    process: str
    target: str
    energy_eV: list[float]
    sigma_m2: list[float]
    source: str


class Geometry(BaseModel):
    radius_m: float = 0.15
    height_m: float = 0.10
    gas_temperature_K: float = 300.0


class Chemistry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(default="simtools.chemistry/1", alias="schema")
    id: str
    status: Literal["ready", "stub"]
    citation: str
    species: list[Species]
    reactions: list[Reaction] = Field(default_factory=list)
    cross_sections: list[CrossSection] = Field(default_factory=list)
    geometry: Geometry = Field(default_factory=Geometry)
    notes: str | None = None

    @model_validator(mode="after")
    def _ready_chemistry_has_rates(self) -> Chemistry:
        if self.status == "ready":
            missing = [r.id for r in self.reactions if r.rate is None]
            if missing:
                msg = f"chemistry {self.id!r} is status=ready but reactions lack rates: {missing}"
                raise ValueError(msg)
        return self


def load_chemistry(path: str | Path) -> Chemistry:
    """Load and validate a chemistry YAML file."""
    data = yaml.safe_load(Path(path).read_text())
    return Chemistry.model_validate(data)
