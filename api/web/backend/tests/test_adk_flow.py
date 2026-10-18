"""Tests for the ADK RunFlow adapter: factory dispatch + report parsing."""

from __future__ import annotations

import pytest

from agents.contracts import FinalReport

from ..adk_flow import _final_report_from, _parse_final_report
from ..mock_flow import MockResearchFlow, build_flow
from ..settings import WebSettings
from ..store import RunStore


def test_build_flow_dispatches_to_mock_by_default() -> None:
    flow = build_flow(RunStore(), WebSettings())
    assert isinstance(flow, MockResearchFlow)


def test_build_flow_constructs_adk_backend_offline() -> None:
    from ..adk_flow import AdkResearchFlow

    settings = WebSettings(flow_backend="adk")
    flow = build_flow(RunStore(), settings)
    assert isinstance(flow, AdkResearchFlow)
    assert flow.settings is settings


def test_build_flow_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unknown flow backend"):
        build_flow(RunStore(), WebSettings(flow_backend="quantum"))


def test_parse_final_report_accepts_plain_and_wrapped_json() -> None:
    report = FinalReport(case_id="c1", summary="s", sign_off="pending")
    parsed = _parse_final_report(report.model_dump_json())
    assert parsed.sign_off == "pending"
    wrapped = f"Final answer:\n```json\n{report.model_dump_json()}\n```"
    assert _parse_final_report(wrapped).case_id == "c1"


def test_parse_final_report_raises_without_payload() -> None:
    with pytest.raises(ValueError, match="without a parseable FinalReport"):
        _parse_final_report(None)


def test_final_report_prefers_workflow_output_over_trailing_text() -> None:
    # Cloud Run regression: the Workflow's FinalReport arrives as event.output
    # with no text, so the last *text* was the Professor's review JSON.
    report = FinalReport(case_id="c1", summary="s", sign_off="escalated")
    review_text = '{"verdict": "revise", "round": 3, "feedback": []}'
    assert _final_report_from(report.model_dump(mode="json"), review_text) == report
    assert _final_report_from(report, review_text) == report
    assert _final_report_from(None, report.model_dump_json()) == report
