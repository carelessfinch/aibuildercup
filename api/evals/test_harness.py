"""Behavioural tests for the W6 offline review harness."""

import pytest

from agents.contracts import ProfessorReview
from evals.harness import (
    apply_injection,
    default_review,
    load_cases,
    prepare_case,
    run_case,
    run_suite,
    timing_from_events,
)


def make_review(verdict: str, feedback: tuple[str, ...] = ()) -> ProfessorReview:
    return ProfessorReview(verdict=verdict, round=1, feedback=list(feedback))


def test_injections_are_explicit_and_do_not_mutate_source() -> None:
    source = {"a": {"b": [1, 2]}}
    updated = apply_injection(source, {"path": "a.b.1", "op": "set", "value": 20})
    assert source["a"]["b"] == [1, 2]
    assert updated["a"]["b"] == [1, 20]
    with pytest.raises(ValueError, match="needs a path"):
        apply_injection(source, {"op": "set"})


def test_default_review_catches_seeded_faults() -> None:
    report = run_suite()
    by_id = {run.case_id: run for run in report.runs}
    assert by_id["fault_bias_mv_as_v"].passed
    assert by_id["fault_te_impossible"].passed
    assert report.silent_signoffs == 0


def test_good_cases_can_be_approved_by_default_review() -> None:
    report = run_suite()
    assert report.good_pass_rate == 1.0
    assert {run.review.verdict for run in report.good_runs} == {"approve"}


def test_invalid_chemistry_is_escalated_and_cited_in_checks() -> None:
    case = next(item for item in load_cases() if item["case_id"] == "fault_chemistry_negative_rate")
    run = run_case(case)
    assert run.review.verdict == "escalate"
    assert run.passed
    assert "chemistry_schema" in _check_names(run.review)


def test_missing_wafer_is_reported_without_crashing() -> None:
    case = next(item for item in load_cases() if item["case_id"] == "fault_missing_wafer")
    run = run_case(case)
    assert run.passed
    assert "wafer missing: provide Material.wafer" in run.review.feedback


def test_custom_review_fn_is_the_m2_seam() -> None:
    case = load_cases()[0]

    def reviewer(request):
        assert request.case_id == case["case_id"]
        return make_review("revise", ("custom reviewer saw the request",))

    run = run_case(case, reviewer)
    assert run.verdict_correct
    assert run.review.feedback == ["custom reviewer saw the request"]


def test_timing_stub_uses_event_log_intervals() -> None:
    events = [
        {"event": "form_submit", "at_seconds": 0},
        {"event": "human_active_start", "at_seconds": 10},
        {"event": "human_active_end", "at_seconds": 190},
        {"event": "sign_off", "at_seconds": 900},
    ]
    kpis = timing_from_events("timing-case", events)
    assert kpis.end_to_end_minutes == 15
    assert kpis.expert_minutes == 3
    assert kpis.end_to_end_ratio == 0.125


def test_default_review_requests_are_well_formed() -> None:
    for case in load_cases():
        request = prepare_case(case)
        assert request.case_id == case["case_id"]
        assert request.rubric["schema"] == "agents.rubric/1"
        assert default_review(request).round == 1


def _check_names(review: ProfessorReview) -> set[str]:
    return {item.name for item in review.physics_checks}
