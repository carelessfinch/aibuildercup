"""Postdoc ADK agent: 4M planning, calibration, and figure assembly."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from google.genai import types

from agents.contracts import FourMMetadata, SimulationPlan
from agents.litrag_tools import safe_search_literature
from agents.postdoc_tools import (
    build_simulation_plan,
    cross_model_comsol_check,
    evaluate_plan_calibration,
)
from simtools.postproc import plot_sweep

PROMPT = (Path(__file__).parent / "prompts" / "postdoc.md").read_text(encoding="utf-8")


def build_postdoc(
    model: str, name: str = "postdoc", *, include_etch: bool = False
) -> LlmAgent:
    """Build the planning role with the frozen SimulationPlan output schema."""

    def build_demo_plan(metadata: FourMMetadata) -> SimulationPlan:
        return build_simulation_plan(metadata, include_etch=include_etch)

    return LlmAgent(
        name=name,
        model=model,
        description="Plans simulations and calibrates them against experiment data.",
        instruction=PROMPT,
        tools=[
            build_demo_plan,
            evaluate_plan_calibration,
            cross_model_comsol_check,
            plot_sweep,
            safe_search_literature,
        ],
        output_schema=SimulationPlan,
        # Planning is a single deterministic tool call; long thinking only
        # stalled live runs (5+ minutes, then an empty reply).
        generate_content_config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
        ),
        mode="single_turn",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        include_contents="none",
    )
