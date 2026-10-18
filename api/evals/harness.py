"""Offline fault-injection harness and Professor-review protocol (E4).

The Professor agent adapter in M2 implements :class:`ReviewFn`; the default
reviewer wraps the frozen physics rubric so the suite runs without Gemini.
"""

from __future__ import annotations

import argparse
import copy
import json
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.contracts import FourMMetadata, PlasmaResult, ProfessorReview, SimulationPlan
from simtools.chemistry import Chemistry
from simtools.fourm import parse_form
from simtools.validation import check_physics, load_rubric

REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = Path(__file__).parent / "cases"
DEFAULT_RUBRIC = REPO_ROOT / "agents" / "rubrics" / "plasma.yaml"
FIXTURE_DIR = Path(__file__).parent / "fixtures"

SITES = {"fourm_input", "plan", "plasma_result", "chemistry"}
GOOD_VERDICTS = {"approve"}
FAULT_VERDICTS = {"revise", "escalate"}


@dataclass(frozen=True)
class ReviewRequest:
    """All review inputs in one request.

    ``metadata_error``/``chemistry_error`` let a reviewer catch malformed inputs
    while the frozen Pydantic contracts remain valid for the successful path.
    """

    case_id: str
    rubric: dict[str, Any]
    metadata: FourMMetadata | None
    raw_metadata: dict[str, Any]
    metadata_error: str | None
    result: PlasmaResult | None
    plan: SimulationPlan | None
    chemistry: Chemistry | None
    raw_chemistry: dict[str, Any] | None
    chemistry_error: str | None
    review_scope: str = "result"


ReviewFn = Callable[[ReviewRequest], ProfessorReview]


@dataclass(frozen=True)
class CaseRun:
    case_id: str
    kind: str
    expected_verdicts: set[str]
    must_catch: tuple[str, ...]
    review: ProfessorReview
    caught: tuple[str, ...]
    missed: tuple[str, ...]
    verdict_correct: bool
    silent_signoff: bool
    passed: bool
    review_seconds: float


@dataclass(frozen=True)
class TimingKPIs:
    case_id: str
    end_to_end_minutes: float | None
    expert_minutes: float | None
    baseline_minutes: float = 120.0

    @property
    def end_to_end_ratio(self) -> float | None:
        if self.end_to_end_minutes is None:
            return None
        return self.end_to_end_minutes / self.baseline_minutes


@dataclass
class EvalReport:
    runs: list[CaseRun]
    timing: list[TimingKPIs] = field(default_factory=list)

    @property
    def fault_runs(self) -> list[CaseRun]:
        return [run for run in self.runs if run.kind == "fault"]

    @property
    def good_runs(self) -> list[CaseRun]:
        return [run for run in self.runs if run.kind == "good"]

    @property
    def catch_rate(self) -> float:
        faults = self.fault_runs
        if not faults:
            return 0.0
        return sum(run.passed for run in faults) / len(faults)

    @property
    def silent_signoffs(self) -> int:
        return sum(run.silent_signoff for run in self.fault_runs)

    @property
    def good_pass_rate(self) -> float:
        goods = self.good_runs
        if not goods:
            return 0.0
        return sum(run.passed for run in goods) / len(goods)

    def summary(self) -> dict[str, Any]:
        timed = [item for item in self.timing if item.end_to_end_minutes is not None]
        expert = [item for item in self.timing if item.expert_minutes is not None]
        return {
            "cases": len(self.runs),
            "faults": len(self.fault_runs),
            "goods": len(self.good_runs),
            "catch_rate": self.catch_rate,
            "caught_faults": sum(run.passed for run in self.fault_runs),
            "silent_signoffs": self.silent_signoffs,
            "good_pass_rate": self.good_pass_rate,
            "review_seconds_total": sum(run.review_seconds for run in self.runs),
            "end_to_end_minutes": {
                "samples": len(timed),
                "values": [item.end_to_end_minutes for item in timed],
            },
            "expert_minutes": {
                "samples": len(expert),
                "values": [item.expert_minutes for item in expert],
            },
        }


