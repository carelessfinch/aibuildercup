"""FastAPI backend for the literature RAG: search endpoints plus ADK agents (Gemini) that answer with citations.

Run locally:   uvicorn app.main:app --port 8080      (interactive API docs at /docs)
"""
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from .auth import (
    DUMMY_HASH,
    auth_secret_from_env,
    issue_token,
    verify_password,
    verify_token,
)
from .config import Settings
from .index_store import load_index, prepare_index
from .ratelimit import SlidingWindow, client_ip

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rag-api")

APP_NAME = "litrag"
AgentName = Literal["literature_assistant", "professor_reviewer"]


# ---------- request / response shapes (these drive the OpenAPI docs the frontend builds against) ----------

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, examples=["electron temperature in a low-pressure ICP"])
    top_k: int = Field(5, ge=1, le=10)
    source_ids: list[str] | None = Field(None, description="Restrict to these source ids (see GET /v1/sources)")
    kind: Literal["textbook", "paper", "vendor_model"] | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["Why is Te nearly independent of power in a global model?"])
    agent: AgentName = "literature_assistant"
    session_id: str | None = Field(None, description="Omit to start a new conversation; send the returned one back to continue it")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    token: str
    username: str
    expires_at: int


class Citation(BaseModel):
    citation: str
    source_id: str
    pdf_pages: list[int]
    section: str | None = None
    snippet: str = ""


class ToolCall(BaseModel):
    name: str
    args: dict


class ChatResponse(BaseModel):
    session_id: str
    agent: str
    answer: str
    citations: list[Citation]
    tool_calls: list[ToolCall]
    model: str
    elapsed_s: float


# ---------- helpers ----------

def _citations_from(name: str, response: dict, args: dict) -> list[dict]:
    if not isinstance(response, dict) or response.get("status") != "success":
        return []
    if name == "search_literature":
        return [{"citation": r["citation"], "source_id": r["source_id"], "pdf_pages": list(r["pdf_pages"]),
                 "section": r.get("section"), "snippet": r["text"][:300]} for r in response.get("results", [])]
    if name == "read_source_pages" and response.get("pages"):
        pages = response["pages"]
        return [{"citation": response["citation"], "source_id": args.get("source_id", ""),
                 "pdf_pages": [pages[0]["pdf_page"], pages[-1]["pdf_page"]], "section": pages[0].get("section"),
                 "snippet": pages[0]["text"][:300]}]
    return []


