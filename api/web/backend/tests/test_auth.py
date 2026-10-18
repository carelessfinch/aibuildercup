"""Focused behavior tests for the shared auth module; route integration belongs to W3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from web.backend import auth

SECRET = b"shared-hackathon-auth-secret"


def test_pbkdf2_hash_round_trip_and_malformed_hashes() -> None:
    encoded = auth.hash_password("correct horse battery staple")
    assert encoded.startswith("pbkdf2_sha256$240000$")
    assert auth.verify_password("correct horse battery staple", encoded)
    assert not auth.verify_password("wrong password", encoded)
    assert not auth.verify_password("wrong password", "not-a-hash")
    assert not auth.verify_password("wrong password", "pbkdf2_sha256$zero$#$#")


def test_token_round_trip_tamper_wrong_key_and_expiry() -> None:
    now = datetime(2026, 10, 17, tzinfo=UTC)
    token, claims = auth.issue_token("demo-user", SECRET, now)
    assert claims == {
        "sub": "demo-user",
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + auth.TOKEN_LIFETIME_S,
    }
    assert auth.verify_token(token, SECRET, now.timestamp()) == claims
    assert auth.verify_token(token + "x", SECRET, now.timestamp()) is None
    assert auth.verify_token(token, b"wrong-secret", now.timestamp()) is None
    expiry = now - timedelta(seconds=auth.TOKEN_LIFETIME_S + 1)
    expired, _ = auth.issue_token("demo-user", SECRET, expiry)
    assert auth.verify_token(expired, SECRET, now.timestamp()) is None


def test_missing_auth_secret_is_disabled_with_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    with caplog.at_level("WARNING"):
        assert auth.auth_secret_from_env() is None
    assert any("authentication is DISABLED" in record.message for record in caplog.records)
    monkeypatch.setenv("AUTH_SECRET", "configured")
    assert auth.auth_secret_from_env() == b"configured"
