"""Transport models for the web API; domain contracts remain in agents/contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RunStatus = Literal[
    "queued",
    "running",
    "awaiting_signoff",
    "signed_off",
    "escalated",
    "failed",
]


class SignOffRequest(BaseModel):
    """Reserved for future sign-off metadata; identity always comes from the token."""


class RunEventResponse(BaseModel):
    sequence: int
    event_type: str
    actor: str
    message: str
    created_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)


class RunCreatedResponse(BaseModel):
    run_id: str
    status: RunStatus
    submitted_at: datetime
    events_url: str
    plots_url_pattern: str


class RunResponse(BaseModel):
    run_id: str
    status: RunStatus
    submitted_at: datetime
    completed_at: datetime | None = None
    elapsed_seconds: float
    events: list[RunEventResponse]
    plots: list[str]

