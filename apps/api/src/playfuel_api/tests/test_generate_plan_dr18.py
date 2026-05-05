"""DR_18 regression: generate_plan accommodation columns must be in tournaments SELECT.

Root cause of production 500 on 2026-05-05T20:01:52Z:
    Migration 0021 added accommodation_lat/lng/kind/address to the tournaments table.
    routes/plans.py:generate_plan() SELECT explicitly requests accommodation_lat,
    accommodation_lng, and accommodation_kind.  Migration 0021 was applied locally but
    NOT to the remote Supabase database.  The execute() call raised:
        APIError: column tournaments.accommodation_lat does not exist (code 42703)
    which propagated as an unhandled exception → 500 on every plan/generate call.

Fix: applied migration 0021 to remote via `supabase db push`.  No code change needed.

Tests:
    DR18_1  Column names for accommodation fields are present in generate_plan source.
            Pure code-level guard: fails immediately if someone removes a column name
            from the SELECT string without also removing the migration dependency note.

    DR18_2  Smoke: generate succeeds when tournament row INCLUDES accommodation fields.
            Validates the full data path — values are read via .get() and passed to
            build_timeline() as acc_lat/acc_lng/acc_kind.

    DR18_3  Smoke: generate succeeds when tournament row OMITS accommodation fields
            (legacy rows pre-migration-0021 have NULL for all four columns).  Confirms
            the graceful fallback via .get() returns None without raising.

DR_18 gate rule (standing): every deploy must confirm ALL local migrations are present
in the remote column of `supabase migration list`.  Not just the three historically
checked (0002, 0007, 0016) — every row must be LOCAL=REMOTE.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

TID = "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID1 = "c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

_MATCH_ROW = {
    "id": MID1,
    "tournament_id": TID,
    "scheduled_start": "2026-05-15T14:00:00+00:00",
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
    "doubles_format": None,
    "is_done": False,
    "round": None,
}

# Tournament row WITH accommodation fields set (migration 0021 scenario).
_TOURNAMENT_WITH_ACCOMMODATION = {
    "venue_lat": 40.7128,
    "venue_lng": -74.0060,
    "venue_name": "NYC Tennis Center",
    "venue_country": "US",
    "preferred_language": None,
    "accommodation_lat": 40.7580,
    "accommodation_lng": -73.9855,
    "accommodation_kind": "hotel",
}

# Tournament row WITHOUT accommodation fields (legacy row / pre-0021 columns NULL).
_TOURNAMENT_WITHOUT_ACCOMMODATION = {
    "venue_lat": 40.7128,
    "venue_lng": -74.0060,
    "venue_name": "NYC Tennis Center",
    "venue_country": None,
    "preferred_language": None,
    # accommodation_* keys absent — simulates pre-0021 remote row
    # .get() returns None gracefully for missing keys.
}


def _build_mock_db(tournament_row: dict) -> MagicMock:
    """Build a fully-wired mock_db for the generate_plan route."""
    mock_db = MagicMock()

    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = [
        _MATCH_ROW
    ]

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        tournament_row
    ]

    # LLM cache: return no cached explanation (miss path).
    llm_cache_chain = MagicMock()
    llm_cache_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

    def _table_dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "llm_explanation_cache": llm_cache_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _table_dispatch
    return mock_db


# ── Test DR18_1 — source-level column guard ───────────────────────────────────

def test_dr18_1_accommodation_columns_present_in_generate_plan_source():
    """The generate_plan tournament SELECT must include all accommodation columns (0021).

    If this test fails, someone removed an accommodation column from the SELECT string
    without removing the migration 0021 dependency — that would re-introduce the 500.
    Update both the SELECT string and this test together.
    """
    from playfuel_api.routes import plans as plans_module

    source = inspect.getsource(plans_module.generate_plan)

    required = [
        "accommodation_lat",
        "accommodation_lng",
        "accommodation_kind",
        # Baseline columns (pre-0021) also validated for completeness
        "venue_lat",
        "venue_lng",
        "venue_name",
        "venue_country",
        "preferred_language",
    ]
    missing = [col for col in required if col not in source]
    assert not missing, (
        f"generate_plan tournament SELECT is missing column(s): {missing}. "
        "Add them back to the SELECT string AND confirm migration 0021 is applied to remote."
    )


# ── Test DR18_2 — smoke with accommodation set ───────────────────────────────

def test_dr18_2_generate_plan_succeeds_with_accommodation_fields(client_with_auth, mock_db):
    """POST plans/generate returns 200 when tournament row has accommodation_lat/lng/kind set.

    Validates the data path introduced by ACCOMMODATIONS_V1.md and migration 0021:
    acc_lat / acc_lng / acc_kind are read from the tournament row and forwarded to
    build_timeline() — plan generates without crash.
    """
    from playfuel_api.services.places import MockPlacesProvider

    mock_db.table.side_effect = _build_mock_db(_TOURNAMENT_WITH_ACCOMMODATION).table.side_effect

    with (
        patch("playfuel_api.routes.plans.get_or_fetch_weather", new_callable=AsyncMock) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food") as mock_places,
    ):
        mock_wx.return_value = None
        mock_places.return_value = list(
            MockPlacesProvider().search_nearby(40.71, -74.01, 4828, 6)
        )
        resp = client_with_auth.post(f"/v1/tournaments/{TID}/plans/generate")

    assert resp.status_code == 200, f"Expected 200 with accommodation fields set; got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "singlesPlans" in body
    assert len(body["singlesPlans"]) >= 1
    # placesUnavailable must be False when find_nearby_food returns mock results.
    plan = body["singlesPlans"][0]
    assert plan.get("placesUnavailable") is False, "placesUnavailable must be False for mock-places path"


# ── Test DR18_3 — smoke without accommodation (legacy row graceful fallback) ──

def test_dr18_3_generate_plan_succeeds_without_accommodation_fields(client_with_auth, mock_db):
    """POST plans/generate returns 200 when tournament row lacks accommodation columns.

    Simulates a pre-migration-0021 tournament row that has no accommodation_* keys.
    The route uses .get() with no default, so missing keys return None — plan generates
    without crash.  This is the pre-0021 contract preserved.
    """
    from playfuel_api.services.places import MockPlacesProvider

    mock_db.table.side_effect = _build_mock_db(_TOURNAMENT_WITHOUT_ACCOMMODATION).table.side_effect

    with (
        patch("playfuel_api.routes.plans.get_or_fetch_weather", new_callable=AsyncMock) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food") as mock_places,
    ):
        mock_wx.return_value = None
        mock_places.return_value = list(
            MockPlacesProvider().search_nearby(40.71, -74.01, 4828, 6)
        )
        resp = client_with_auth.post(f"/v1/tournaments/{TID}/plans/generate")

    assert resp.status_code == 200, f"Expected 200 without accommodation fields; got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "singlesPlans" in body
    assert len(body["singlesPlans"]) >= 1
