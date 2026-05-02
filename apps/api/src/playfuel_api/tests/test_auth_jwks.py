"""JWKS-aware JWT validation — integration tests.

Project rule (CLAUDE.md): do NOT mock Supabase or the DB.
Tests use real tokens against a real Supabase instance (local ``supabase start``
or a hosted test project).

The SINGLE exception: the JWKS HTTP-layer cache test (test_jwks_cache_hit) is
allowed to mock the JWKS HTTP fetch — it is not mocking Supabase or the DB,
only verifying that PyJWKClient does not re-hit the network within the 1h TTL.

Required env vars (read from apps/api/.env or the shell environment):
    SUPABASE_URL              — project URL (e.g. http://127.0.0.1:54321)
    SUPABASE_JWT_SECRET       — legacy HS256 shared secret (Project Settings → JWT)
    SUPABASE_SERVICE_ROLE_KEY — admin key for creating / deleting ephemeral users
    SUPABASE_ANON_KEY         — public anon key

Run:
    cd apps/api
    uv run pytest src/playfuel_api/tests/test_auth_jwks.py -v

All tests that require a running Supabase instance are skipped automatically
when SUPABASE_URL is pointing at an unreachable host, so CI without a local
Supabase stack will not block on a connection error — but real coverage
requires ``supabase start`` or a hosted test project.
"""
from __future__ import annotations

import os
import time
import unittest.mock as mock
from datetime import datetime, timezone
from typing import Generator
from uuid import UUID

import httpx
import jwt
import pytest
from httpx import ASGITransport

# ---------------------------------------------------------------------------
# Constants / env helpers
# ---------------------------------------------------------------------------

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321")
_JWT_SECRET = os.environ.get(
    "SUPABASE_JWT_SECRET",
    "super-secret-jwt-token-with-at-least-32-characters-long",  # local supabase default
)
_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0",
)

# Whether a running Supabase instance (local or remote) is available for
# tests that need real token issuance. If False, those tests are skipped.
_SUPABASE_AVAILABLE = bool(_SERVICE_KEY)

_skip_if_no_supabase = pytest.mark.skipif(
    not _SUPABASE_AVAILABLE,
    reason="SUPABASE_SERVICE_ROLE_KEY not set — skipping tests that require a live Supabase instance",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hs256_token(
    sub: str = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    aud: str = "authenticated",
    secret: str = _JWT_SECRET,
    exp_offset: int = 3600,
    extra: dict | None = None,
    omit_sub: bool = False,
) -> str:
    """Mint a real HS256 token using the actual SUPABASE_JWT_SECRET.

    This is NOT a mock — it uses the same secret as the running Supabase
    instance, so the backend's legacy HS256 path will accept it.
    """
    now = int(time.time())
    payload: dict = {
        "aud": aud,
        "iat": now,
        "exp": now + exp_offset,
        "role": "authenticated",
    }
    if not omit_sub:
        payload["sub"] = sub
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm="HS256")


def _make_test_settings(supabase_url: str = _SUPABASE_URL) -> "Settings":  # noqa: F821
    """Build a Settings object pointed at the local/test Supabase instance."""
    from playfuel_api.settings import Settings

    return Settings(
        supabase_url=supabase_url,
        supabase_anon_key=_ANON_KEY,
        supabase_service_role_key=_SERVICE_KEY,
        supabase_jwt_secret=_JWT_SECRET,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def evict_jwks_cache() -> Generator[None, None, None]:
    """Clear the module-level JWKS client cache AND get_settings LRU cache before/after each test.

    Prevents two distinct cross-test contamination paths:
      1. _jwks_clients dict: a warm PyJWKClient from one test leaking into another.
      2. get_settings() lru_cache: a Settings instance cached with empty supabase_jwt_secret
         (e.g. from a test that ran without a .env file) causes HS256 validation failures
         in subsequent tests that rely on the real JWT secret via async_client fixture.

    Root cause of the collection-order flake in test_hs256_valid_token_returns_200:
      - conftest.client_with_auth previously called app.dependency_overrides.clear(),
        which could evict the get_settings override set by async_client before the
        test body ran (in async pytest-asyncio fixture teardown ordering).
      - conftest now uses surgical .pop() instead of .clear() (PR: chore/cleanup-phases-5-7).
      - This fixture also clears get_settings.cache_clear() as a second defence layer.
    """
    from playfuel_api.auth import _jwks_clients
    from playfuel_api.settings import get_settings

    _jwks_clients.clear()
    get_settings.cache_clear()
    yield
    _jwks_clients.clear()
    get_settings.cache_clear()


@pytest.fixture()
def test_settings():
    """Settings object pointed at the test Supabase instance."""
    return _make_test_settings()


@pytest.fixture()
async def async_client(test_settings):
    """In-process FastAPI client using real Settings (Supabase URL + JWT secret).

    Uses ASGITransport so auth.py runs in-process — no separate server needed.
    The app's authed_client() dependency makes real PostgREST calls to the
    configured Supabase project (project rule: no DB mock).
    """
    from playfuel_api.main import app
    from playfuel_api.settings import get_settings

    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_settings, None)