def _parse_timestamp(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError as exc:
            raise ValueError(
                f"event timestamp must be epoch seconds or ISO-8601: {value!r}"
            ) from exc
    raise TypeError(f"event timestamp must be epoch seconds or ISO-8601, got {type(value)}")


def timing_from_events(case_id: str, events: Sequence[Mapping[str, Any]]) -> TimingKPIs:
    """Compute KPI stubs from the event log emitted by web/agents in M2.

    Expected event names are ``form_submit``, ``sign_off``,
    ``human_active_start`` and ``human_active_end``. Unpaired active intervals
    are ignored rather than invented.
    """

    starts: list[float] = []
    active_s = 0.0
    submit_at: float | None = None
    signoff_at: float | None = None
    for event in events:
        name = event.get("event")
        timestamp = _parse_timestamp(event.get("at_seconds", event.get("timestamp")))
        if name == "form_submit":
            submit_at = timestamp
        elif name == "sign_off":
            signoff_at = timestamp
        elif name == "human_active_start":
            starts.append(timestamp)
        elif name == "human_active_end" and starts:
            active_s += max(0.0, timestamp - starts.pop())
    e2e = None if submit_at is None or signoff_at is None else max(0.0, signoff_at - submit_at)
    return TimingKPIs(
        case_id=case_id,
        end_to_end_minutes=None if e2e is None else e2e / 60,
        expert_minutes=active_s / 60,
    )


def _path_parts(path: str) -> list[str | int]:
    parts: list[str | int] = []
    for raw in path.split("."):
        if raw.isdigit():
            parts.append(int(raw))
        else:
            parts.append(raw)
    return parts


def apply_injection(target: Any, injection: Mapping[str, Any]) -> Any:
    """Apply an explicit dotted-path mutation without mutating the source."""

    if "path" not in injection:
        raise ValueError(f"injection needs a path: {injection!r}")
    operation = injection.get("op", "set")
    parts = _path_parts(injection["path"])
    if not parts:
        raise ValueError("injection path cannot be empty")
    output = copy.deepcopy(target)
    node = output
    for part in parts[:-1]:
        node = node[part]
    last = parts[-1]
    if operation == "set":
        if "value" not in injection:
            raise ValueError(f"set injection needs a value: {injection!r}")
        node[last] = injection["value"]
    elif operation == "add":
        node[last] = node[last] + injection["value"]
    elif operation == "remove":
        del node[last]
    else:
        raise ValueError(f"unknown injection op: {operation!r}")
    return output


def apply_fault(target: Any, fault: Mapping[str, Any]) -> Any:
    spec = fault.get("inject")
    if spec is None:
        raise ValueError(f"fault {fault.get('site')!r} has no explicit inject spec")
    if isinstance(spec, Mapping):
        return apply_injection(target, spec)
    for injection in spec:
        target = apply_injection(target, injection)
    return target


def _chemistry_issues(chemistry: Chemistry) -> list[str]:
    issues: list[str] = []
    species = {item.name for item in chemistry.species}
    electrons = [item for item in chemistry.species if item.role == "electron"]
    if len(electrons) != 1:
        issues.append("chemistry_schema: exactly one electron species is required")
    for reaction in chemistry.reactions:
        if reaction.rate is not None and min(
            value
            for value in (reaction.rate.A, reaction.rate.B, reaction.rate.C)
            if value is not None
        ) < 0:
            issues.append(f"chemistry_schema: negative rate coefficient in {reaction.id}")
        tokens = {
            token
            for side in reaction.equation.split("->")
            for token in side.replace("+", " ").split()
        }
        unknown = sorted(token for token in tokens if token not in species and token != "e")
        if unknown:
            issues.append(
                f"chemistry_schema: unknown species {', '.join(unknown)} in {reaction.id}"
            )
    return issues


def _metadata_issues(metadata: FourMMetadata) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    recipe = metadata.method.recipe
    power = recipe.get("power_W")
    pressure = recipe.get("pressure_mTorr")
    flows = recipe.get("flow_sccm", {})
    bias = recipe.get("bias_sweep_V", [])
    if not metadata.material.wafer:
        issues.append(("wafer missing", "Material.wafer is required"))
    if not isinstance(power, int | float) or not 5 <= power <= 1000:
        issues.append(("power_out_of_range", f"power_W={power} outside 5..1000 W"))
    if not isinstance(pressure, int | float) or not 0.5 <= pressure <= 100:
        label = "pressure_out_of_range"
        if isinstance(pressure, int | float) and pressure <= 0:
            label = "impossible_pressure"
        issues.append((label, f"pressure_mTorr={pressure} outside 0.5..100 mTorr"))
    for gas, value in sorted(flows.items()):
        if not isinstance(value, int | float) or value <= 0:
            issues.append(("negative_flow", f"flow_sccm[{gas}]={value} must be positive"))
        elif value > 500:
            issues.append(("flow_out_of_range", f"flow_sccm[{gas}]={value} exceeds 500 sccm"))
    if not isinstance(bias, list) or not bias:
        issues.append(("bias_sweep_missing", "bias_sweep_V must be a non-empty list"))
    else:
        if any(not isinstance(value, int | float) or abs(value) > 1000 for value in bias):
            issues.append(("bias out of plausible range", "bias sweep must be within +/-1000 V"))
        if any(left >= right for left, right in zip(bias, bias[1:], strict=False)):
            issues.append(("non_monotone_bias_sweep", f"bias_sweep_V={bias} is not increasing"))
    question = metadata.question.lower()
    needs_probe = "electron density" in question or "ion flux" in question
    if needs_probe and "langmuir_probe" not in metadata.machine.diagnostics:
        issues.append(
            (
                "metrology_mismatch",
                "question needs ne/ion-flux validation but langmuir_probe is absent",
            )
        )
    return issues


def default_review(request: ReviewRequest) -> ProfessorReview:
    """Deterministic offline reviewer used until the W3 Professor is wired."""

    feedback: list[str] = []
    physics_checks: list[dict[str, Any]] = []
    rubric_results: list[dict[str, Any]] = []
    has_failure = False

    if request.metadata_error is not None:
        if "wafer" in request.metadata_error.lower():
            feedback.append("wafer missing: provide Material.wafer")
        else:
            feedback.append(f"invalid 4M metadata: {request.metadata_error}")
        has_failure = True

    metadata = request.metadata
    if metadata is not None:
        for issue, detail in _metadata_issues(metadata):
            feedback.append(f"{issue}: {detail}")
            has_failure = True

    if request.chemistry_error is not None:
        feedback.append(f"chemistry_schema: {request.chemistry_error}")
        physics_checks.append(
            {
                "name": "chemistry_schema",
                "status": "fail",
                "detail": request.chemistry_error,
            }
        )
        return ProfessorReview(
            verdict="escalate",
            round=1,
            physics_checks=physics_checks,
            feedback=feedback,
        )

    if request.raw_chemistry is not None and request.chemistry is not None:
        chemistry_issues = _chemistry_issues(request.chemistry)
        if chemistry_issues:
            feedback.extend(chemistry_issues)
            physics_checks.append(
                {
                    "name": "chemistry_schema",
                    "status": "fail",
                    "detail": "; ".join(chemistry_issues),
                }
            )
            return ProfessorReview(
                verdict="escalate",
                round=1,
                physics_checks=physics_checks,
                feedback=feedback,
            )

    if request.plan is not None:
        bias = request.plan.operating_point.bias_sweep_V
        if any(left >= right for left, right in zip(bias, bias[1:], strict=False)):
            feedback.append(f"non_monotone_bias_sweep: plan bias_sweep_V={bias} is not increasing")
            has_failure = True

    result = request.result
    if result is not None:
        rubric_results = [item.model_dump() for item in check_physics(result, request.rubric)]
        failed = [item for item in rubric_results if item["status"] == "fail"]
        for item in failed:
            feedback.append(f"{item['item_id']}: got {item['value']}, expected {item['expected']}")
        has_failure = has_failure or bool(failed)
    elif request.review_scope != "metadata":
        feedback.append("no PlasmaResult: cannot approve a physics result")
        has_failure = True

    if request.review_scope == "metadata" and not has_failure:
        verdict = "approve"
    elif request.chemistry is not None and request.raw_chemistry is not None and not feedback:
        verdict = "approve"
    elif has_failure:
        verdict = "revise"
    else:
        verdict = "approve"
    return ProfessorReview(
        verdict=verdict,
        round=1,
        rubric_results=rubric_results,
        physics_checks=physics_checks,
        feedback=feedback,
    )


def _load_rubric_for(case: Mapping[str, Any]) -> dict[str, Any]:
    rubric_path = case.get("rubric_ref")
    if rubric_path is None:
        return load_rubric(DEFAULT_RUBRIC)
    return load_rubric(REPO_ROOT / rubric_path)


def _validate_target(kind: str, target: Any) -> Any:
    if kind == "fourm_input":
        return parse_form(target, enforce_ranges=False)
    if kind == "plasma_result":
        return PlasmaResult.model_validate(target)
    if kind == "plan":
        return SimulationPlan.model_validate(target)
    if kind == "chemistry":
        return Chemistry.model_validate(target)
    raise ValueError(f"unknown injection site: {kind!r}")


def prepare_case(case: Mapping[str, Any]) -> ReviewRequest:
    fault = case.get("fault", {})
    site = fault.get("site")
    metadata_raw = copy.deepcopy(case.get("fourm_input", {}))
    result_raw = copy.deepcopy(case.get("plasma_result"))
    plan_raw = copy.deepcopy(case.get("plan"))
    chemistry_raw = copy.deepcopy(case.get("chemistry"))
    if site == "fourm_input":
        metadata_raw = apply_fault(metadata_raw, fault)
    elif site == "plasma_result":
        if result_raw is None:
            raise ValueError(f"{case['case_id']}: plasma_result injection needs a baseline")
        result_raw = apply_fault(result_raw, fault)
    elif site == "plan":
        if plan_raw is None:
            raise ValueError(f"{case['case_id']}: plan injection needs a baseline")
        plan_raw = apply_fault(plan_raw, fault)
    elif site == "chemistry":
        if chemistry_raw is None:
            fixture = case.get("chemistry_fixture", "chemistry_ar_ready.json")
            chemistry_raw = json.loads((FIXTURE_DIR / fixture).read_text())
        chemistry_raw = apply_fault(chemistry_raw, fault)

    metadata: FourMMetadata | None = None
    metadata_error: str | None = None
    result: PlasmaResult | None = None
    chemistry: Chemistry | None = None
    chemistry_error: str | None = None
    plan: SimulationPlan | None = None
    try:
        metadata = _validate_target("fourm_input", metadata_raw)
    except Exception as exc:  # noqa: BLE001 - harness records malformed eval inputs
        metadata_error = str(exc)
    try:
        result = _validate_target("plasma_result", result_raw)
    except Exception as exc:  # noqa: BLE001
        if result_raw is not None:
            raise ValueError(f"{case['case_id']}: invalid injected PlasmaResult: {exc}") from exc
    try:
        chemistry = _validate_target("chemistry", chemistry_raw)
    except Exception as exc:  # noqa: BLE001
        if chemistry_raw is not None:
            chemistry_error = str(exc)
    if plan_raw is not None:
        plan = _validate_target("plan", plan_raw)
    return ReviewRequest(
        case_id=case["case_id"],
        rubric=_load_rubric_for(case),
        metadata=metadata,
        raw_metadata=metadata_raw,
        metadata_error=metadata_error,
        result=result,
        plan=plan,
        chemistry=chemistry,
        raw_chemistry=chemistry_raw,
        chemistry_error=chemistry_error,
        review_scope=case.get("review_scope", "result"),
    )


def _texts(review: ProfessorReview) -> set[str]:
    texts: set[str] = set()
    texts.update(review.feedback)
    texts.update(item.item_id for item in review.rubric_results)
    texts.update(item.name for item in review.physics_checks)
    texts.update(item.detail for item in review.physics_checks)
    texts.update(f"{item.item_id}: {item.value}" for item in review.rubric_results)
    return texts


def _caught(must_catch: Iterable[str], review: ProfessorReview) -> tuple[str, ...]:
    texts = _texts(review)
    return tuple(item for item in must_catch if any(item in text for text in texts))


def run_case(case: Mapping[str, Any], review_fn: ReviewFn = default_review) -> CaseRun:
    started = time.perf_counter()
    request = prepare_case(case)
    review = review_fn(request)
    elapsed = time.perf_counter() - started
    kind = case["kind"]
    allowed = FAULT_VERDICTS if kind == "fault" else GOOD_VERDICTS
    must_catch = tuple(case.get("expect", {}).get("must_catch", []))
    caught = _caught(must_catch, review)
    missed = tuple(item for item in must_catch if item not in caught)
    verdict_correct = review.verdict in allowed
    silent = kind == "fault" and review.verdict == "approve"
    passed = verdict_correct and not missed and not silent
    return CaseRun(
        case_id=case["case_id"],
        kind=kind,
        expected_verdicts=allowed,
        must_catch=must_catch,
        review=review,
        caught=caught,
        missed=missed,
        verdict_correct=verdict_correct,
        silent_signoff=silent,
        passed=passed,
        review_seconds=elapsed,
    )


def load_cases(case_dir: Path = CASE_DIR) -> list[dict[str, Any]]:
    return [json.loads(path.read_text()) for path in sorted(case_dir.glob("*.json"))]


def run_suite(
    review_fn: ReviewFn = default_review,
    cases: Sequence[Mapping[str, Any]] | None = None,
) -> EvalReport:
    loaded = load_cases() if cases is None else [dict(case) for case in cases]
    runs = [run_case(case, review_fn) for case in loaded]
    timing = [
        timing_from_events(case["case_id"], events)
        for case in loaded
        if (events := case.get("event_log")) is not None
    ]
    return EvalReport(runs=runs, timing=timing)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print machine-readable summary")
    args = parser.parse_args(argv)
    report = run_suite()
    payload = report.summary()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for run in report.runs:
            state = "PASS" if run.passed else "FAIL"
            print(f"{state} {run.case_id}: {run.review.verdict}")
            for issue in run.missed:
                print(f"  missed: {issue}")
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if (
        report.silent_signoffs == 0
        and report.good_pass_rate == 1.0
        and report.catch_rate >= 0.8
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
