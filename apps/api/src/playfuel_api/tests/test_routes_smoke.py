"""Route smoke tests — /healthz (no auth) + /v1/me (auth required).

Three minimum-acceptance cases per the Task #5 brief:
    1. GET /healthz    → 200 + correct JSON body (no auth needed)
    2. GET /v1/me      → 401 without Bearer token
    3. GET /v1/me      → 200 with mocked auth + mocked Supabase

These tests use conftest.py fixtures:
    client_no_auth    — plain TestClient, no dependency overrides
    client_with_auth  — TestClient with auth + DB deps overridden (no network calls)
    mock_db           — MagicMock for Supabase Client
"""


def test_healthz_unauthed_returns_200(client_no_auth):
    """GET /healthz returns {"status":"ok","rules_version":"1.0.0"} without auth."""
    resp = client_no_auth.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["rules_version"] == "1.0.0"


def test_protected_route_without_token_returns_401(client_no_auth):
    """GET /v1/me without Bearer token → 401 (auth.py raises 401 on missing credentials)."""
    resp = client_no_auth.get("/v1/me")
    assert resp.status_code == 401


def test_protected_route_with_mocked_auth_returns_200(client_with_auth, mock_db):
    """GET /v1/me with mocked auth + mocked Supabase → 200, user record returned.

    conftest.py dependency overrides:
      verify_supabase_jwt → returns TEST_USER_ID (no real JWT validation needed)
      authed_client       → returns mock_db      (no Supabase network call made)

    mock_db is configured here to return a minimal user dict so the /v1/me route
    does not raise HTTP 404 from its empty-data guard.
    """
    # Configure mock chain: client.table("users").select("*").eq("id", ...).execute().data
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11", "email": "test@example.com"}
    ]
    resp = client_with_auth.get("/v1/me")
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