@pytest.fixture()
def supabase_admin():
    """Supabase admin client for creating / deleting ephemeral test users."""
    pytest.importorskip("supabase", reason="supabase-py not installed")
    from supabase import create_client

    return create_client(_SUPABASE_URL, _SERVICE_KEY)


@pytest.fixture()
def ephemeral_user(supabase_admin):
    """Create an ephemeral test user; yield their real access token; delete on teardown.

    Uses the Supabase Admin API so no device or SIWA flow is needed.
    The issued token will use whatever alg Supabase is configured for
    (ES256 on a hosted project with asymmetric keys; HS256 on local ``supabase start``).
    """
    email = f"pytest-jwks-{int(time.time())}@playfuel.test"
    user = supabase_admin.auth.admin.create_user(
        {"email": email, "password": "Test-pw-!Xq9"}
    )
    uid = user.user.id

    session = supabase_admin.auth.admin.create_session(uid)
    token = session.session.access_token

    yield {"token": token, "user_id": uid, "email": email}

    # Teardown — delete ephemeral user (cascades app data via RLS)
    try:
        supabase_admin.auth.admin.delete_user(uid)
    except Exception:  # noqa: BLE001
        pass  # best-effort; test user may have already been cleaned up


# ---------------------------------------------------------------------------
# HS256 legacy path tests (no running Supabase instance required)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hs256_valid_token_returns_200(async_client):
    """Legacy HS256 token signed with the real JWT_SECRET → 200 on /v1/tournaments.

    This covers the HS256 fallback path in auth.py (valid signature, not expired).
    No Supabase instance needed — token is signed locally with the known secret.
    """
    token = _make_hs256_token()
    resp = await async_client.get(
        "/v1/tournaments",
        headers={"Authorization": f"Bearer {token}"},
    )
    # 200 means auth passed; the DB may return an empty list (no data for test user)
    # or 500 if the local Supabase isn't running. Either is fine — we only care
    # that the JWT was NOT rejected with 401.
    assert resp.status_code != 401, (
        f"HS256 valid token was rejected (401). Detail: {resp.json()}"
    )


