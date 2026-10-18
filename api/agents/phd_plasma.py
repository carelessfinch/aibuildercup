"""PhD-Plasma ADK agent: one configured run per sweep/plan."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from agents.contracts import PlasmaResult
from agents.solver_tools import run_plasma_sweep

PROMPT = (Path(__file__).parent / "prompts" / "phd_plasma.md").read_text(encoding="utf-8")


def build_phd_plasma(model: str, name: str = "phd_plasma") -> LlmAgent:
    """Build the plasma executor with the frozen PlasmaResult output schema."""
    return LlmAgent(
        name=name,
        model=model,
        description="Executes a complete plasma bias sweep through simtools.",
        instruction=PROMPT,
        tools=[run_plasma_sweep],
        output_schema=PlasmaResult,
        mode="single_turn",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        include_contents="none",
    )
