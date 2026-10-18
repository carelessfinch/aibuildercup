"""Role contracts for the Professor / Postdoc / PhD agents.

FROZEN at v1.0.0 on 2026-10-09 (M0). These Pydantic models are the single
source of truth for structured outputs exchanged between roles, simtools,
the web UI and evals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

CONTRACTS_VERSION = "1.2.0"

Verdict = Literal["approve", "revise", "escalate"]
SignOffState = Literal["pending", "signed_off", "escalated"]
DataKind = Literal["experiment", "model"]  # K2: experiment vs cross-model check


# --- 4M input ---------------------------------------------------------------


class Machine(BaseModel):
    chamber_radius_mm: float | None = None
    reactor_height_mm: float | None = None
    chuck: str | None = None
    diagnostics: list[str] = Field(default_factory=list)


class Material(BaseModel):
    wafer: str
    stack: list[str] = Field(default_factory=list)


class Method(BaseModel):
    recipe: dict[str, Any] = Field(default_factory=dict)
    metrology: list[str] = Field(default_factory=list)


class Man(BaseModel):
    """Optional 4th M (decision I3): operator, shift, experience."""

    operator_experience: Literal["junior", "senior"] | None = None
    shift: str | None = None
    notes: str | None = None


class FourMMetadata(BaseModel):
    case_id: str
    question: str
    machine: Machine
    material: Material
    method: Method
    man: Man | None = None
    source: Literal["form", "spreadsheet", "synthetic"]


# --- Postdoc → PhDs ---------------------------------------------------------


class OperatingPoint(BaseModel):
    power_W: float
    pressure_mTorr: float
    flow_sccm: dict[str, float] = Field(default_factory=dict)
    bias_sweep_V: list[float] = Field(default_factory=list)
    # v1.1.0 (2026-10-09): the Postdoc calibration loop tunes this; engines
    # fall back to their chemistry default (argon: 0.8) when it is None.
    # ge + validator rather than gt: Vertex response schemas reject
    # exclusiveMinimum (see test_contracts_vertex_schema).
    power_coupling_eff: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("power_coupling_eff")
    @classmethod
    def _coupling_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0.0:
            raise ValueError("power_coupling_eff must be > 0")
        return value


class UncertainParameter(BaseModel):
    name: str
    # [lo, hi]; a list, not a tuple, because Vertex rejects prefixItems.
    bounds: list[float] = Field(min_length=2, max_length=2)


class SolverGeometry(BaseModel):
    """Chamber geometry from the 4M Machine fields (v1.2.0).

    None on the plan means "use the chemistry file's default geometry".
    """

    radius_m: float
    height_m: float
    gas_temperature_K: float = 300.0


class CalibrationTarget(BaseModel):
    metric: str
    source: str
    source_kind: DataKind = "experiment"  # K2
    tolerance_pct: float


class SimulationPlan(BaseModel):
    case_id: str
    question: str
    solver: Literal["plasma_global_model", "viennaps_bosch"]
    chemistry_ref: str
    operating_point: OperatingPoint
    uncertain_parameters: list[UncertainParameter] = Field(default_factory=list)
    calibration_targets: list[CalibrationTarget] = Field(default_factory=list)
    acceptance_criteria_proposal: list[str] = Field(default_factory=list)
    literature_refs: list[str] = Field(default_factory=list)
    # v1.2.0: chamber geometry survives planning (W3 flag #1); engines fall
    # back to the chemistry file when it is None.
    geometry: SolverGeometry | None = None


# --- solver outputs ---------------------------------------------------------


class PlasmaPoint(BaseModel):
    bias_V: float
    te_eV: float
    ne_m3: float
    ion_flux_m2s: float
    ion_energy_eV: float
    species_m3: dict[str, float] = Field(default_factory=dict)
    etchant_fluxes_m2s: dict[str, float] = Field(default_factory=dict)
    # v1.2.0: populated once the chemistry supports an etch-yield model
    # (CF4/O2); the Professor rubric checks it when present (W3/W6 flag).
    etch_rate_nm_per_min: float | None = None


class SolverDiagnostics(BaseModel):
    power_balance_residual_pct: float | None = None
    runtime_s: float
    chemistry_id: str
    averaging_note: str | None = None  # K3: how any 2D reference was averaged


class PlasmaResult(BaseModel):
    points: list[PlasmaPoint]
    diagnostics: SolverDiagnostics


class EtchResult(BaseModel):
    depth_um: float
    cd_um: float
    cycles: int
    profile_image: Path
    metrics: dict[str, float] = Field(default_factory=dict)


# --- calibration & review ---------------------------------------------------


class GapRow(BaseModel):
    metric: str
    source_kind: DataKind
    measured: float
    simulated: float
    unit: str
    gap_pct: float
    within_tolerance: bool


class CalibrationReport(BaseModel):
    gaps: list[GapRow]
    tuned_parameters: dict[str, float] = Field(default_factory=dict)
    converged: bool


class RubricResult(BaseModel):
    item_id: str
    status: Literal["pass", "fail", "warn"]
    value: str
    expected: str


class PhysicsCheck(BaseModel):
    name: str
    status: Literal["pass", "fail", "warn"]
    detail: str
    citation: str | None = None


class ProfessorReview(BaseModel):
    verdict: Verdict
    round: int = Field(ge=1)
    rubric_results: list[RubricResult] = Field(default_factory=list)
    physics_checks: list[PhysicsCheck] = Field(default_factory=list)
    feedback: list[str] = Field(default_factory=list)  # specific, actionable
    citations: list[str] = Field(default_factory=list)


class FinalReport(BaseModel):
    case_id: str
    summary: str
    figures: list[Path] = Field(default_factory=list)
    calibration: CalibrationReport | None = None
    reviews: list[ProfessorReview] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    sign_off: SignOffState
    signed_off_by: str | None = None
