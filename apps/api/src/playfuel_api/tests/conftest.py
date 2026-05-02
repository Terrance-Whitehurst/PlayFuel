"""Shared pytest fixtures for PlayFuel API tests.

Fixtures:
    mock_db            — MagicMock standing in for the Supabase Client.
    client_with_auth   — FastAPI TestClient with both auth + DB overridden.
    client_no_auth     — Plain TestClient with NO dependency overrides (real HTTPBearer).
    _reset_rate_limit  — autouse; clears per-user rate-limit deques between every test.

Auth override injects TEST_USER_ID so no real JWT secret is required in CI.
DB override prevents any real Supabase network calls during unit / smoke tests.

Rate-limit reset (SP-2): routes/plans.py keeps module-level in-memory deques to enforce
per-user hourly / daily caps on plan generation.  Without a reset fixture these counters
accumulate across tests — after the 10th generate_plan route call the 11th test trips
the 429 limit regardless of intent.  The autouse fixture below clears the deques before
every test, making plan-generation tests order-independent.
"""
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

TEST_USER_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


@pytest.fixture()
def mock_db() -> MagicMock:
    """Return a MagicMock that mimics the supabase-py Client interface.

    Callers configure return values per-test:
        mock_db.table.return_value.select.return_value.execute.return_value.data = [...]
    """
    return MagicMock()


@pytest.fixture()
def client_with_auth(mock_db: MagicMock) -> TestClient:
    """TestClient with auth and DB dependencies overridden.

    - verify_supabase_jwt → returns TEST_USER_ID (no real JWT needed)
    - authed_client → returns mock_db (no real Supabase network calls)
    """
    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    app.dependency_overrides[verify_supabase_jwt] = lambda: TEST_USER_ID
    app.dependency_overrides[authed_client] = lambda: mock_db

    with TestClient(app) as tc:
        yield tc

    # Pop only the overrides THIS fixture set — never call .clear() here.
    # Using .clear() would wipe overrides set by concurrent async fixtures
    # (e.g. async_client in test_auth_jwks.py) and cause order-dependent failures.
    app.dependency_overrides.pop(verify_supabase_jwt, None)
    app.dependency_overrides.pop(authed_client, None)


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Clear plan-generation rate-limit counters before (and after) every test.

    routes/plans._hourly_calls and ._daily_calls are module-level defaultdict(deque)
    singletons.  Each successful generate_plan call appends a timestamp. Without this
    reset, tests that call the route accumulate entries across the entire pytest session.
    After the 10th call the limit fires, causing unrelated tests to receive 429 instead
    of 200 — a difficult-to-diagnose ordering-dependent flake.

    This fixture is safe to be autouse because:
      - Tests that explicitly test rate-limiting (test_rate_limit.py) pre-fill the
        deques themselves after this fixture clears them.
      - Tests that don't care about rate-limiting get a clean slate on every invocation.
    """
    from playfuel_api.routes.plans import _daily_calls, _hourly_calls

    _hourly_calls.clear()
    _daily_calls.clear()
    yield
    _hourly_calls.clear()
    _daily_calls.clear()


@pytest.fixture()
def client_no_auth() -> TestClient:
    """TestClient with NO dependency overrides.

    Use this to test that unauthenticated requests are rejected correctly.
    No real credentials are needed — HTTPBearer will reject the absent header.
    """
    from playfuel_api.main import app

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
