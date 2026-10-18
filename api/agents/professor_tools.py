"""Deterministic review evidence and literature-derived case checks."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Literal

from agents.contracts import PhysicsCheck, PlasmaResult, ProfessorReview, RubricResult
from agents.litrag_tools import safe_search_literature
from agents.rubric import rubric_path
from simtools.validation import check_physics, load_rubric

BASE_QUERY_NAMES = (
    "electron temperature in a low-pressure ICP global model",
    "Bohm flux at a plasma wafer sheath edge",
    "CF4/O2 ICP silicon etch rate versus substrate bias",
)
CheckStatus = Literal["pass", "fail", "warn"]


def derive_case_checks(
    chemistry_id: str = "cf4o2_kimura2006",
    search_fn: Callable[..., dict[str, Any]] = safe_search_literature,
    queries: Iterable[str] = BASE_QUERY_NAMES,
) -> list[PhysicsCheck]:
    """Create 2-4 cited candidate checks; unavailable literature degrades to warns."""
    checks: list[PhysicsCheck] = []
    selected_queries = list(queries)[:4]
    if len(selected_queries) < 2:
        selected_queries = list(BASE_QUERY_NAMES)[:2]

    for query in selected_queries:
        response = search_fn(query, top_k=1, kind=None)
        citation = None
        status: CheckStatus = "warn"
        if response.get("status") == "success" and response.get("results"):
            citation = str(response["results"][0].get("citation", "")) or None
            detail = (
                "Literature-derived check: validate against the cited passage. "
                f"Question: {query}."
            )
        else:
            detail = (
                "Literature index unavailable; using the conservative fallback "
                f"check: {query}."
            )

        checks.append(
            PhysicsCheck(
                name=query[:70],
                status=status,
                detail=detail,
                citation=citation,
            )
        )

    if "cf4o2" in chemistry_id.lower():
        checks[0] = checks[0].model_copy(
            update={"name": "CF4/O2 chemistry consistency", "detail": checks[0].detail}
        )
    return checks[:4]


def _rubric_results(result: PlasmaResult) -> list[RubricResult]:
    return check_physics(result, load_rubric(rubric_path()))


def failed_fixed_checks(result: PlasmaResult) -> list[RubricResult]:
    """Fixed rubric items that fail; the flow never lets the Professor approve these."""
    return [item for item in _rubric_results(result) if item.status == "fail"]


def enforce_fixed_rubric(review: ProfessorReview, result: PlasmaResult) -> ProfessorReview:
    """Downgrade an approve verdict to revise when any fixed rubric check fails."""
    if review.verdict != "approve":
        return review
    failed = failed_fixed_checks(result)
    if not failed:
        return review
    known = {item.item_id for item in review.rubric_results}
    feedback = list(review.feedback) + [
        f"Fixed rubric check '{item.item_id}' failed: got {item.value}, expected "
        f"{item.expected}. Approval overridden to revise."
        for item in failed
    ]
    return review.model_copy(
        update={
            "verdict": "revise",
            "feedback": feedback,
            "rubric_results": list(review.rubric_results)
            + [item for item in failed if item.item_id not in known],
        }
    )


def prepare_professor_evidence(
    plasma_result: PlasmaResult,
    round_number: int = 1,
) -> dict[str, Any]:
    """Evaluate the fixed rubric and collect evidence for ProfessorReview."""
    # No callable parameters: ADK builds a JSON schema from this signature.
    chemistry_id = plasma_result.diagnostics.chemistry_id
    rubric_results = _rubric_results(plasma_result)
    physics_checks = derive_case_checks(chemistry_id, search_fn=safe_search_literature)
    failed = [item.item_id for item in rubric_results if item.status == "fail"]
    return {
        "round": round_number,
        "rubric_results": [item.model_dump(mode="json") for item in rubric_results],
        "physics_checks": [item.model_dump(mode="json") for item in physics_checks],
        "failed_fixed_checks": failed,
        "note": (
            "Physics checks are evidence; the Professor still sets the final verdict "
            "and actionable feedback."
        ),
    }


def validate_professor_review(review: ProfessorReview, expected_round: int) -> None:
    """Reject contract violations that would hide review progress."""
    if review.round != expected_round:
        msg = f"review round {review.round} does not match execution round {expected_round}"
        raise ValueError(msg)
    if not review.feedback and review.verdict == "revise":
        msg = "a revise verdict needs specific feedback"
        raise ValueError(msg)
