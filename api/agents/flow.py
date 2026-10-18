"""Google ADK 2.11 graph and coordinator flows over the frozen role contracts."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.events import Event
from google.adk.workflow import START, FunctionNode, Node, Workflow
from google.genai import types
from pydantic import ConfigDict

from agents.config import AgentRuntimeConfig, load_config
from agents.contracts import (
    FinalReport,
    FourMMetadata,
    PlasmaResult,
    ProfessorReview,
    SimulationPlan,
)
from agents.phd_etch import build_phd_etch
from agents.phd_plasma import build_phd_plasma
from agents.postdoc import build_postdoc
from agents.postdoc_tools import build_simulation_plan, evaluate_plan_calibration
from agents.professor import build_professor
from agents.professor_tools import enforce_fixed_rubric, validate_professor_review
from agents.solver_tools import run_plasma_sweep

logger = logging.getLogger(__name__)
FALLBACK_NOTE = "Postdoc fallback plan used"
SOLVER_FALLBACK_NOTE = "PhD fallback solver run used"


class ReviewLoopNode(Node):
    """The bounded Postdoc -> PhD -> Professor revision cycle inside a Workflow."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    postdoc: LlmAgent
    phd_plasma: LlmAgent
    phd_etch: LlmAgent | None = None
    professor: LlmAgent
    max_rounds: int
    fault_injector: Callable[[PlasmaResult], PlasmaResult] | None = None
    # Live Gemini planning took 5+ minutes and sometimes returned nothing;
    # past this budget the deterministic plan is used instead.
    plan_timeout_s: float = 90.0
    # Same for the PhD, whose only job is run_plasma_sweep(plan): live calls
    # passed it an empty bias sweep and crashed the run.
    solve_timeout_s: float = 120.0
    # The Professor has no fallback; retry its call when Vertex returns 429
    # (gemini-3.8-flash runs on shared global capacity).
    professor_retries: int = 2
    retry_backoff_s: float = 20.0

    output_schema: type[FinalReport] | None = FinalReport
    rerun_on_resume: bool = True

    async def _invoke_role(
        self, ctx: Any, agent: LlmAgent, input_data: Any, round_no: int, attempt: int = 0
    ) -> Any:
        suffix = f"-retry-{attempt}" if attempt else ""
        return await ctx.run_node(
            agent,
            _jsonable(input_data),
            run_id=f"{agent.name}-round-{round_no}{suffix}",
        )

    async def _review_with_retry(self, ctx: Any, review_input: Any, round_no: int) -> Any:
        """Call the Professor, retrying only on Vertex rate limiting."""
        for attempt in range(self.professor_retries + 1):
            try:
                return await self._invoke_role(
                    ctx, self.professor, review_input, round_no, attempt
                )
            except Exception as exc:
                if attempt >= self.professor_retries or not _is_rate_limited(exc):
                    raise
                delay = self.retry_backoff_s * (attempt + 1)
                logger.warning(
                    "Professor rate-limited in round %d; retry %d in %.0fs",
                    round_no,
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(delay)
        msg = "unreachable: retry loop always returns or raises"
        raise AssertionError(msg)

    async def _plan_or_fallback(
        self, ctx: Any, input_data: Any, round_no: int, fallback: SimulationPlan
    ) -> tuple[SimulationPlan, str | None]:
        """Ask the Postdoc for a plan; on timeout or bad output use ``fallback``."""
        try:
            output = await asyncio.wait_for(
                self._invoke_role(ctx, self.postdoc, input_data, round_no),
                timeout=self.plan_timeout_s,
            )
            return SimulationPlan.model_validate(_plan_dict(output)), None
        except Exception as exc:  # timeout, empty reply, or schema mismatch
            reason = type(exc).__name__
            logger.warning("%s in round %d (%s)", FALLBACK_NOTE, round_no, reason)
            ctx.state.setdefault("postdoc_fallback_rounds", []).append(round_no)
            kept = "deterministic 4M plan" if round_no == 1 else "previous plan kept"
            return fallback, f"{FALLBACK_NOTE} (round {round_no}: {kept}; {reason})."

    async def _solve_or_fallback(
        self, ctx: Any, plan: SimulationPlan, round_no: int
    ) -> tuple[PlasmaResult, str | None]:
        """Ask the PhD to run the sweep; on timeout or bad output run it directly."""
        try:
            output = await asyncio.wait_for(
                self._invoke_role(ctx, self.phd_plasma, plan, round_no),
                timeout=self.solve_timeout_s,
            )
            return PlasmaResult.model_validate(output), None
        except Exception as exc:  # timeout, failed tool call, or schema mismatch
            reason = type(exc).__name__
            logger.warning("%s in round %d (%s)", SOLVER_FALLBACK_NOTE, round_no, reason)
            ctx.state.setdefault("phd_fallback_rounds", []).append(round_no)
            result = await asyncio.to_thread(run_plasma_sweep, plan)
            return result, f"{SOLVER_FALLBACK_NOTE} (round {round_no}; {reason})."

    def _note_event(self, text: str, author: str | None = None) -> Event:
        return Event(
            author=author or self.postdoc.name,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
        )

    async def run_node_impl(
        self, *, ctx: Any, node_input: Any
    ) -> AsyncGenerator[Event | FinalReport]:
        # ADK 2.11 drives this with `async for`, so it must be a generator.
        metadata = FourMMetadata.model_validate(ctx.state["fourm_input"])
        reviews: list[ProfessorReview] = []
        feedback: list[str] = []
        if isinstance(node_input, SimulationPlan) or (
            isinstance(node_input, dict) and "solver" in node_input
        ):
            plan = SimulationPlan.model_validate(_plan_dict(node_input))
        else:
            include_etch = self.phd_etch is not None
            plan, note = await self._plan_or_fallback(
                ctx,
                metadata,
                1,
                build_simulation_plan(metadata, include_etch=include_etch),
            )
            if note:
                yield self._note_event(note)

        for round_no in range(1, self.max_rounds + 1):
            if round_no > 1:
                revision_input = {
                    "four_m": metadata.model_dump(mode="json"),
                    "professor_feedback": feedback,
                    "previous_plan": plan.model_dump(mode="json"),
                }
                plan, note = await self._plan_or_fallback(ctx, revision_input, round_no, plan)
                if note:
                    yield self._note_event(note)

            plasma_result, note = await self._solve_or_fallback(ctx, plan, round_no)
            if note:
                yield self._note_event(note, author=self.phd_plasma.name)
            if self.fault_injector is not None:
                plasma_result = self.fault_injector(plasma_result)
            # The web adapter reads this to draw the real sweep plots.
            ctx.state["plasma_result"] = plasma_result.model_dump(mode="json")
            calibration = evaluate_plan_calibration(plan, plasma_result)
            solver_input = {
                "plan": plan.model_dump(mode="json"),
                "plasma_result": plasma_result.model_dump(mode="json"),
            }
            if plan.solver == "viennaps_bosch":
                if self.phd_etch is None:
                    msg = "PhD-Etch is disabled; the planner must use the plasma-only model"
                    raise RuntimeError(msg)
                await self._invoke_role(ctx, self.phd_etch, solver_input, round_no)

            review_input = {
                "metadata": metadata.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "plasma_result": plasma_result.model_dump(mode="json"),
                "calibration": calibration.model_dump(mode="json"),
                "round_number": round_no,
                "previous_feedback": feedback,
            }
            review = ProfessorReview.model_validate(
                await self._review_with_retry(ctx, review_input, round_no)
            )
            review = review.model_copy(update={"round": round_no})
            validate_professor_review(review, round_no)
            review = enforce_fixed_rubric(review, plasma_result)
            reviews.append(review)

            if review.verdict == "approve":
                yield _final_report(
                    metadata, plan, reviews, "pending", calibration=calibration
                )
                return
            feedback = review.feedback

        escalation_feedback = list(feedback) + [
            f"Review cap of {self.max_rounds} reached; ESCALATED — NOT SIGNED OFF."
        ]
        final_review = reviews[-1].model_copy(
            update={"verdict": "escalate", "feedback": escalation_feedback}
        )
        reviews[-1] = final_review
        yield _final_report(
            metadata,
            plan,
            reviews,
            "escalated",
            calibration=calibration,
            open_issues=["Review cap reached; result is not signed off."],
        )


def _is_rate_limited(exc: BaseException) -> bool:
    """True if a 429 / RESOURCE_EXHAUSTED sits anywhere in the error chain."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = f"{type(current).__name__} {current}"
        if "429" in text or "RESOURCE_EXHAUSTED" in text or "ResourceExhausted" in text:
            return True
        # ADK wraps node failures in DynamicNodeFailError(.error).
        current = (
            current.__cause__
            or current.__context__
            or getattr(current, "error", None)
        )
    return False


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _plan_dict(node_input: Any) -> dict[str, Any]:
    if isinstance(node_input, SimulationPlan):
        return node_input.model_dump(mode="json")
    if isinstance(node_input, dict):
        return node_input
    msg = "review loop expected a SimulationPlan from the Postdoc"
    raise TypeError(msg)


def _final_report(
    metadata: FourMMetadata,
    plan: SimulationPlan,
    reviews: list[ProfessorReview],
    sign_off: Any,
    calibration: Any = None,
    open_issues: list[str] | None = None,
) -> FinalReport:
    return FinalReport(
        case_id=metadata.case_id,
        summary=(
            f"Completed {len(reviews)} review round(s) for {plan.solver}; "
            "human sign-off is pending."
            if sign_off == "pending"
            else f"Completed {len(reviews)} review round(s); escalated to a human."
        ),
        calibration=calibration,
        reviews=reviews,
        open_issues=open_issues or [],
        sign_off=sign_off,
    )


def build_roles(config: AgentRuntimeConfig | None = None) -> dict[str, LlmAgent]:
    """Build three demo roles, or four when flow.include_etch is enabled."""
    cfg = config or load_config()
    roles = {
        "postdoc": build_postdoc(
            cfg.agent.model, include_etch=cfg.flow.include_etch
        ),
        "phd_plasma": build_phd_plasma(cfg.agent.model),
        "professor": build_professor(cfg.agent.model),
    }
    if cfg.flow.include_etch:
        roles["phd_etch"] = build_phd_etch(cfg.agent.model)
    return roles


def build_graph_flow(
    config: AgentRuntimeConfig | None = None,
    fault_injector: Callable[[PlasmaResult], PlasmaResult] | None = None,
) -> Workflow:
    """Build the fixed ADK 2.11 Workflow with a bounded conditional review loop."""
    cfg = config or load_config()
    roles = build_roles(cfg)

    def capture_input(ctx: Any, node_input: FourMMetadata) -> FourMMetadata:
        ctx.state["fourm_input"] = node_input.model_dump(mode="json")
        return node_input

    capture_node = FunctionNode(
        func=capture_input, name="capture_input", rerun_on_resume=True
    )
    review_loop = ReviewLoopNode(
        postdoc=roles["postdoc"],
        phd_plasma=roles["phd_plasma"],
        phd_etch=roles.get("phd_etch"),
        professor=roles["professor"],
        max_rounds=cfg.review.max_rounds,
        fault_injector=fault_injector,
        name="review_loop",
        rerun_on_resume=True,
    )
    return Workflow(
        name="plasma_research_group",
        edges=[
            (START, capture_node),
            # The loop calls the Postdoc itself so planning has a time budget
            # and a deterministic fallback.
            (capture_node, review_loop),
        ],
    )


def build_coordinator_flow(config: AgentRuntimeConfig | None = None) -> LlmAgent:
    """Minimal coordinator alternative using exactly the same role contracts."""
    cfg = config or load_config()
    roles = build_roles(cfg)
    return LlmAgent(
        name="research_coordinator",
        model=cfg.agent.model,
        description="LLM-coordinated alternative to the fixed research-group graph.",
        instruction=(
            "Delegate in this order: Postdoc plans, PhD-Plasma executes"
            + (", PhD-Etch only for Bosch" if cfg.flow.include_etch else "")
            + f", Professor reviews. Do not exceed {cfg.review.max_rounds} review "
            "rounds. On the cap, "
            "mark the result ESCALATED — NOT SIGNED OFF and request a human."
        ),
        sub_agents=[
            roles["postdoc"],
            roles["phd_plasma"],
            roles["phd_etch"],
            roles["professor"],
        ]
        if cfg.flow.include_etch
        else [roles["postdoc"], roles["phd_plasma"], roles["professor"]],
        disallow_transfer_to_parent=True,
    )


def build_flow(config: AgentRuntimeConfig | None = None) -> Workflow | LlmAgent:
    """Select graph (default) or coordinator using flow.mode (D1)."""
    cfg = config or load_config()
    if cfg.flow.mode == "graph":
        return build_graph_flow(cfg)
    return build_coordinator_flow(cfg)


def build_app(config: AgentRuntimeConfig | None = None) -> App:
    """Wrap the selected root in the ADK 2.11 App container."""
    cfg = config or load_config()
    return App(name="plasma_research_group", root_agent=build_flow(cfg))
