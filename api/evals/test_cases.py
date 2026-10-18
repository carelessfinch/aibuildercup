"""Case-suite invariants: format, coverage matrix, and expectation hygiene (E4)."""

import json
from pathlib import Path

from simtools.fourm import parse_form
from simtools.validation import load_rubric

REQUIRED_COVERAGE = {
    "wrong_unit",
    "impossible_te",
    "power_balance_violation",
    "chemistry_invalid",
    "out_of_range_power",
    "out_of_range_pressure",
    "out_of_range_flow",
    "negative_flow",
    "impossible_pressure",
    "metrology_mismatch",
    "bohm_flux_consistency",
    "non_monotone_sweep",
    "missing_wafer",
}

CASES = Path(__file__).parent / "cases"


def load_cases() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(CASES.glob("*.json"))]


def test_cases_exist_and_parse() -> None:
    cases = load_cases()
    assert len(cases) >= 11
    for case in cases:
        assert case["kind"] in {"good", "fault"}
        assert case["case_id"]
        assert case["expect"]["verdict_in"]
    assert len({case["case_id"] for case in cases}) == len(cases)


def test_fault_injections_and_coverage_are_explicit() -> None:
    cases = load_cases()
    faults = [case for case in cases if case["kind"] == "fault"]
    assert len(faults) >= 8
    covered: set[str] = set()
    for case in faults:
        fault = case["fault"]
        assert fault["site"] in {"fourm_input", "plan", "plasma_result", "chemistry"}
        assert fault["description"]
        assert fault.get("inject"), case["case_id"]
        coverage = set(fault.get("coverage", []))
        assert coverage, case["case_id"]
        covered.update(coverage)
        assert set(case["expect"]["verdict_in"]) <= {"revise", "escalate"}
        assert case["expect"]["must_not_signoff"] is True
        assert case["expect"]["must_catch"], case["case_id"]
    assert REQUIRED_COVERAGE <= covered


def test_good_cases_have_known_review_scope() -> None:
    goods = [case for case in load_cases() if case["kind"] == "good"]
    assert len(goods) >= 3
    for case in goods:
        assert case["expect"]["must_signoff_possible"] is True
        assert case["expect"]["verdict_in"] == ["approve"]
        assert case.get("review_scope", "result") in {"metadata", "result"}
        if case.get("stretch"):
            assert case["review_scope"] == "metadata"


def test_fourm_inputs_are_valid_contracts() -> None:
    for case in load_cases():
        if case.get("fault", {}).get("site") != "fourm_input":
            meta = parse_form(case["fourm_input"])
            assert meta.case_id == case["fourm_input"]["case_id"]


def test_fault_cases_must_never_sign_off() -> None:
    faults = [c for c in load_cases() if c["kind"] == "fault"]
    assert len(faults) >= 8
    for case in faults:
        assert case["expect"]["must_not_signoff"] is True
        assert case["expect"]["must_catch"], case["case_id"]


def test_good_cases_allow_signoff() -> None:
    for case in load_cases():
        if case["kind"] == "good":
            assert case["expect"].get("must_signoff_possible") is True


def test_case_rubric_refs_load() -> None:
    for case in load_cases():
        if "rubric_ref" not in case:
            continue
        assert load_rubric(case["rubric_ref"])["schema"] == "agents.rubric/1"
