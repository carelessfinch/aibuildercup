"""RunFlow adapter that drives the real ADK research-group flow (W3 seam).

Same ``execute(metadata, sink) -> {"report", "plots"}`` contract as the mock,
so the web store never knows which backend produced a run. The mock stays the
default for offline tests; ``WEB_FLOW_BACKEND=adk`` (or ``web.flow_backend``
in configs/base.yaml) selects this adapter in deployment.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agents.config import AgentRuntimeConfig, load_config
from agents.contracts import FinalReport, FourMMetadata, PlasmaPoint, PlasmaResult
from agents.flow import build_coordinator_flow, build_graph_flow

from .plots import create_demo_plots
from .presets import apply_plasma_fault
from .settings import WebSettings
from .store import EventSink, RunStore

APP_NAME = "plasma_research_group"
USER_ID = "web-user"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class AdkResearchFlow:
    """Drive the ADK Workflow (or coordinator) and translate events for the UI."""

    def __init__(
        self,
        store: RunStore,
        settings: WebSettings,
        fault_spec: dict[str, Any] | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.fault_spec = fault_spec

    async def execute(self, metadata: FourMMetadata, sink: EventSink) -> dict[str, Any]:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        await sink.emit(
            "flow_started",
            "web",
            "ADK research-group flow started.",
            {"backend": "adk", "flow_mode": self.settings.flow_mode},
        )
        cfg = self._config()
        if self.settings.flow_mode == "coordinator":
            flow = build_coordinator_flow(cfg)
        else:
            fault_spec = self.fault_spec

            def injector(result: PlasmaResult) -> PlasmaResult:
                return (
                    apply_plasma_fault(result, fault_spec)
                    if fault_spec is not None
                    else result
                )

            flow = build_graph_flow(cfg, injector)
        session_service = InMemorySessionService()
        runner = Runner(app_name=APP_NAME, agent=flow, session_service=session_service)
        session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
        content = types.Content(
            role="user", parts=[types.Part(text=metadata.model_dump_json())]
        )

        final_text: str | None = None
        final_output: Any = None
        async for event in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=content
        ):
            author = _display_actor(getattr(event, "author", None) or "agent")
            text = _event_text(event)
            if text:
                await sink.emit("agent_message", author, text[:2000])
            if getattr(event, "is_final_response", False) and text:
                final_text = text
            # Workflow nodes put the FinalReport in event.output with no text.
            output = getattr(event, "output", None)
            if isinstance(output, FinalReport) or (
                isinstance(output, dict) and "sign_off" in output
            ):
                final_output = output

        report = _final_report_from(final_output, final_text)
        points = await self._session_points(session_service, session.id)
        plot_urls: list[str] = []
        if points:
            for filename, (content_type, payload) in create_demo_plots(points).items():
                await sink.add_plot(filename, content_type, payload)
                plot_urls.append(f"/runs/{sink.run_id}/plots/{filename}")

        approved = report.sign_off == "pending"
        await sink.emit(
            "awaiting_signoff" if approved else "escalated",
            "Professor",
            "Human sign-off is required."
            if approved
            else "Review cap reached; the result is NOT signed off.",
            {"report": report.model_dump(mode="json")},
        )
        return {"report": report.model_dump(mode="json"), "plots": plot_urls}

    def _config(self) -> AgentRuntimeConfig:
        """Agent env config, reconciled with the web layer's flow settings."""
        cfg = load_config()
        updates: dict[str, Any] = {}
        flow_updates: dict[str, Any] = {}
        if self.settings.flow_mode != cfg.flow.mode:
            flow_updates["mode"] = self.settings.flow_mode
        if self.settings.flow_include_etch != cfg.flow.include_etch:
            flow_updates["include_etch"] = self.settings.flow_include_etch
        if flow_updates:
            updates["flow"] = cfg.flow.model_copy(update=flow_updates)
        if self.settings.review_max_rounds != cfg.review.max_rounds:
            updates["review"] = cfg.review.model_copy(
                update={"max_rounds": self.settings.review_max_rounds}
            )
        return cfg.model_copy(update=updates) if updates else cfg

    async def _session_points(
        self, session_service: Any, session_id: str
    ) -> list[PlasmaPoint]:
        try:
            session = await session_service.get_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=session_id
            )
            state = dict(getattr(session, "state", None) or {})
            raw = state.get("plasma_result")
            return PlasmaResult.model_validate(raw).points if raw else []
        except Exception:
            return []


def _final_report_from(final_output: Any, final_text: str | None) -> FinalReport:
    """Prefer the workflow's structured output; fall back to parsing text."""
    if final_output is not None:
        if hasattr(final_output, "model_dump"):
            final_output = final_output.model_dump(mode="json")
        return FinalReport.model_validate(final_output)
    return _parse_final_report(final_text)


def _event_text(event: Any) -> str | None:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    texts = [part.text for part in parts if getattr(part, "text", None)]
    return "\n".join(texts) if texts else None


def _display_actor(author: str) -> str:
    normalized = author.replace("_", "-").replace("-", " ").strip().lower()
    if normalized in {"phd plasma", "phd etch"}:
        return "PhD"
    if normalized == "postdoc":
        return "Postdoc"
    if normalized == "professor":
        return "Professor"
    return author


def _parse_final_report(final_text: str | None) -> FinalReport:
    if final_text:
        try:
            return FinalReport.model_validate(json.loads(final_text))
        except (ValueError, TypeError):
            match = _JSON_BLOCK.search(final_text)
            if match:
                return FinalReport.model_validate(json.loads(match.group(0)))
    msg = "The ADK flow finished without a parseable FinalReport."
    raise ValueError(msg)
