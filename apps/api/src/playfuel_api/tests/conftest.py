"""Shared pytest fixtures for PlayFuel API tests.

Fixtures:
    mock_db            — MagicMock standing in for the Supabase Client.
    client_with_auth   — FastAPI TestClient with both auth + DB overridden.
    client_no_auth     — Plain TestClient with NO dependency overrides (real HTTPBearer).

Auth override injects TEST_USER_ID so no real JWT secret is required in CI.
DB override prevents any real Supabase network calls during unit / smoke tests.
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

    app.dependency_overrides.clear()


@pytest.fixture()
def client_no_auth() -> TestClient:
    """TestClient with NO dependency overrides.

    Use this to test that unauthenticated requests are rejected correctly.
    No real credentials are needed — HTTPBearer will reject the absent header.
    """
    from playfuel_api.main import app

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
