from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from simtools.fourm import parse_form
from web.backend import auth
from web.backend.app import create_app
from web.backend.presets import CASE_DIR
from web.backend.settings import WebSettings
from web.backend.store import RunStore

FOUR_M = {
    "case_id": "cf4o2_demo",
    "question": "How does ion flux vary to 100 V bias?",
    "machine": {
        "chamber_radius_mm": 150,
        "reactor_height_mm": 120,
        "chuck": "100 mm cathode",
        "diagnostics": ["langmuir_probe"],
    },
    "material": {"wafer": "Si", "stack": ["SiO2"]},
    "method": {
        "recipe": {
            "power_W": 100,
            "pressure_mTorr": 15,
            "CF4_sccm": 40,
            "O2_sccm": 10,
        },
        "metrology": ["SEM"],
    },
    "man": {"operator_experience": "senior", "shift": "day", "notes": "Demo"},
    "source": "form",
}


def settings(**overrides: object) -> WebSettings:
    values: dict[str, object] = {"run_task_delay_s": 0.01, **overrides}
    return WebSettings(**values)  # type: ignore[arg-type]


def wait_for_status(
    client: TestClient,
    run_id: str,
    status: str,
    timeout: float = 2.0,
    headers: dict[str, str] | None = None,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/runs/{run_id}", headers=headers)
        if response.status_code == 200 and response.json()["status"] == status:
            return
        time.sleep(0.01)
    raise AssertionError(f"run did not reach {status!r}")


def test_health_reports_the_configured_flow_seam() -> None:
    client = TestClient(create_app(settings()))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "flow_backend": "mock",
        "flow_mode": "graph",
        "flow_include_etch": False,
    }


def test_review_round_cap_is_enforced_at_settings_boundary() -> None:
    assert WebSettings(review_max_rounds=99).review_max_rounds == 3
    assert WebSettings(review_max_rounds=0).review_max_rounds == 1


def test_create_stream_and_signoff_flow() -> None:
    client = TestClient(create_app(settings()))
    response = client.post("/runs", json=FOUR_M)
    assert response.status_code == 201, response.text
    run_id = response.json()["run_id"]

    wait_for_status(client, run_id, "awaiting_signoff")
    with client.stream("GET", f"/runs/{run_id}/events", params={"replay": "true"}) as stream:
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        body = stream.read().decode("utf-8")
    assert "event: run_received" in body
    assert "event: awaiting_signoff" in body
    assert '"case_id":"cf4o2_demo"' in body

    plots = client.get(f"/runs/{run_id}").json()["plots"]
    assert len(plots) == 3
    first_plot = client.get(plots[0])
    assert first_plot.status_code == 200
    assert first_plot.headers["content-type"] == "image/svg+xml"

    signoff = client.post(f"/runs/{run_id}/signoff", json={"reviewer": "reviewer"})
    assert signoff.status_code == 200
    assert signoff.json()["status"] == "signed_off"
    assert signoff.json()["elapsed_seconds"] >= 0

    again = client.post(f"/runs/{run_id}/signoff", json={"reviewer": "reviewer"})
    assert again.status_code == 409


def test_invalid_4m_payload_is_rejected_with_field_details() -> None:
    client = TestClient(create_app(settings()))
    bad = {**FOUR_M, "material": {"stack": ["SiO2"]}}
    response = client.post("/runs", json=bad)
    assert response.status_code == 422
    assert "material" in response.text


def test_unknown_run_and_plot_are_404() -> None:
    client = TestClient(create_app(settings()))
    assert client.get("/runs/missing/events").status_code == 404
    assert client.get("/runs/missing/plots/nope.svg").status_code == 404
    assert client.post("/runs/missing/signoff", json={}).status_code == 404


def test_per_ip_rate_limit_returns_429_with_retry_after() -> None:
    client = TestClient(create_app(settings(rate_limit_per_ip_per_hour=1)))
    first = client.post("/runs", json=FOUR_M)
    assert first.status_code == 201
    second = client.post("/runs", json=FOUR_M)
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0
    assert "Too many runs" in second.json()["detail"]


def test_concurrent_cap_and_spend_killswitch() -> None:
    client = TestClient(create_app(settings(max_concurrent_runs=0)))
    blocked = client.post("/runs", json=FOUR_M)
    assert blocked.status_code == 409

    stopped = TestClient(create_app(settings(spend_killswitch=True)))
    killed = stopped.post("/runs", json=FOUR_M)
    assert killed.status_code == 503
    assert "spending kill-switch" in killed.json()["detail"]


