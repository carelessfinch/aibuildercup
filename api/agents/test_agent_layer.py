"""Offline ADK-layer tests: construction, wiring, tools, and bounded escalation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from google.adk.agents import LlmAgent
from google.adk.workflow import Workflow

from agents.config import AgentRuntimeConfig, load_config
from agents.contracts import (
    EtchResult,
    FinalReport,
    FourMMetadata,
    PlasmaResult,
    ProfessorReview,
    SimulationPlan,
)
from agents.flow import (
    ReviewLoopNode,
    build_app,
    build_coordinator_flow,
    build_graph_flow,
    build_roles,
)
from agents.litrag_tools import (
    HTTP_TIMEOUT_S,
    safe_list_literature_sources,
    safe_read_source_pages,
    safe_search_literature,
)
from agents.postdoc_tools import build_simulation_plan
from agents.professor_tools import derive_case_checks, enforce_fixed_rubric
from agents.solver_tools import run_plasma_sweep


def metadata() -> FourMMetadata:
    return FourMMetadata.model_validate(
        {
            "case_id": "offline_case",
            "question": "Validate the low-power CF4/O2 ICP sweep.",
            "machine": {},
            "material": {"wafer": "Si"},
            "method": {
                "recipe": {
                    "power_W": 300,
                    "pressure_mTorr": 10,
                    "flow_sccm": {"Ar": 50},
                    "bias_sweep_V": [0, 25, 50],
                }
            },
            "source": "synthetic",
        }
    )


def plan() -> SimulationPlan:
    return build_simulation_plan(metadata())


def plasma_result() -> PlasmaResult:
    return run_plasma_sweep(plan())


def config(tmp_path: Path, **values: object) -> AgentRuntimeConfig:
    base = {
        "agent": {"model": values.get("model", "gemini-3.8-flash")},
        "flow": {
            "mode": values.get("mode", "graph"),
            "include_etch": values.get("include_etch", False),
        },
        "review": {"max_rounds": values.get("rounds", "3")},
        "solver": {"backend": "local"},
        "litrag": {"index_dir": "", "embed_backend": "gemini"},
    }
    path = tmp_path / "config.yaml"
    path.write_text(json.dumps(base), encoding="utf-8")
    return load_config(path)


def test_config_has_one_model_value_and_env_overrides(tmp_path: Path) -> None:
    cfg = load_config(environ={})
    assert cfg.agent.model == "gemini-3.8-flash"
    assert cfg.flow.mode == "graph"
    assert cfg.flow.include_etch is False
    assert cfg.review.max_rounds == 3

    overridden = config(
        tmp_path,
        model="gemini-4-test",
        mode="coordinator",
        include_etch=True,
        rounds="2",
    )
    env = load_config(
        None,
        environ={
            "AGENT_MODEL": "gemini-4-test",
            "FLOW_MODE": "coordinator",
            "FLOW_INCLUDE_ETCH": "true",
            "REVIEW_MAX_ROUNDS": "2",
            "SOLVER_BACKEND": "local",
            "LITRAG_INDEX_DIR": "/tmp/private-index",
        },
    )
    assert overridden.agent.model == env.agent.model == "gemini-4-test"
    assert overridden.flow.mode == env.flow.mode == "coordinator"
    assert overridden.flow.include_etch is env.flow.include_etch is True
    assert overridden.review.max_rounds == env.review.max_rounds == 2
    assert env.litrag.index_dir == "/tmp/private-index"


def test_role_agents_use_frozen_contracts(tmp_path: Path) -> None:
    schemas = {
        "postdoc": SimulationPlan,
        "phd_plasma": PlasmaResult,
        "professor": ProfessorReview,
    }
    built = build_roles(config(tmp_path, mode="graph"))
    assert set(built) == set(schemas)
    for name, schema in schemas.items():
        agent = built[name]
        assert isinstance(agent, LlmAgent)
        assert agent.output_schema is schema
        assert agent.mode == "single_turn"
        assert agent.model == "gemini-3.8-flash"
    assert built["professor"].instruction

    four_roles = build_roles(config(tmp_path, mode="graph", include_etch=True))
    assert set(four_roles) == {*schemas, "phd_etch"}
    assert four_roles["phd_etch"].output_schema is EtchResult

def test_graph_flow_uses_verified_adk_workflow(tmp_path: Path) -> None:
    flow = build_graph_flow(config(tmp_path))
    assert isinstance(flow, Workflow)
    edges = [(edge.from_node.name, edge.to_node.name) for edge in flow.graph.edges]
    assert edges == [
        ("__START__", "capture_input"),
        ("capture_input", "review_loop"),
    ]
    loop = flow.graph.nodes[-1]
    assert isinstance(loop, ReviewLoopNode)
    assert loop.max_rounds == 3
    assert loop.output_schema is not None


def test_coordinator_uses_same_roles_and_cap_instruction(tmp_path: Path) -> None:
    coordinator = build_coordinator_flow(config(tmp_path, mode="coordinator"))
    assert isinstance(coordinator, LlmAgent)
    assert [agent.name for agent in coordinator.sub_agents] == [
        "postdoc",
        "phd_plasma",
        "professor",
    ]
    assert "Do not exceed 3 review" in coordinator.instruction
    assert "PhD-Etch" not in coordinator.instruction

    full = build_coordinator_flow(config(tmp_path, mode="coordinator", include_etch=True))
    assert [agent.name for agent in full.sub_agents] == [
        "postdoc",
        "phd_plasma",
        "phd_etch",
        "professor",
    ]
    assert "PhD-Etch only for Bosch" in full.instruction

def test_litrag_http_backend_uses_service_key_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert HTTP_TIMEOUT_S == 20.0
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/search":
            return httpx.Response(200, json={"status": "success", "results": [{"citation": "ref"}]})
        if request.url.path == "/v1/sources/ref/pages":
            return httpx.Response(200, json={"status": "success", "pages": []})
        return httpx.Response(200, json={"status": "success", "sources": []})

    def fake_client(base_url: str) -> httpx.Client:
        return httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(20.0),
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setenv("LITRAG_API_URL", "https://rag-api.example.test")
    monkeypatch.setenv("SERVICE_KEY", "service-secret")
    monkeypatch.setattr("agents.litrag_tools._new_http_client", fake_client)
    assert safe_search_literature("Bohm flux")["results"] == [{"citation": "ref"}]
    assert safe_read_source_pages("ref", 2)["status"] == "success"
    assert safe_read_source_pages("ref", 2, 4)["status"] == "success"
    assert safe_list_literature_sources()["status"] == "success"
    assert [request.method for request in requests] == ["POST", "GET", "GET", "GET"]
    assert requests[0].url.path == "/v1/search"
    assert requests[1].url.path == "/v1/sources/ref/pages"
    assert dict(requests[1].url.params) == {"first": "2"}
    assert requests[2].url.path == "/v1/sources/ref/pages"
    assert dict(requests[2].url.params) == {"first": "2", "last": "4"}
    assert requests[3].url.path == "/v1/sources"
    assert all(request.headers["X-Service-Key"] == "service-secret" for request in requests)


def test_litrag_http_backend_falls_back_structurally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "unavailable"})

    monkeypatch.setenv("LITRAG_API_URL", "https://rag-api.example.test")
    monkeypatch.delenv("SERVICE_KEY", raising=False)
    monkeypatch.setattr(
        "agents.litrag_tools._new_http_client",
        lambda base_url: httpx.Client(
            base_url=base_url,
            timeout=20.0,
            transport=httpx.MockTransport(handler),
        ),
    )
    result = safe_search_literature("Bohm flux")
    assert result["status"] == "unavailable"
    assert result["operation"] == "search_literature"
    assert result["results"] == []

def test_litrag_degrades_without_private_index() -> None:
    response = safe_search_literature("Bohm flux in a low pressure ICP")
    assert response["status"] == "unavailable"
    assert "literature index unavailable" in response["error_message"]
    checks = derive_case_checks(search_fn=safe_search_literature)
    assert 2 <= len(checks) <= 4
    assert all(check.status == "warn" for check in checks)
    assert all(check.citation is None for check in checks)


def test_plasma_tool_returns_one_contract_result_for_whole_sweep() -> None:
    result = plasma_result()
    assert [point.bias_V for point in result.points] == [0.0, 25.0, 50.0]
    assert result.diagnostics.runtime_s >= 0
    assert result.diagnostics.averaging_note is not None


def test_postdoc_uses_experiment_calibration_not_comsol() -> None:
    built_plan = plan()
    assert built_plan.chemistry_ref == "chemistry_ar_lieberman.yaml"
    assert built_plan.calibration_targets
    assert all(target.source_kind == "experiment" for target in built_plan.calibration_targets)
    assert all("COMSOL" not in target.source for target in built_plan.calibration_targets)
    assert any("COMSOL" in criterion for criterion in built_plan.acceptance_criteria_proposal)


class FakeContext:
    def __init__(self, metadata_data: dict[str, Any]) -> None:
        self.state = {"fourm_input": metadata_data}
        self.calls: list[tuple[str, str]] = []

    async def run_node(self, agent: LlmAgent, node_input: Any, *, run_id: str) -> Any:
        assert "round-" in run_id
        self.calls.append((agent.name, run_id))
        return node_input


async def _run_escalation_test(tmp_path: Path) -> None:
    cfg = config(tmp_path, rounds="2")
    loop = ReviewLoopNode(
        postdoc=build_roles(cfg)["postdoc"],
        phd_plasma=build_roles(cfg)["phd_plasma"],
        professor=build_roles(cfg)["professor"],
        max_rounds=2,
        name="review_loop",
    )
    ctx = FakeContext(metadata().model_dump(mode="json"))
    initial_plan = plan().model_dump(mode="json")
    review = ProfessorReview(
        verdict="revise",
        round=99,
        feedback=["Lower the ion energy and rerun."],
    )

    async def fake_run_node(agent: LlmAgent, node_input: Any, *, run_id: str) -> Any:
        ctx.calls.append((agent.name, run_id))
        if agent.name == "postdoc":
            return initial_plan
        if agent.name == "phd_plasma":
            return plasma_result().model_dump(mode="json")
        return review.model_dump(mode="json")

    ctx.run_node = fake_run_node  # type: ignore[method-assign]
    # Drive it the way ADK's Node._run_impl does (Cloud Run regression).
    outputs = [item async for item in loop.run_node_impl(ctx=ctx, node_input=initial_plan)]
    assert len(outputs) == 1
    report = outputs[0]
    assert isinstance(report, FinalReport)

    assert report.sign_off == "escalated"
    assert "plasma_result" in ctx.state
    assert len(report.reviews) == 2
    assert report.reviews[-1].verdict == "escalate"
    assert "ESCALATED — NOT SIGNED OFF" in report.reviews[-1].feedback[-1]
    # Round 1's Postdoc is the static graph node; round 2 uses a dynamic revision.
    assert len([name for name, _ in ctx.calls if name == "postdoc"]) == 1


def test_review_loop_escalates_at_cap_and_never_signs_off(tmp_path: Path) -> None:
    asyncio.run(_run_escalation_test(tmp_path))


def test_plan_carries_chamber_geometry_when_machine_provides_it() -> None:
    with_chamber = FourMMetadata.model_validate(
        {
            **metadata().model_dump(mode="json"),
            "machine": {
                "chamber_radius_mm": 400.0,
                "reactor_height_mm": 700.0,
            },
        }
    )
    planned = build_simulation_plan(with_chamber)
    assert planned.geometry is not None
    assert planned.geometry.radius_m == 0.4
    assert planned.geometry.height_m == 0.7

    planned_default = build_simulation_plan(metadata())
    assert planned_default.geometry is None


def test_plan_tolerates_null_recipe_fields_from_llm_tool_calls() -> None:
    # Cloud Run regression: Gemini sent "flow_sccm": null to build_demo_plan.
    nulled = FourMMetadata.model_validate(
        {
            **metadata().model_dump(mode="json"),
            "method": {
                "recipe": {
                    "power_W": None,
                    "pressure_mTorr": 10,
                    "flow_sccm": None,
                    "bias_sweep_V": None,
                }
            },
        }
    )
    planned = build_simulation_plan(nulled)
    assert planned.operating_point.flow_sccm == {}
    assert planned.operating_point.power_W == 100.0
    assert planned.operating_point.bias_sweep_V == [0.0, 25.0, 50.0, 75.0, 100.0]


def test_app_is_a_valid_adk_container(tmp_path: Path) -> None:
    app = build_app(config(tmp_path))
    assert app.name == "plasma_research_group"
    assert isinstance(app.root_agent, Workflow)


def test_bosch_request_is_plasma_only_when_etch_is_disabled() -> None:
    bosch = metadata().model_copy(
        update={"question": "Validate a Bosch SF6/C4F8 trench etch."}
    )
    bosch.method.recipe["flow_sccm"] = {"SF6": 100, "C4F8": 30}
    demo_plan = build_simulation_plan(bosch, include_etch=False)
    assert demo_plan.solver == "plasma_global_model"
    assert any(
        "out of scope for this demo" in item
        for item in demo_plan.acceptance_criteria_proposal
    )

    full_plan = build_simulation_plan(bosch, include_etch=True)
    assert full_plan.solver == "viennaps_bosch"


def test_fixed_rubric_failure_overrides_professor_approval() -> None:
    good = plasma_result()
    approve = ProfessorReview(verdict="approve", round=1)
    assert enforce_fixed_rubric(approve, good).verdict == "approve"

    raw = good.model_dump(mode="json")
    raw["points"][0]["te_eV"] = 250.0
    faulty = PlasmaResult.model_validate(raw)
    review = enforce_fixed_rubric(approve, faulty)
    assert review.verdict == "revise"
    assert any("te_range" in line for line in review.feedback)
    assert any(item.item_id == "te_range" and item.status == "fail"
               for item in review.rubric_results)


def test_every_role_tool_builds_a_function_declaration(tmp_path: Path) -> None:
    # Cloud Run regression: a Callable parameter on prepare_professor_evidence
    # made ADK's declaration builder raise PydanticInvalidForJsonSchema.
    from google.adk.tools.function_tool import FunctionTool

    roles = build_roles(config(tmp_path, mode="graph", include_etch=True))
    for role, agent in roles.items():
        for tool in agent.tools:
            wrapped = tool if hasattr(tool, "_get_declaration") else FunctionTool(tool)
            assert wrapped._get_declaration() is not None, f"{role}.{wrapped.name}"


def _fallback_loop(tmp_path: Path, **values: Any) -> ReviewLoopNode:
    cfg = config(tmp_path, rounds="1")
    roles = build_roles(cfg)
    return ReviewLoopNode(
        postdoc=roles["postdoc"],
        phd_plasma=roles["phd_plasma"],
        professor=roles["professor"],
        max_rounds=1,
        name="review_loop",
        **values,
    )


async def _run_postdoc_fallback(tmp_path: Path, postdoc_output: Any, delay_s: float) -> None:
    from google.adk.events import Event

    loop = _fallback_loop(tmp_path, plan_timeout_s=0.05)
    ctx = FakeContext(metadata().model_dump(mode="json"))
    approve = ProfessorReview(verdict="approve", round=1, feedback=[])

    async def fake_run_node(agent: LlmAgent, node_input: Any, *, run_id: str) -> Any:
        if agent.name == "postdoc":
            await asyncio.sleep(delay_s)
            return postdoc_output
        if agent.name == "phd_plasma":
            return plasma_result().model_dump(mode="json")
        return approve.model_dump(mode="json")

    ctx.run_node = fake_run_node  # type: ignore[method-assign]
    outputs = [
        item async for item in loop.run_node_impl(ctx=ctx, node_input=metadata())
    ]
    notes, report = outputs[:-1], outputs[-1]
    assert isinstance(report, FinalReport)
    assert report.sign_off == "pending"
    assert ctx.state["postdoc_fallback_rounds"] == [1]
    assert len(notes) == 1 and isinstance(notes[0], Event)
    assert notes[0].author == "postdoc"
    assert "Postdoc fallback plan used" in notes[0].content.parts[0].text


def test_review_loop_falls_back_when_postdoc_returns_nothing(tmp_path: Path) -> None:
    # Cloud Run regression: Gemini's Postdoc reply was empty after ~5 minutes.
    asyncio.run(_run_postdoc_fallback(tmp_path, None, delay_s=0))


def test_review_loop_falls_back_when_postdoc_times_out(tmp_path: Path) -> None:
    asyncio.run(_run_postdoc_fallback(tmp_path, plan().model_dump(mode="json"), delay_s=1))


def test_review_loop_uses_valid_postdoc_plan_without_note(tmp_path: Path) -> None:
    async def run() -> None:
        loop = _fallback_loop(tmp_path)
        ctx = FakeContext(metadata().model_dump(mode="json"))
        approve = ProfessorReview(verdict="approve", round=1, feedback=[])

        async def fake_run_node(agent: LlmAgent, node_input: Any, *, run_id: str) -> Any:
            if agent.name == "postdoc":
                return plan().model_dump(mode="json")
            if agent.name == "phd_plasma":
                return plasma_result().model_dump(mode="json")
            return approve.model_dump(mode="json")

        ctx.run_node = fake_run_node  # type: ignore[method-assign]
        outputs = [
            item async for item in loop.run_node_impl(ctx=ctx, node_input=metadata())
        ]
        assert len(outputs) == 1 and isinstance(outputs[0], FinalReport)
        assert "postdoc_fallback_rounds" not in ctx.state

    asyncio.run(run())


def test_review_loop_runs_solver_directly_when_phd_fails(tmp_path: Path) -> None:
    # Cloud Run regression: the PhD passed an empty bias sweep to the solver.
    async def run() -> None:
        loop = _fallback_loop(tmp_path)
        ctx = FakeContext(metadata().model_dump(mode="json"))
        approve = ProfessorReview(verdict="approve", round=1, feedback=[])

        async def fake_run_node(agent: LlmAgent, node_input: Any, *, run_id: str) -> Any:
            if agent.name == "postdoc":
                return plan().model_dump(mode="json")
            if agent.name == "phd_plasma":
                raise ValueError("sweep must contain at least one bias voltage")
            return approve.model_dump(mode="json")

        ctx.run_node = fake_run_node  # type: ignore[method-assign]
        outputs = [
            item async for item in loop.run_node_impl(ctx=ctx, node_input=metadata())
        ]
        notes, report = outputs[:-1], outputs[-1]
        assert isinstance(report, FinalReport)
        assert ctx.state["phd_fallback_rounds"] == [1]
        assert [n.author for n in notes] == ["phd_plasma"]
        assert "PhD fallback solver run used" in notes[0].content.parts[0].text
        points = ctx.state["plasma_result"]["points"]
        assert [p["bias_V"] for p in points] == [0.0, 25.0, 50.0]

    asyncio.run(run())


class _WrappedNodeError(Exception):
    """Stand-in for ADK's DynamicNodeFailError, which keeps the cause in .error."""

    def __init__(self, error: Exception) -> None:
        super().__init__("Dynamic node professor failed")
        self.error = error


