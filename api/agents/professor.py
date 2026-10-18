"""Professor ADK agent and its fixed-rubric/literature tools."""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

from agents.contracts import ProfessorReview
from agents.litrag_tools import (
    safe_list_literature_sources,
    safe_read_source_pages,
    safe_search_literature,
)
from agents.postdoc_tools import cross_model_comsol_check
from agents.professor_tools import prepare_professor_evidence

PROMPT = (Path(__file__).parent / "prompts" / "professor.md").read_text(encoding="utf-8")


def build_professor(model: str, name: str = "professor") -> LlmAgent:
    """Build the reviewing role with the frozen ProfessorReview output schema."""
    return LlmAgent(
        name=name,
        model=model,
        description="Reviews simulation evidence and recommends approve, revise, or escalate.",
        instruction=PROMPT,
        tools=[
            prepare_professor_evidence,
            safe_search_literature,
            safe_read_source_pages,
            safe_list_literature_sources,
            cross_model_comsol_check,
        ],
        output_schema=ProfessorReview,
        mode="single_turn",
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        include_contents="none",
    )