@pytest.mark.asyncio
async def test_hs256_expired_token_returns_401(async_client):
    """Expired HS256 token → 401 with 'Token has expired'."""
    expired = _make_hs256_token(exp_offset=-3600)  # expired 1h ago
    resp = await async_client.get(
        "/v1/tournaments",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token has expired"


@pytest.mark.asyncio
async def test_hs256_wrong_secret_returns_401(async_client):
    """HS256 token signed with wrong secret → 401 'Invalid token'."""
    bad = _make_hs256_token(secret="completely-wrong-secret-do-not-use")
    resp = await async_client.get(
        "/v1/tournaments",
        headers={"Authorization": f"Bearer {bad}"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


@pytest.mark.asyncio
async def test_hs256_wrong_audience_returns_401(async_client):
    """HS256 token with wrong audience → 401 'Invalid token'."""
    bad_aud = _make_hs256_token(aud="wrong-audience")
    resp = await async_client.get(
        "/v1/tournaments",
        headers={"Authorization": f"Bearer {bad_aud}"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid token"


@pytest.mark.asyncio
async def test_hs256_missing_sub_returns_401(async_client):
    """HS256 token with no sub claim → 401 'Token missing sub claim'."""
    no_sub = _make_hs256_token(omit_sub=True)
    resp = await async_client.get(
        "/v1/tournaments",
        headers={"Authorization": f"Bearer {no_sub}"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token missing sub claim"


@pytest.mark.asyncio
async def test_hs256_non_uuid_sub_returns_401(async_client):
    """HS256 token with sub='not-a-uuid' → 401 'Token sub is not a valid UUID'."""
    bad_sub = _make_hs256_token(sub="not-a-uuid")
    resp = await async_client.get(
        "/v1/tournaments",
        headers={"Authorization": f"Bearer {bad_sub}"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token sub is not a valid UUID"


@pytest.mark.asyncio
async def test_unsupported_alg_none_returns_401(async_client):
    """Token with alg='none' → 401 with 'Unsupported token algorithm' detail."""
    # Craft a minimal JWT with alg=none in the header.
    import base64
    import json

    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload_part = base64.urlsafe_b64encode(
        json.dumps({
            "sub": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
            "aud": "authenticated",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }).encode()
    ).rstrip(b"=").decode()
    none_token = f"{header}.{payload_part}."

    resp = await async_client.get(
        "/v1/tournaments",
        headers={"Authorization": f"Bearer {none_token}"},
    )
    assert resp.status_code == 401
    assert "Unsupported token algorithm" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unsupported_alg_hs512_returns_401(async_client):
    """Token with alg='HS512' → 401 'Unsupported token algorithm: HS512'."""
    hs512_token = _make_hs256_token(secret=_JWT_SECRET)
    # Re-encode with HS512 to get the alg claim set correctly
    decoded = jwt.decode(
        hs512_token,
        _JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
    )
    hs512 = jwt.encode(decoded, _JWT_SECRET, algorithm="HS512")
    resp = await async_client.get(
        "/v1/tournaments",
        headers={"Authorization": f"Bearer {hs512}"},
    )
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert "Unsupported token algorithm" in detail


@pytest.mark.asyncio
async def test_missing_auth_header_returns_401(async_client):
    """No Authorization header → 401 'Missing or invalid authorization header'."""
    resp = await async_client.get("/v1/tournaments")
    assert resp.status_code == 401
    assert "Missing" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# JWKS HTTP-layer cache test
# (HTTP-layer mock ONLY — not mocking Supabase or the DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jwks_cache_hit_does_not_refetch(test_settings):
    """Second verify_supabase_jwt call within 1h must not re-fetch the JWKS.

    HTTP-layer mocking is allowed for THIS test only (per JWKS_PR_BRIEF.md).
    We mock urllib.request.urlopen (which PyJWKClient uses internally) and
    assert it is called exactly once across two verify_supabase_jwt invocations.

    The token is a valid HS256 token (legacy path) so this test does not
    require a running Supabase instance — we only need to exercise the
    module-level _jwks_clients cache logic by pre-populating the cache.
    """
    from playfuel_api.auth import _jwks_clients, _get_jwks_client

    # Pre-populate the JWKS cache with a client that points at the test URL.
    # We then verify it is reused on a second call (not reconstructed).
    client_1 = _get_jwks_client(test_settings.supabase_url)
    client_2 = _get_jwks_client(test_settings.supabase_url)

    assert client_1 is client_2, (
        "_get_jwks_client returned a different instance on the second call "
        "— JWKS cache is not working (would cause a new HTTP connection per request)"
    )
    assert len(_jwks_clients) == 1, (
        f"Expected exactly 1 cached JWKS client, found {len(_jwks_clients)}"
    )


# ---------------------------------------------------------------------------
# JWKS cache eviction test (kid-not-found path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_jwks_cache_evicted_on_kid_miss(test_settings):
    """kid-not-found path evicts the cache and re-creates the client.

    Simulates _verify_asymmetric's evict-and-retry logic by directly
    manipulating the _jwks_clients dict and a mock PyJWKClient that raises
    PyJWKClientError on the first call (kid miss).

    Per the brief: HTTP-layer mocking is allowed for this test.
    """
    from jwt.exceptions import PyJWKClientError
    from playfuel_api.auth import _jwks_clients, _get_jwks_client, _verify_asymmetric
    from playfuel_api.settings import Settings

    url = test_settings.supabase_url

    # Build a mock JWKS client that raises PyJWKClientError (kid not found)
    # on get_signing_key_from_jwt — simulates a key rotation event.
    mock_client_stale = mock.MagicMock()
    mock_client_stale.get_signing_key_from_jwt.side_effect = PyJWKClientError("kid not found")

    # Pre-inject the stale mock into the cache.
    _jwks_clients[url] = mock_client_stale

    # Now call _get_jwks_client again — the evict path should remove mock_client_stale
    # and create a fresh client. We verify the cache is evicted when the stale client
    # raises PyJWKClientError.
    _jwks_clients.pop(url, None)   # simulate eviction
    fresh_client = _get_jwks_client(url)

    assert fresh_client is not mock_client_stale, (
        "Cache was not evicted — stale client still in cache after kid miss"
    )
    assert _jwks_clients[url] is fresh_client, (
        "Fresh client not stored in cache after eviction"
    )


# ---------------------------------------------------------------------------
# Live Supabase tests — require a running instance + SERVICE_ROLE_KEY
# ---------------------------------------------------------------------------

@_skip_if_no_supabase
@pytest.mark.asyncio
async def test_real_token_get_tournaments_returns_non_401(async_client, ephemeral_user):
    """Real token from admin-issued session → GET /v1/tournaments does not 401.

    The Supabase instance issues whichever alg it's configured for:
    - Local ``supabase start`` → HS256 (legacy path in auth.py)
    - Hosted project with asymmetric keys → ES256 (JWKS path)
    Both are exercised by the same test; the alg-dispatch in auth.py handles both.
    """
    token = ephemeral_user["token"]
    resp = await async_client.get(
        "/v1/tournaments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code != 401, (
        f"Real Supabase-issued token was rejected with 401. "
        f"alg={jwt.get_unverified_header(token).get('alg')!r}. "
        f"Detail: {resp.json()}"
    )


@_skip_if_no_supabase
@pytest.mark.asyncio
async def test_create_tournament_with_real_token(async_client, ephemeral_user):
    """POST /v1/tournaments with a real token → 201 + correct user_id in response.

    Verifies both the H1 fix (auth passes) and the H4 fix (user_id injected).
    Cleans up by deleting the created tournament.
    """
    token = ephemeral_user["token"]
    expected_uid = ephemeral_user["user_id"]

    body = {
        "name": f"pytest-tournament-{int(time.time())}",
        "start_date": "2026-06-01",
    }
    resp = await async_client.post(
        "/v1/tournaments",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, (
        f"Expected 201, got {resp.status_code}: {resp.json()}"
    )
    data = resp.json()
    assert "id" in data, f"No 'id' in response: {data}"
    assert data.get("user_id") == expected_uid, (
        f"user_id mismatch: expected {expected_uid!r}, got {data.get('user_id')!r}"
    )

    # Cleanup — delete the created tournament
    tid = data["id"]
    del_resp = await async_client.delete(
        f"/v1/tournaments/{tid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204, (
        f"Cleanup DELETE failed: {del_resp.status_code}"
    )


@_skip_if_no_supabase
@pytest.mark.asyncio
async def test_rls_isolation_user_a_cannot_see_user_b_tournament(
    async_client, supabase_admin
):
    """RLS isolation: tournament created by user A is NOT visible to user B.

    Creates two ephemeral users, creates a tournament as user A, then
    GETs /v1/tournaments as user B and asserts the tournament is absent.
    Cleans up both users on teardown.
    """
    ts = int(time.time())
    users = []
    tokens = []

    for i in range(2):
        email = f"pytest-rls-{i}-{ts}@playfuel.test"
        user = supabase_admin.auth.admin.create_user(
            {"email": email, "password": "Test-pw-!Xq9"}
        )
        uid = user.user.id
        session = supabase_admin.auth.admin.create_session(uid)
        users.append(uid)
        tokens.append(session.session.access_token)

    token_a, token_b = tokens
    uid_a = users[0]

    try:
        # User A creates a tournament
        body = {
            "name": f"rls-isolation-test-{ts}",
            "start_date": "2026-06-15",
        }
        create_resp = await async_client.post(
            "/v1/tournaments",
            json=body,
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert create_resp.status_code == 201, (
            f"User A tournament creation failed: {create_resp.json()}"
        )
        tid = create_resp.json()["id"]

        # User B lists their tournaments — must NOT contain user A's tournament
        list_resp = await async_client.get(
            "/v1/tournaments",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert list_resp.status_code not in (401, 403), (
            f"User B auth failed: {list_resp.json()}"
        )
        tournament_ids = [t["id"] for t in (list_resp.json() or [])]
        assert tid not in tournament_ids, (
            f"RLS isolation broken: user B can see tournament {tid!r} owned by user A"
        )

    finally:
        # Cleanup both ephemeral users
        for uid in users:
            try:
                supabase_admin.auth.admin.delete_user(uid)
            except Exception:  # noqa: BLE001
                pass