def _professor_retry_loop(tmp_path: Path, failures: list[Exception]) -> tuple[
    ReviewLoopNode, FakeContext, list[str]
]:
    loop = _fallback_loop(tmp_path, retry_backoff_s=0.0)
    ctx = FakeContext(metadata().model_dump(mode="json"))
    approve = ProfessorReview(verdict="approve", round=1, feedback=[])
    professor_runs: list[str] = []

    async def fake_run_node(agent: LlmAgent, node_input: Any, *, run_id: str) -> Any:
        if agent.name == "postdoc":
            return plan().model_dump(mode="json")
        if agent.name == "phd_plasma":
            return plasma_result().model_dump(mode="json")
        professor_runs.append(run_id)
        if failures:
            raise failures.pop(0)
        return approve.model_dump(mode="json")

    ctx.run_node = fake_run_node  # type: ignore[method-assign]
    return loop, ctx, professor_runs


def test_professor_call_retries_on_vertex_429(tmp_path: Path) -> None:
    async def run() -> None:
        quota = RuntimeError("429 RESOURCE_EXHAUSTED. Resource exhausted.")
        loop, ctx, runs = _professor_retry_loop(
            tmp_path, [_WrappedNodeError(quota), _WrappedNodeError(quota)]
        )
        outputs = [
            item async for item in loop.run_node_impl(ctx=ctx, node_input=metadata())
        ]
        assert outputs[-1].sign_off == "pending"
        assert runs == [
            "professor-round-1",
            "professor-round-1-retry-1",
            "professor-round-1-retry-2",
        ]

    asyncio.run(run())


def test_professor_call_does_not_retry_other_errors(tmp_path: Path) -> None:
    async def run() -> None:
        loop, ctx, runs = _professor_retry_loop(tmp_path, [ValueError("bad review")])
        with pytest.raises(ValueError, match="bad review"):
            async for _ in loop.run_node_impl(ctx=ctx, node_input=metadata()):
                pass
        assert runs == ["professor-round-1"]

    asyncio.run(run())


def test_professor_call_gives_up_after_retry_budget(tmp_path: Path) -> None:
    async def run() -> None:
        quota = RuntimeError("429 RESOURCE_EXHAUSTED")
        loop, ctx, runs = _professor_retry_loop(tmp_path, [quota, quota, quota])
        with pytest.raises(RuntimeError, match="RESOURCE_EXHAUSTED"):
            async for _ in loop.run_node_impl(ctx=ctx, node_input=metadata()):
                pass
        assert len(runs) == 3

    asyncio.run(run())
