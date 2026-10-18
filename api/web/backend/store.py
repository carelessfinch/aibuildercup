"""In-memory run state and an explicit adapter seam for the real ADK flow."""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from agents.contracts import FourMMetadata

from .models import RunStatus
from .settings import WebSettings


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class RunEvent:
    sequence: int
    event_type: str
    actor: str
    message: str
    created_at: datetime
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PlotArtifact:
    filename: str
    content_type: str
    content: bytes


@dataclass
class RunRecord:
    run_id: str
    metadata: FourMMetadata
    status: RunStatus
    submitted_at: datetime
    completed_at: datetime | None = None
    events: list[RunEvent] = field(default_factory=list)
    plots: dict[str, PlotArtifact] = field(default_factory=dict)
    final_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status in {"queued", "running"}

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at or utcnow()
        return max(0.0, (end - self.submitted_at).total_seconds())


class EventSink(Protocol):
    run_id: str

    async def emit(
        self, event_type: str, actor: str, message: str, data: dict[str, Any] | None = None
    ) -> None: ...

    async def add_plot(self, filename: str, content_type: str, content: bytes) -> str: ...


class RunFlow(Protocol):
    """The only seam W3's ADK graph/coordinator has to implement."""

    async def execute(self, metadata: FourMMetadata, sink: EventSink) -> dict[str, Any]: ...


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = threading.Lock()

    def create(self, metadata: FourMMetadata) -> RunRecord:
        run_id = uuid.uuid4().hex
        record = RunRecord(
            run_id=run_id,
            metadata=metadata,
            status="queued",
            submitted_at=utcnow(),
        )
        self.append_event_sync(
            record,
            event_type="run_received",
            actor="web",
            message="4M metadata received; research group is being convened.",
            data={"case_id": metadata.case_id, "question": metadata.question},
        )
        with self._lock:
            self._runs[run_id] = record
        return record

    def attach_flow(self, record: RunRecord, flow: RunFlow, settings: WebSettings) -> None:
        """Start the flow. Production replaces the factory, not this store."""

        task = asyncio.create_task(
            self.run_flow(record, flow, settings),
            name=f"research-flow-{record.run_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def run_flow(self, record: RunRecord, flow: RunFlow, settings: WebSettings) -> None:
        sink = StoreEventSink(record.run_id, self)
        try:
            self.update_status(record.run_id, "running")
            payload = await flow.execute(record.metadata, sink)
            self.set_final_payload(record.run_id, payload)
            report = payload.get("report")
            if isinstance(report, dict) and report.get("sign_off") == "pending":
                self.update_status(record.run_id, "awaiting_signoff")
            elif isinstance(report, dict) and report.get("sign_off") == "escalated":
                self.update_status(record.run_id, "escalated", completed=True)
            else:
                self.update_status(record.run_id, "signed_off", completed=True)
        except Exception as exc:
            self.update_status(record.run_id, "failed", completed=True)
            await sink.emit(
                "run_failed",
                "web",
                "The run stopped because of an internal error.",
                {"error": str(exc)},
            )

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def require(self, run_id: str) -> RunRecord:
        record = self._runs.get(run_id)
        if record is None:
            raise KeyError(run_id)
        return record

    def append_event_sync(
        self,
        record: RunRecord,
        *,
        event_type: str,
        actor: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> RunEvent:
        with self._lock:
            event = RunEvent(
                sequence=len(record.events) + 1,
                event_type=event_type,
                actor=actor,
                message=message,
                created_at=utcnow(),
                data=data or {},
            )
            record.events.append(event)
        return event

    async def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        actor: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> RunEvent:
        record = self.require(run_id)
        event = self.append_event_sync(
            record, event_type=event_type, actor=actor, message=message, data=data
        )
        await asyncio.sleep(0)
        return event

    def update_status(
        self, run_id: str, status: RunStatus, *, completed: bool = False
    ) -> None:
        record = self.require(run_id)
        record.status = status
        if completed and record.completed_at is None:
            record.completed_at = utcnow()

    def set_final_payload(self, run_id: str, payload: dict[str, Any]) -> None:
        self.require(run_id).final_payload = payload

    def add_plot(self, run_id: str, filename: str, content_type: str, content: bytes) -> str:
        record = self.require(run_id)
        record.plots[filename] = PlotArtifact(filename, content_type, content)
        return f"/runs/{run_id}/plots/{filename}"

    def active_run_count(self) -> int:
        return sum(record.is_active for record in self._runs.values())


class StoreEventSink:
    def __init__(self, run_id: str, store: RunStore):
        self.run_id = run_id
        self.store = store

    async def emit(
        self, event_type: str, actor: str, message: str, data: dict[str, Any] | None = None
    ) -> None:
        await self.store.append_event(
            self.run_id, event_type=event_type, actor=actor, message=message, data=data or {}
        )

    async def add_plot(self, filename: str, content_type: str, content: bytes) -> str:
        return self.store.add_plot(self.run_id, filename, content_type, content)
