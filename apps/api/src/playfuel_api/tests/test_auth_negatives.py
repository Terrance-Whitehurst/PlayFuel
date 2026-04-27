"""JWT authentication negative-path tests.

Covers the gap in Task #5 QA report — verify_supabase_jwt negative paths
(expired, missing sub, non-UUID sub, wrong audience, invalid signature)
were untested.

All tests assert HTTP 401 with the exact static detail string from auth.py.
No exception text is reflected in the response body (security closure per Task #5).

Detail strings (verbatim from auth.py — do not change without updating auth.py):
    no creds       → "Missing or invalid authorization header"
    expired        → "Token has expired"
    InvalidToken   → "Invalid token"
    missing sub    → "Token missing sub claim"
    non-UUID sub   → "Token sub is not a valid UUID"

Fixture: jwt_test_client
    TestClient where Settings is overridden with a known JWT secret so we can
    mint test tokens that the real verify_supabase_jwt dependency can decode.
    Supabase client is NOT overridden — /v1/me will attempt a real DB call.
    We use /v1/me because it's the simplest authenticated endpoint; 401 is
    returned before the DB call is attempted when auth fails.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

# ── Constants ─────────────────────────────────────────────────────────────────

TEST_SECRET = "test-secret-for-jwt-tests-only-do-not-use-in-prod"
TEST_USER_UUID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
VALID_AUD = "authenticated"

_NOW = datetime.now(tz=timezone.utc)


def _make_token(
    extra_claims: dict | None = None,
    secret: str = TEST_SECRET,
    algorithm: str = "HS256",
    omit_sub: bool = False,
) -> str:
    """Mint a test JWT using pyjwt. Base claims satisfy auth.py's requirements."""
    base: dict = {
        "aud": VALID_AUD,
        "exp": int((_NOW + timedelta(hours=1)).timestamp()),
        "iat": int(_NOW.timestamp()),
    }
    if not omit_sub:
        base["sub"] = TEST_USER_UUID
    if extra_claims:
        base.update(extra_claims)
    return jwt.encode(base, secret, algorithm=algorithm)


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def jwt_test_client():
    """TestClient with Settings overridden to use TEST_SECRET.

    Only get_settings is overridden — the real verify_supabase_jwt dependency
    runs, which means auth failures are genuine (not mocked out).

    The mock_db fixture from conftest is NOT used here because we never reach
    the DB call — all JWT-negative tests should fail at the auth layer first.
    The client is constructed with raise_server_exceptions=False so that
    unhandled 5xx (e.g., if a test accidentally passes auth) don't mask the
    real assertion.
    """
    from playfuel_api.main import app
    from playfuel_api.settings import Settings, get_settings

    test_settings = Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test-anon",
        supabase_service_role_key="test-service",
        supabase_jwt_secret=TEST_SECRET,
    )
    app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc

    app.dependency_overrides.pop(get_settings, None)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_no_authorization_header_returns_401(client_no_auth):
    """GET /v1/me without any Authorization header → 401.

    Uses the standard client_no_auth fixture (no dep overrides).
    Verifies the Task #5 closeout 401-not-403 fix still holds:
    HTTPBearer(auto_error=False) + manual guard → always 401 for missing creds.
    """
    resp = client_no_auth.get("/v1/me")
    assert resp.status_code == 401, (
        f"Expected 401 for missing auth header, got {resp.status_code}"
    )
    body = resp.json()
    assert "Missing or invalid authorization header" in body.get("detail", ""), (
        f"Unexpected detail: {body.get('detail')}"
    )


def test_expired_jwt_returns_401(jwt_test_client):
    """JWT with exp in the past → 401 with 'Token has expired' detail."""
    expired_token = _make_token(
        extra_claims={"exp": int((_NOW - timedelta(hours=1)).timestamp())}
    )
    resp = jwt_test_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401, (
        f"Expected 401 for expired token, got {resp.status_code}"
    )
    detail = resp.json().get("detail", "")
    assert "expired" in detail.lower(), (
        f"Expected 'expired' in detail, got: {detail!r}"
    )


def test_jwt_with_wrong_audience_returns_401(jwt_test_client):
    """JWT with aud != 'authenticated' → 401 with 'Invalid token' detail."""
    wrong_aud_token = _make_token(extra_claims={"aud": "wrong-audience"})
    resp = jwt_test_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {wrong_aud_token}"},
    )
    assert resp.status_code == 401, (
        f"Expected 401 for wrong audience, got {resp.status_code}"
    )
    detail = resp.json().get("detail", "")
    assert "Invalid token" in detail, (
        f"Expected 'Invalid token' in detail, got: {detail!r}"
    )


def test_jwt_missing_sub_returns_401(jwt_test_client):
    """JWT without 'sub' claim → 401 with 'Token missing sub claim' detail."""
    no_sub_token = _make_token(omit_sub=True)
    resp = jwt_test_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {no_sub_token}"},
    )
    assert resp.status_code == 401, (
        f"Expected 401 for missing sub, got {resp.status_code}"
    )
    detail = resp.json().get("detail", "")
    assert "missing sub" in detail.lower(), (
        f"Expected 'missing sub' in detail, got: {detail!r}"
    )


def test_jwt_non_uuid_sub_returns_401(jwt_test_client):
    """JWT with sub='not-a-uuid' → 401 with 'Token sub is not a valid UUID' detail."""
    bad_sub_token = _make_token(extra_claims={"sub": "not-a-uuid"})
    resp = jwt_test_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {bad_sub_token}"},
    )
    assert resp.status_code == 401, (
        f"Expected 401 for non-UUID sub, got {resp.status_code}"
    )
    detail = resp.json().get("detail", "")
    assert "not a valid UUID" in detail, (
        f"Expected 'not a valid UUID' in detail, got: {detail!r}"
    )


def test_jwt_with_invalid_signature_returns_401(jwt_test_client):
    """JWT signed with wrong secret → 401 with 'Invalid token' detail."""
    wrong_secret_token = _make_token(secret="a-completely-different-secret")
    resp = jwt_test_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {wrong_secret_token}"},
    )
    assert resp.status_code == 401, (
        f"Expected 401 for invalid signature, got {resp.status_code}"
    )
    detail = resp.json().get("detail", "")
    assert "Invalid token" in detail, (
        f"Expected 'Invalid token' in detail, got: {detail!r}"
    )


def test_jwt_detail_does_not_leak_exception_string(jwt_test_client):
    """Invalid token detail must be static — must NOT contain the raw exception message.

    Security closure: auth.py was updated in Task #5 to use static 'Invalid token'
    string rather than f'Invalid token: {exc}'. This test locks that in.
    """
    wrong_secret_token = _make_token(secret="another-wrong-secret")
    resp = jwt_test_client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {wrong_secret_token}"},
    )
    assert resp.status_code == 401
    detail = resp.json().get("detail", "")
    # Must not contain colon-separated exception info (the old format was "Invalid token: <exc>")
    assert "Signature verification failed" not in detail, (
        "JWT exception detail leaked in response body — security regression"
    )
    assert "DecodeError" not in detail, (
        "JWT exception class leaked in response body — security regression"
    )
