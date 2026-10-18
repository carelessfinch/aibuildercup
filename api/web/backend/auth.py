"""Shared demo auth: PBKDF2 password hashes and 12-hour HMAC-SHA256 tokens."""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time
from datetime import UTC, datetime
from typing import Any

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 240_000
TOKEN_LIFETIME_S = 12 * 60 * 60
DUMMY_HASH = (
    "pbkdf2_sha256$240000$wgvi4ROufFo8JTso8sQMMg==$"
    "ehnYNi1tVCj2ACpEw6B6ZVwNZ75svew52UFjr73xSUY="
)
_log = logging.getLogger(__name__)


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        (
            PBKDF2_ALGORITHM,
            str(iterations),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, salt, expected = encoded.split("$", 3)
        iterations = int(raw_iterations)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     base64.b64decode(salt, validate=True), iterations)
        return algorithm == PBKDF2_ALGORITHM and iterations > 0 and hmac.compare_digest(
            digest, base64.b64decode(expected, validate=True))
    except (ValueError, TypeError):
        return False


def issue_token(
    sub: str, secret: bytes, now: datetime | None = None
) -> tuple[str, dict[str, int | str]]:
    at = int((now or datetime.now(UTC)).timestamp())
    payload = {"sub": sub, "iat": at, "exp": at + TOKEN_LIFETIME_S}
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(encoded).rstrip(b"=")
    digest = hmac.new(secret, body, hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).rstrip(b"=")
    return f"{body.decode('ascii')}.{signature.decode('ascii')}", payload


def verify_token(token: str, secret: bytes, now: float | None = None) -> dict[str, Any] | None:
    try:
        body, supplied = token.rsplit(".", 1)
        expected = hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(supplied + "=" * (-len(supplied) % 4))
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        at = int(time.time() if now is None else now)
        valid = hmac.compare_digest(actual, expected) and payload["exp"] > at
        return payload if valid and isinstance(payload.get("sub"), str) else None
    except (KeyError, TypeError, ValueError, UnicodeError):
        return None


def auth_secret_from_env(name: str = "AUTH_SECRET") -> bytes | None:
    secret = os.environ.get(name, "")
    if not secret:
        _log.warning(
            "%s is unset: authentication is DISABLED. Never deploy this configuration.", name
        )
        return None
    return secret.encode("utf-8")


def _hash_cli() -> None:
    if sys.argv[1:] != ["hash"]:
        print("usage: python -m app.auth hash", file=sys.stderr)
        raise SystemExit(2)
    password, repeat = getpass.getpass("Password: "), getpass.getpass("Confirm password: ")
    if password != repeat:
        print("passwords do not match", file=sys.stderr)
        raise SystemExit(1)
    print(hash_password(password))


if __name__ == "__main__":
    _hash_cli()