def _text_of(event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(p.text for p in event.content.parts if p.text and not getattr(p, "thought", False))


class Turn:
    """Accumulates what one agent turn produced, from the ADK event stream."""

    def __init__(self):
        self.answer, self.citations, self.tool_calls, self._seen, self._args = "", [], [], set(), {}

    def add(self, event) -> list[tuple[str, dict]]:
        """Returns the stream events (type, payload) this ADK event produces for the frontend."""
        out = []
        calls = [] if event.partial else event.get_function_calls()
        for fc in calls:
            call = {"name": fc.name, "args": dict(fc.args or {})}
            self.tool_calls.append(call)
            self._args[fc.id] = call["args"]
            out.append(("tool_call", call))
        for fr in event.get_function_responses():
            new = []
            for c in _citations_from(fr.name, fr.response, self._args.get(fr.id, {})):
                key = (c["source_id"], tuple(c["pdf_pages"]), c["citation"])
                if key not in self._seen:
                    self._seen.add(key)
                    self.citations.append(c)
                    new.append(c)
            out.append(("tool_result", {"name": fr.name, "status": (fr.response or {}).get("status"), "citations": new}))
        text = _text_of(event)
        if text:
            if event.partial:
                out.append(("text", {"delta": text}))
            elif event.is_final_response():
                self.answer = text
        return out


# ---------- app ----------

def create_app(model=None, index_dir=None, settings: Settings | None = None) -> FastAPI:
    """Create an app; `model`, `index_dir`, and `settings` make focused tests deterministic."""
    settings = settings or Settings.from_env()
    state = {}
    auth_secret = auth_secret_from_env()
    auth_enabled = auth_secret is not None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from .agents import (
            build_agents,  # imported here so litrag sees LITRAG_INDEX_DIR first
        )

        idx_dir = index_dir or prepare_index(settings.index_uri, settings.local_index_dir)
        state["index"] = load_index(idx_dir)
        state["sessions"] = InMemorySessionService()
        state["model_name"] = model if isinstance(model, str) else (getattr(model, "model", None) or settings.gemini_model)
        agents = build_agents(model or settings.gemini_model)
        state["runners"] = {name: Runner(app_name=APP_NAME, agent=a, session_service=state["sessions"])
                            for name, a in agents.items()}
        log.info("ready: agents=%s model=%s", list(agents), state["model_name"])
        yield

    app = FastAPI(title="Plasma literature RAG API", version="1.0.0", lifespan=lifespan,
                  description="Search the group's plasma and etching literature, and talk to ADK agents (Gemini) "
                              "that answer with citations.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    chat_ip = SlidingWindow(settings.chat_per_minute_per_ip, 60)
    chat_day = SlidingWindow(settings.chat_per_day_total, 86_400)
    search_ip = SlidingWindow(settings.search_per_minute_per_ip, 60)
    login_ip = SlidingWindow(settings.login_per_minute_per_ip, 60)

    def authenticate(request: Request) -> dict | None:
        """Return the token identity, or None only when auth is explicitly off."""
        if not auth_enabled:
            return None
        service_key = request.headers.get("x-service-key", "")
        if settings.service_key and secrets.compare_digest(
                service_key.encode("utf-8"), settings.service_key.encode("utf-8")):
            return {"sub": "service:research-api"}
        bearer = request.headers.get("authorization", "")
        if bearer.startswith("Bearer "):
            claims = verify_token(bearer[7:], auth_secret)  # type: ignore[arg-type]
            if claims:
                return claims
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})

    def current_user(claims: dict | None = Depends(authenticate)) -> str:  # noqa: B008
        return claims["sub"] if claims else "anonymous"

    def _demo_users() -> dict[str, str]:
        try:
            users = json.loads(settings.demo_users)
            return users if isinstance(users, dict) else {}
        except json.JSONDecodeError:
            log.exception("DEMO_USERS is not valid JSON")
            return {}

    def limit_search(request: Request):
        if not search_ip.allow(client_ip(request)):
            raise HTTPException(429, "too many searches, try again in a minute")

    def limit_chat(request: Request):
        if not chat_ip.allow(client_ip(request)):
            raise HTTPException(429, "too many messages, try again in a minute")
        if not chat_day.allow("all"):
            raise HTTPException(429, "the demo's daily message limit is reached, try again tomorrow")

    v1 = [Depends(authenticate)]

    # Cloud Run reserves paths ending in "z" (/healthz 404s at its front end), so /health serves the same check.
    @app.get("/health", tags=["ops"])
    @app.get("/healthz", tags=["ops"], include_in_schema=False)
    def healthz():
        idx = state.get("index")
        return {"status": "ok" if idx else "starting", "passages": len(idx.chunks) if idx else 0,
                "search_mode": idx.mode if idx else None, "dense_error": idx.dense_error if idx else None,
                "model": state.get("model_name")}

    @app.post("/v1/auth/login", response_model=LoginResponse, tags=["auth"])
    def login(req: LoginRequest, request: Request):
        """Exchange demo credentials for a token accepted by rag-api and research-api."""
        if not auth_enabled or not settings.demo_users or not login_ip.allow(client_ip(request)):
            if auth_enabled and settings.demo_users:
                raise HTTPException(429, "too many login attempts, try again in a minute")
            raise HTTPException(503, "authentication is not configured")
        users = _demo_users()
        encoded = users.get(req.username)
        if not verify_password(req.password, encoded or DUMMY_HASH):
            raise HTTPException(401, "Invalid username or password")
        token, claims = issue_token(req.username, auth_secret)  # type: ignore[arg-type]
        return LoginResponse(token=token, username=req.username, expires_at=claims["exp"])

    @app.get("/v1/auth/me", dependencies=v1, tags=["auth"])
    def me(username: str = Depends(current_user)):
        return {"username": username}

    @app.get("/v1/agents", dependencies=v1, tags=["agents"])
    def list_agents():
        from .agents import AGENT_DESCRIPTIONS
        return {"model": state["model_name"], "agents": [{"name": k, "description": v} for k, v in AGENT_DESCRIPTIONS.items()]}

    @app.get("/v1/sources", dependencies=v1, tags=["literature"])
    def sources():
        from litrag.tools import list_literature_sources
        return list_literature_sources()

    @app.post("/v1/search", dependencies=v1 + [Depends(limit_search)], tags=["literature"])
    def search(req: SearchRequest):
        """Direct hybrid search (no LLM): fast, free, good for a search box or a sources panel."""
        from litrag.tools import search_literature
        res = search_literature(req.query, req.top_k, req.source_ids, req.kind)
        if res["status"] != "success":
            raise HTTPException(400, res.get("error_message"))
        return res

    @app.get("/v1/sources/{source_id}/pages", dependencies=v1 + [Depends(limit_search)], tags=["literature"])
    def pages(source_id: str, first: int = Query(..., ge=1), last: int | None = Query(None, ge=1)):
        """Full text of up to 4 PDF pages, e.g. to open a citation."""
        from litrag.tools import read_source_pages
        res = read_source_pages(source_id, first, last)
        if res["status"] != "success":
            raise HTTPException(404, res.get("error_message"))
        return res

    async def _session(req: ChatRequest, user_id: str):
        svc = state["sessions"]
        if req.session_id:
            s = await svc.get_session(app_name=APP_NAME, user_id=user_id, session_id=req.session_id)
            if s:
                return s
        return await svc.create_session(app_name=APP_NAME, user_id=user_id,
                                        session_id=req.session_id or uuid.uuid4().hex)

    def _check_message(req: ChatRequest):
        if len(req.message) > settings.max_message_chars:
            raise HTTPException(413, f"message longer than {settings.max_message_chars} characters")

    @app.post("/v1/chat", response_model=ChatResponse, dependencies=v1 + [Depends(limit_chat)], tags=["agents"])
    async def chat(req: ChatRequest, user_id: str = Depends(current_user)):
        """One agent turn; returns when the answer is complete."""
        _check_message(req)
        t0 = time.time()
        session = await _session(req, user_id)
        turn = Turn()
        msg = types.Content(role="user", parts=[types.Part(text=req.message)])
        try:
            async for event in state["runners"][req.agent].run_async(user_id=user_id, session_id=session.id, new_message=msg):
                turn.add(event)
        except Exception as exc:
            log.exception("agent run failed")
            raise HTTPException(502, f"agent error: {type(exc).__name__}: {str(exc)[:300]}")
        return ChatResponse(session_id=session.id, agent=req.agent, answer=turn.answer, citations=turn.citations,
                            tool_calls=turn.tool_calls, model=state["model_name"], elapsed_s=round(time.time() - t0, 2))

    @app.post("/v1/chat/stream", dependencies=v1 + [Depends(limit_chat)], tags=["agents"])
    async def chat_stream(req: ChatRequest, user_id: str = Depends(current_user)):
        """Same as /v1/chat, streamed as Server-Sent Events: `session`, `tool_call`, `tool_result`, `text`
        (answer deltas), then `done` (full answer + citations) or `error`."""
        _check_message(req)
        session = await _session(req, user_id)
        msg = types.Content(role="user", parts=[types.Part(text=req.message)])

        def sse(kind, data):
            return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        async def gen():
            t0 = time.time()
            turn = Turn()
            yield sse("session", {"session_id": session.id, "agent": req.agent, "model": state["model_name"]})
            try:
                async for event in state["runners"][req.agent].run_async(
                        user_id=user_id, session_id=session.id, new_message=msg,
                        run_config=RunConfig(streaming_mode=StreamingMode.SSE)):
                    for kind, data in turn.add(event):
                        yield sse(kind, data)
            except Exception as exc:
                log.exception("agent run failed")
                yield sse("error", {"message": f"{type(exc).__name__}: {str(exc)[:300]}"})
                return
            yield sse("done", {"session_id": session.id, "answer": turn.answer, "citations": turn.citations,
                               "tool_calls": turn.tool_calls, "elapsed_s": round(time.time() - t0, 2)})

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/v1/sessions/{session_id}", dependencies=v1, tags=["agents"])
    async def get_session(session_id: str, user_id: str = Depends(current_user)):
        """The conversation so far (user messages and agent answers), e.g. to restore a chat after a page reload."""
        s = await state["sessions"].get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        if not s:
            raise HTTPException(404, "session not found (sessions live in memory and are lost when the service restarts)")
        messages = []
        for e in s.events:
            text = _text_of(e)
            if text and not e.partial:
                messages.append({"role": "user" if e.author == "user" else "agent", "author": e.author,
                                 "text": text, "timestamp": e.timestamp})
        return {"session_id": s.id, "messages": messages}

    @app.delete("/v1/sessions/{session_id}", dependencies=v1, tags=["agents"])
    async def delete_session(session_id: str, user_id: str = Depends(current_user)):
        await state["sessions"].delete_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        return {"deleted": session_id}

    return app


app = create_app()
