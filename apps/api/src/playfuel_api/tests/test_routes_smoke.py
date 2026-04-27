"""Route smoke tests — /healthz, /v1/me, and plans generate endpoint.

Minimum-acceptance cases:
    1. GET  /healthz    → 200 + correct JSON body (no auth needed)
    2. GET  /v1/me      → 401 without Bearer token
    3. GET  /v1/me      → 200 with mocked auth + mocked Supabase
    4. POST /v1/tournaments/{tid}/plans/generate → 200; foodOptions not null (Phase 5)

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


def test_generate_plan_food_options_not_null(client_with_auth, mock_db):
    """POST plans/generate returns foodOptions list (Phase 5 smoke).

    Patches:
      - find_nearby_food  → MockPlacesProvider Dallas fixture (3 places)
      - get_or_fetch_weather → None (skip async weather; keeps test synchronous)

    Verifies that foodOptions in the response is non-null and has ≥1 entry
    when scenarios produce non-bag_only buckets (Dallas gap = 240 min → light_meal).
    """
    from unittest.mock import MagicMock, AsyncMock, patch
    from datetime import datetime, timezone

    TID = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    MID1 = "c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    MID2 = "d0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

    match1 = {
        "id": MID1,
        "tournament_id": TID,
        "scheduled_start": "2026-05-15T14:00:00+00:00",
        "estimated_duration_minutes": None,
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "age_bracket": "14U",
        "display_order": 1,
        "round_label": "R16",
        "opponent_label": None,
        "court_label": "Court 7",
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }
    match2 = {
        **match1,
        "id": MID2,
        "scheduled_start": "2026-05-15T18:00:00+00:00",  # 4 hr gap → light_meal
        "display_order": 2,
        "round_label": "QF",
        "court_label": None,
    }

    # Build per-table mock dispatch
    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = [
        match1, match2
    ]

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"venue_lat": 32.776664, "venue_lng": -96.796988}
    ]

    plans_chain = MagicMock()
    plans_chain.insert.return_value.execute.return_value.data = [{}]

    def _table_dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _table_dispatch

    with (
        patch("playfuel_api.routes.plans.get_or_fetch_weather", new_callable=AsyncMock) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food") as mock_places,
    ):
        mock_wx.return_value = None  # no weather — keeps test simple

        from playfuel_api.services.places import MockPlacesProvider
        mock_places.return_value = list(
            MockPlacesProvider().search_nearby(32.78, -96.80, 4828, 6)
        )

        resp = client_with_auth.post(f"/v1/tournaments/{TID}/plans/generate")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    plan = body["plan"]
    assert plan["foodOptions"] is not None, "foodOptions must not be None after Phase 5"
    assert len(plan["foodOptions"]) >= 1, f"Expected ≥1 food option, got {len(plan['foodOptions'])}"
    # Sanity-check first option shape
    opt = plan["foodOptions"][0]
    assert "name" in opt
    assert "category" in opt
    assert "recommendedOrder" in opt
    assert "provider" in opt
    assert opt["provider"] == "mock"