def test_escalated_report_is_never_marked_signed_off() -> None:
    store = RunStore()
    metadata = FOUR_M.copy()
    record = store.create(parse_form(metadata))

    class EscalatedFlow:
        async def execute(self, _metadata, _sink):
            return {"report": {"sign_off": "escalated"}}

    asyncio.run(store.run_flow(record, EscalatedFlow(), settings()))
    assert record.status == "escalated"
    assert record.completed_at is not None


def test_input_ranges_are_enforced() -> None:
    client = TestClient(create_app(settings()))
    variants = [
        {**FOUR_M, "method": {"recipe": {"power_W": 0, "pressure_mTorr": 15}}},
        {**FOUR_M, "method": {"recipe": {"power_W": 100, "pressure_mTorr": 501}}},
        {**FOUR_M, "method": {"recipe": {"power_W": 100, "pressure_mTorr": 15, "CF4_sccm": 1001}}},
        {
            **FOUR_M,
            "method": {
                "recipe": {
                    "power_W": 100,
                    "pressure_mTorr": 15,
                    "bias_sweep_V": [-201, 0],
                }
            },
        },
        {
            **FOUR_M,
            "method": {
                "recipe": {
                    "power_W": 100,
                    "pressure_mTorr": 15,
                    "bias_sweep_V": list(range(13)),
                }
            },
        },
    ]
    for payload in variants:
        response = client.post("/runs", json=payload)
        assert response.status_code == 422, response.text
        assert "between" in response.text or "at most 12 points" in response.text


def test_presets_allow_list_and_fault_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    client = TestClient(create_app(settings()))
    presets = client.get("/presets")
    assert presets.status_code == 200
    rows = presets.json()["presets"]
    ids = [row["preset_id"] for row in rows]
    case_ids = sorted(path.stem for path in CASE_DIR.glob("*.json"))
    assert sorted(ids) == case_ids  # every public eval case is offered
    assert ids[:2] == ["good_cf4o2_baseline", "good_argon_baseline"]
    for row in rows:
        assert row["title"] and row["fourm_input"]["case_id"]
    # 4M-input faults show the faulty input so the form matches what is rejected.
    wafer = next(row for row in rows if row["preset_id"] == "fault_missing_wafer")
    assert "wafer" not in wafer["fourm_input"]["material"]
    for rejected, reason in (
        ("fault_negative_flow", "negative_flow"),
        ("fault_chemistry_negative_rate", "chemistry_schema"),
    ):
        response = client.post("/runs", json={"preset_id": rejected})
        assert response.status_code == 422, response.text
        assert reason in response.json()["detail"]

    created = client.post("/runs", json={"preset_id": "fault_te_impossible"})
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    wait_for_status(client, run_id, "escalated")
    run = client.get(f"/runs/{run_id}").json()
    assert any(event["event_type"] == "fault_injected_demo" for event in run["events"])
    result_events = [event for event in run["events"] if event["event_type"] == "result_received"]
    assert result_events[0]["data"]["result"]["points"][0]["te_eV"] == 250.0
    assert any(event["actor"] == "PhD" for event in run["events"])
    assert client.post("/runs", json={"preset_id": "not_allowed"}).status_code == 404
    combined = client.post("/runs", json={"preset_id": "good_argon_baseline", "question": "x"})
    assert combined.status_code == 422


def test_research_api_auth_and_token_derived_signoff(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = b"0123456789abcdef0123456789abcdef"
    monkeypatch.setenv("AUTH_SECRET", secret.decode())
    client = TestClient(create_app(settings()))
    assert client.get("/health").status_code == 200
    assert client.get("/presets").status_code == 401
    assert client.post("/runs", json=FOUR_M).status_code == 401

    token, _ = auth.issue_token("demo-user", secret)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/presets", headers=headers).status_code == 200
    created = client.post("/runs", json=FOUR_M, headers=headers)
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    wait_for_status(client, run_id, "awaiting_signoff", headers=headers)
    with client.stream(
        "GET", f"/runs/{run_id}/events", params={"replay": "true"}, headers=headers
    ) as stream:
        assert stream.status_code == 200
        assert "event: awaiting_signoff" in stream.read().decode("utf-8")

    signed = client.post(
        f"/runs/{run_id}/signoff", json={"reviewer": "spoofed"}, headers=headers
    )
    assert signed.status_code == 200
    assert signed.json()["signed_off_by"] == "demo-user"
    detail = client.get(f"/runs/{run_id}", headers=headers).json()
    assert detail["final_payload"]["report"]["signed_off_by"] == "demo-user"
