"""FastAPI app: 4M submission, live research-group stream, plots and sign-off."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask
from starlette.staticfiles import StaticFiles

from simtools.fourm import parse_form

from . import auth
from .guards import GuardDenied, RunGuards
from .mock_flow import build_flow
from .models import RunCreatedResponse, SignOffRequest
from .presets import list_presets, load_preset
from .settings import WebSettings
from .store import RunStore

PLOT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _sse_data(event: Any) -> str:
    return json.dumps(
        {
            "sequence": event.sequence,
            "event_type": event.event_type,
            "actor": event.actor,
            "message": event.message,
            "created_at": event.created_at.isoformat(),
            "data": event.data,
        },
        separators=(",", ":"),
        default=str,
    )


def _sse_timer_data(record: Any) -> str:
    return json.dumps(
        {
            "sequence": len(record.events),
            "event_type": "timer",
            "actor": "web",
            "message": "Elapsed-time update.",
            "created_at": record.submitted_at.isoformat(),
            "data": {
                "elapsed_seconds": record.elapsed_seconds,
                "status": record.status,
            },
        },
        separators=(",", ":"),
    )


async def get_settings() -> WebSettings:
    return WebSettings.load()


async def require_subject(request: Request) -> str:
    """Require a demo Bearer token when AUTH_SECRET is configured."""
    secret = request.app.state.auth_secret
    if secret is None:
        return "local-dev"
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if separator and scheme.lower() == "bearer":
        claims = auth.verify_token(token.strip(), secret)
        if claims is not None:
            return str(claims["sub"])
    raise HTTPException(status_code=401, detail="Bearer authentication required.")


def get_store(request: Request) -> RunStore:
    return request.app.state.store


def get_guards(request: Request) -> RunGuards:
    return request.app.state.guards


SettingsDependency = Annotated[WebSettings, Depends(get_settings)]
StoreDependency = Annotated[RunStore, Depends(get_store)]
GuardsDependency = Annotated[RunGuards, Depends(get_guards)]
SubjectDependency = Annotated[str, Depends(require_subject)]


def create_app(settings: WebSettings | None = None) -> FastAPI:
    settings = settings or WebSettings.load()
    app = FastAPI(
        title="Plasma Etch Research Group",
        version="0.1.0",
        openapi_url=None,
        docs_url=None,
    )
    store = RunStore()
    guards = RunGuards(settings)
    app.state.store = store
    app.state.guards = guards
    app.state.settings = settings
    app.state.auth_secret = auth.auth_secret_from_env()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(GuardDenied)
    async def handle_guard_denied(request: Request, exc: GuardDenied) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after_s)} if exc.retry_after_s else {}
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )

    @app.exception_handler(ValidationError)
    async def handle_domain_validation(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(ValueError)
    async def handle_input_validation(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "flow_backend": settings.flow_backend,
            "flow_mode": settings.flow_mode,
            "flow_include_etch": settings.flow_include_etch,
        }

    @app.get("/presets")
    async def get_presets(_subject: SubjectDependency) -> dict[str, Any]:
        return {"presets": list_presets()}

    @app.post("/runs", status_code=201, response_model=RunCreatedResponse)
    async def create_run(
        request: Request,
        response: Response,
        payload: dict[str, Any],
        settings: SettingsDependency,
        store: StoreDependency,
        guards: GuardsDependency,
        subject: SubjectDependency,
    ) -> RunCreatedResponse:
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="Request body must be a JSON object.")
        preset_id = payload.pop("preset_id", None)
        fault = None
        if preset_id is not None:
            if payload:
                raise HTTPException(
                    status_code=422,
                    detail="preset_id cannot be combined with a custom 4M payload",
                )
            try:
                preset = load_preset(str(preset_id))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Unknown demo preset.") from exc
            metadata = preset.metadata
            fault = preset.fault
        else:
            metadata = parse_form(payload)
        client_ip = _client_ip(request)
        guards.reserve(client_ip, store.active_run_count())
        record = store.create(metadata)
        if preset_id is not None:
            await store.append_event(
                record.run_id,
                event_type="demo_preset_selected",
                actor="web",
                message=f"Demo preset selected: {preset_id}.",
                data={"preset_id": preset_id, "kind": "demo"},
            )
        flow = build_flow(store, settings, fault)
        created = RunCreatedResponse(
            run_id=record.run_id,
            status=record.status,
            submitted_at=record.submitted_at,
            events_url=f"/runs/{record.run_id}/events",
            plots_url_pattern=f"/runs/{record.run_id}/plots/{{name}}",
        )
        return JSONResponse(
            status_code=201,
            content=created.model_dump(mode="json"),
            background=BackgroundTask(store.run_flow, record, flow, settings),
        )

    @app.get("/runs/{run_id}")
    async def get_run(
        run_id: str, store: StoreDependency, _subject: SubjectDependency
    ) -> dict[str, Any]:
        record = _require(store, run_id)
        return {
            "run_id": record.run_id,
            "status": record.status,
            "submitted_at": record.submitted_at,
            "completed_at": record.completed_at,
            "elapsed_seconds": record.elapsed_seconds,
            "events": record.events,
            "plots": [f"/runs/{run_id}/plots/{name}" for name in record.plots],
            "final_payload": record.final_payload,
        }

    @app.get("/runs/{run_id}/events")
    async def stream_run_events(
        run_id: str, store: StoreDependency, _subject: SubjectDependency, replay: bool = False
    ) -> EventSourceResponse:
        _require(store, run_id)

        async def event_stream():
            after = 0
            last_timer_tick = 0.0
            while True:
                current = store.require(run_id)
                events = current.events[after:]
                for event in events:
                    yield {
                        "event": event.event_type,
                        "data": _sse_data(event),
                    }
                    after = event.sequence
                now_monotonic = time.monotonic()
                if now_monotonic - last_timer_tick >= 1:
                    yield {"event": "timer", "data": _sse_timer_data(current)}
                    last_timer_tick = now_monotonic
                if current.status in {"signed_off", "escalated", "failed"}:
                    break
                await asyncio.sleep(0.08)

        async def replay_stream():
            for event in store.require(run_id).events:
                yield {
                    "event": event.event_type,
                    "data": _sse_data(event),
                }

        return EventSourceResponse(replay_stream() if replay else event_stream())

    @app.get("/runs/{run_id}/plots/{name}")
    async def get_plot(
        run_id: str, name: str, store: StoreDependency, _subject: SubjectDependency
    ) -> Response:
        _require(store, run_id)
        if not PLOT_NAME.fullmatch(name):
            raise HTTPException(status_code=400, detail="Invalid plot name.")
        artifact = store.require(run_id).plots.get(name)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Plot is not ready yet.")
        return Response(
            content=artifact.content,
            media_type=artifact.content_type,
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/runs/{run_id}/signoff")
    async def sign_off(
        run_id: str,
        request: SignOffRequest | None,
        store: StoreDependency,
        subject: SubjectDependency,
    ) -> dict[str, Any]:
        record = _require(store, run_id)
        if record.status != "awaiting_signoff":
            raise HTTPException(
                status_code=409,
                detail="Sign-off is available only after the Professor recommends approval.",
            )
        store.update_status(run_id, "signed_off", completed=True)
        report = record.final_payload.get("report")
        if isinstance(report, dict):
            record.final_payload["report"] = {
                **report,
                "sign_off": "signed_off",
                "signed_off_by": subject,
            }
        await store.append_event(
            run_id,
            event_type="signed_off",
            actor="Human",
            message=f"Result signed off by {subject}.",
            data={"reviewer": subject},
        )
        return {
            "run_id": run_id,
            "status": "signed_off",
            "signed_off_by": subject,
            "elapsed_seconds": record.elapsed_seconds,
        }

    return app


def _mount_frontend(app: FastAPI) -> None:
    if os.environ.get("RESEARCH_API_CONTAINER") == "1":
        return
    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")


def _require(store: RunStore, run_id: str):
    try:
        return store.require(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


app = create_app()
_mount_frontend(app)
