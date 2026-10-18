"""Public, allow-listed demo presets sourced from the public eval cases."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.contracts import FourMMetadata, PlasmaResult
from evals.harness import FIXTURE_DIR, _chemistry_issues, _metadata_issues, apply_fault
from simtools.chemistry import Chemistry
from simtools.fourm import parse_form

CASE_DIR = Path(__file__).resolve().parents[2] / "evals" / "cases"
# Every public eval case, in the order the web app lists them.
ALLOWED_PRESET_IDS = (
    "good_cf4o2_baseline",
    "good_argon_baseline",
    "good_bosch_metadata_stretch",
    # Faults in the solver output: the agents run and the Professor must catch them.
    "fault_te_impossible",
    "fault_power_balance_violation",
    "fault_bohm_flux_inconsistent",
    # Faults in the 4M input or chemistry: rejected at intake with the reason.
    "fault_missing_wafer",
    "fault_negative_flow",
    "fault_impossible_pressure",
    "fault_pressure_out_of_range",
    "fault_power_out_of_range",
    "fault_bias_mv_as_v",
    "fault_non_monotone_sweep",
    "fault_mismatched_metrology",
    "fault_chemistry_negative_rate",
    "fault_chemistry_unknown_species",
)


@dataclass(frozen=True)
class DemoPreset:
    preset_id: str
    kind: str
    description: str
    metadata: FourMMetadata
    fault: dict[str, Any] | None = None


def list_presets(case_dir: Path = CASE_DIR) -> list[dict[str, Any]]:
    """Return the allow-listed presets with the 4M input the form shows.

    Solver payloads stay server-side; for 4M-input faults the faulty input is
    returned so the form shows exactly what will be rejected.
    """
    rows: list[dict[str, Any]] = []
    for preset_id in ALLOWED_PRESET_IDS:
        case = _read_case(preset_id, case_dir)
        fault = case.get("fault") or {}
        rows.append(
            {
                "preset_id": preset_id,
                "title": _title(preset_id),
                "kind": str(case.get("kind", "demo")),
                "description": str(
                    case.get("description") or fault.get("description") or preset_id
                ),
                "fault_site": fault.get("site"),
                "fourm_input": _preset_fourm_input(case),
            }
        )
    return rows


PRESET_TITLES = {
    "good_cf4o2_baseline": "CF\u2084/O\u2082 baseline",
    "good_argon_baseline": "Argon baseline",
    "good_bosch_metadata_stretch": "Bosch metadata (stretch)",
    "fault_te_impossible": "Fault: impossible electron temperature",
    "fault_power_balance_violation": "Fault: power-balance violation",
    "fault_bohm_flux_inconsistent": "Fault: Bohm flux inconsistent",
    "fault_missing_wafer": "Fault: missing wafer",
    "fault_negative_flow": "Fault: negative gas flow",
    "fault_impossible_pressure": "Fault: impossible pressure",
    "fault_pressure_out_of_range": "Fault: pressure out of range",
    "fault_power_out_of_range": "Fault: power out of range",
    "fault_bias_mv_as_v": "Fault: bias entered in mV as V",
    "fault_non_monotone_sweep": "Fault: non-monotone bias sweep",
    "fault_mismatched_metrology": "Fault: metrology mismatch",
    "fault_chemistry_negative_rate": "Fault: negative chemistry rate",
    "fault_chemistry_unknown_species": "Fault: unknown chemistry species",
}


def _title(preset_id: str) -> str:
    return PRESET_TITLES.get(preset_id, preset_id.replace("_", " "))


def _preset_fourm_input(case: dict[str, Any]) -> dict[str, Any]:
    raw = copy.deepcopy(case["fourm_input"])
    fault = case.get("fault") or {}
    return apply_fault(raw, fault) if fault.get("site") == "fourm_input" else raw


def _intake_rejection(preset_id: str, case: dict[str, Any]) -> str | None:
    """Reason a 4M-input or chemistry fault is rejected before any agent runs."""
    fault = case.get("fault") or {}
    site = fault.get("site")
    if site == "fourm_input":
        try:
            metadata = parse_form(_preset_fourm_input(case), enforce_ranges=False)
        except (TypeError, ValueError) as exc:
            first = str(exc).splitlines()[0]
            return f"{fault.get('description', '4M input invalid')} ({first})"
        issues = _metadata_issues(metadata)
        return "; ".join(f"{label}: {detail}" for label, detail in issues) or None
    if site == "chemistry":
        fixture = case.get("chemistry_fixture", "chemistry_ar_ready.json")
        raw = json.loads((FIXTURE_DIR / fixture).read_text(encoding="utf-8"))
        try:
            chemistry = Chemistry.model_validate(apply_fault(raw, fault))
        except ValueError as exc:
            return f"chemistry_schema: {exc}"
        return "; ".join(_chemistry_issues(chemistry)) or None
    return None


def load_preset(preset_id: str, case_dir: Path = CASE_DIR) -> DemoPreset:
    if preset_id not in ALLOWED_PRESET_IDS:
        raise KeyError(preset_id)
    case = _read_case(preset_id, case_dir)
    reason = _intake_rejection(preset_id, case)
    if reason:
        msg = f"Preset {preset_id} rejected at intake (not signed off): {reason}"
        raise ValueError(msg)
    try:
        metadata = parse_form(copy.deepcopy(case["fourm_input"]))
    except (KeyError, TypeError, ValueError) as exc:
        msg = f"Preset {preset_id} has an invalid 4M payload"
        raise ValueError(msg) from exc
    fault = case.get("fault")
    if fault is not None and fault.get("site") != "plasma_result":
        msg = f"Preset {preset_id} uses an unsupported fault site"
        raise ValueError(msg) from None
    return DemoPreset(
        preset_id=preset_id,
        kind=str(case.get("kind", "demo")),
        description=str(case.get("description", preset_id)),
        metadata=metadata,
        fault=copy.deepcopy(fault) if fault is not None else None,
    )


def fault_injector(result: PlasmaResult, fault: dict[str, Any]) -> PlasmaResult:
    """Compatibility callback for the ADK ReviewLoopNode."""
    return apply_plasma_fault(result, fault)


def apply_plasma_fault(result: PlasmaResult, fault: dict[str, Any]) -> PlasmaResult:
    injection = fault.get("inject")
    if not isinstance(injection, dict) or injection.get("op") != "set":
        msg = "demo preset injection must be an explicit set operation"
        raise ValueError(msg)
    raw = result.model_dump(mode="json")
    _assign_dotted(raw, str(injection.get("path", "")), injection.get("value"))
    try:
        return PlasmaResult.model_validate(raw)
    except ValueError as exc:
        msg = "demo preset injection produced an invalid PlasmaResult"
        raise ValueError(msg) from exc


def _read_case(preset_id: str, case_dir: Path) -> dict[str, Any]:
    path = case_dir / f"{preset_id}.json"
    if not path.is_file():
        msg = f"Unknown demo preset: {preset_id}"
        raise KeyError(msg)
    try:
        case = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"Demo preset {preset_id} could not be loaded"
        raise ValueError(msg) from exc
    if not isinstance(case, dict):
        msg = f"Demo preset {preset_id} must be a JSON object"
        raise ValueError(msg)
    return case


def _assign_dotted(target: dict[str, Any], path: str, value: Any) -> None:
    parts: list[str | int] = [
        int(part) if part.isdigit() else part for part in path.split(".") if part
    ]
    invalid = any(
        not str(part).isidentifier() and not isinstance(part, int) for part in parts
    )
    if not parts or invalid:
        msg = f"Invalid preset injection path: {path!r}"
        raise ValueError(msg)
    node: Any = target
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value
