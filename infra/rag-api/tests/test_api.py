"""End-to-end auth/API tests against the real litrag index, with a scripted stand-in for Gemini."""
import json
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmResponse
from google.genai import types

from app import auth

TEST_SECRET = b"test-auth-secret-for-hackathon"
TEST_SERVICE_KEY = "test-service-key"
TEST_PASSWORD = "correct-horse"
TEST_USERS = json.dumps({"demo-user": auth.hash_password(TEST_PASSWORD)})
os.environ.update(
    AUTH_SECRET="test-auth-secret-for-hackathon",
    SERVICE_KEY=TEST_SERVICE_KEY,
    DEMO_USERS=TEST_USERS,
)

from app.main import create_app

INDEX_DIR = Path(os.environ.get("TEST_INDEX_DIR", "/private/tmp/aibuildercup-litrag-index/index"))


class ScriptedLlm(BaseLlm):
    model: str = "scripted-test-model"

    async def generate_content_async(self, llm_request, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        last = llm_request.contents[-1]
        if any(p.function_response for p in last.parts):
            hits = last.parts[0].function_response.response["results"]
            answer = f"Te is set by particle balance [{hits[0]['citation']}]."
            if stream:
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=answer[:10])]), partial=True)
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=answer[10:])]), partial=True)
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=answer)]))
        else:
            call = types.FunctionCall(name="search_literature", args={"query": "electron temperature global model", "top_k": 3})
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=call)]))


def login(client: TestClient, username: str = "demo-user", password: str = TEST_PASSWORD) -> dict:
    response = client.post("/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(model=ScriptedLlm(), index_dir=INDEX_DIR)) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def headers(client):
    return {"Authorization": f"Bearer {login(client)['token']}"}


def test_health_and_sources(client, headers):
    h = client.get("/healthz").json()
    assert h["status"] == "ok" and h["passages"] == 10009
    assert h["search_mode"] in {"hybrid", "keyword"}
    assert client.get("/v1/sources").status_code == 401
    ids = {s["id"] for s in client.get("/v1/sources", headers=headers).json()["sources"]}
    assert {"lieberman2005", "comsol_icp_cf4o2"} <= ids


def test_login_service_key_and_bad_tokens(client):
    wrong_user = client.post("/v1/auth/login", json={"username": "nobody", "password": TEST_PASSWORD})
    wrong_password = client.post("/v1/auth/login", json={"username": "demo-user", "password": "wrong"})
    assert wrong_user.status_code == wrong_password.status_code == 401
    assert wrong_user.json() == wrong_password.json()
    result = login(client)
    claims = auth.verify_token(result["token"], TEST_SECRET)
    assert result["username"] == "demo-user" and claims and result["expires_at"] == claims["exp"]
    assert claims["sub"] == "demo-user"
    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {result['token']}"})
    assert me.status_code == 200 and me.json() == {"username": "demo-user"}
    assert client.get("/v1/auth/me").status_code == 401
    assert client.get("/v1/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    assert client.get("/v1/sources", headers={"X-Service-Key": "wrong"}).status_code == 401
    assert client.get("/v1/sources", headers={"X-Service-Key": TEST_SERVICE_KEY}).status_code == 200


def test_expired_token_is_rejected(client):
    token, _claims = auth.issue_token(
        "demo-user", TEST_SECRET, datetime.now(timezone.utc) - timedelta(hours=12, minutes=1)
    )
    response = client.get("/v1/sources", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_search_and_pages(client, headers):
    r = client.post("/v1/search", headers=headers, json={"query": "Bohm flux to the wafer", "top_k": 3}).json()
    assert r["mode"] in {"hybrid", "keyword"}
    assert len(r["results"]) == 3 and r["results"][0]["citation"]
    hit = r["results"][0]
    p = client.get(f"/v1/sources/{hit['source_id']}/pages", headers=headers,
                   params={"first": hit["pdf_pages"][0]}).json()
    assert p["pages"][0]["text"]
    assert client.get("/v1/sources/nope/pages", headers=headers, params={"first": 1}).status_code == 404


def test_chat_then_continue(client, headers):
    r = client.post("/v1/chat", headers=headers, json={"message": "Why is Te independent of power?", "user_id": "attacker"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tool_calls"][0]["name"] == "search_literature"
    assert len(body["citations"]) == 3 and body["citations"][0]["citation"] in body["answer"]
    sid = body["session_id"]
    r2 = client.post("/v1/chat", headers=headers,
                     json={"message": "Now review that", "agent": "professor_reviewer", "session_id": sid}).json()
    assert r2["session_id"] == sid
    trusted = client.get(f"/v1/sessions/{sid}", headers=headers, params={"user_id": "attacker"})
    assert trusted.status_code == 200
    assert [m["role"] for m in trusted.json()["messages"]] == ["user", "agent", "user", "agent"]


def test_chat_stream(client, headers):
    with client.stream("POST", "/v1/chat/stream", headers=headers,
                       json={"message": "Why is Te independent of power?"}) as r:
        events = []
        kind = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                events.append((kind, json.loads(line[6:])))
    kinds = [k for k, _ in events]
    assert kinds[0] == "session" and kinds[-1] == "done"
    assert "tool_call" in kinds and "tool_result" in kinds
    deltas = "".join(d["delta"] for k, d in events if k == "text")
    assert deltas == events[-1][1]["answer"] and len(events[-1][1]["citations"]) == 3


def test_message_too_long(client, headers):
    assert client.post("/v1/chat", headers=headers, json={"message": "x" * 5000}).status_code == 413


def test_login_rate_limit_per_ip():
    with TestClient(create_app(model=ScriptedLlm(), index_dir=INDEX_DIR)) as limited:
        for _ in range(5):
            response = limited.post("/v1/auth/login", json={"username": "demo-user", "password": "wrong"})
            assert response.status_code == 401
        sixth = limited.post("/v1/auth/login", json={"username": "demo-user", "password": TEST_PASSWORD})
        assert sixth.status_code == 429 and "login attempts" in sixth.json()["detail"]


def test_password_and_token_helpers(monkeypatch, caplog):
    encoded = auth.hash_password("example-password")
    assert encoded.startswith("pbkdf2_sha256$") and auth.verify_password("example-password", encoded)
    assert not auth.verify_password("wrong", encoded) and not auth.verify_password("x", "not-a-hash")
    token, payload = auth.issue_token("alice", TEST_SECRET, now=datetime(2026, 10, 17, tzinfo=timezone.utc))
    assert payload["exp"] - payload["iat"] == auth.TOKEN_LIFETIME_S
    assert auth.verify_token(token + "x", TEST_SECRET) is None
    assert auth.verify_token(token, b"other-secret") is None
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    assert auth.auth_secret_from_env() is None
    assert any("DISABLED" in record.message for record in caplog.records)
