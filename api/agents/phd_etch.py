"""PhD-Etch ADK agent: one configured ViennaPS run per plan."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from agents.contracts import EtchResult
from agents.solver_tools import run_etch_plan

PROMPT = (Path(__file__).parent / "prompts" / "phd_etch.md").read_text(encoding="utf-8")


def build_phd_etch(model: str, name: str = "phd_etch") -> LlmAgent:
    """Build the etch executor with the frozen EtchResult output schema."""
    return LlmAgent(
        name=name,
        model=model,
        description="Executes a Bosch etch plan through simtools.",
        instruction=PROMPT,
        tools=[run_etch_plan],
        output_schema=EtchResult,
        mode="single_turn",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        include_contents="none",
    )
