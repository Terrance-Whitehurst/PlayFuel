"""Geo-agnostic food options regression test.

Root cause: MockPlacesProvider had a Dallas bounding-box gate that returned []
for any coordinates outside the Dallas demo area.  When GOOGLE_PLACES_API_KEY
returned a 4xx/5xx, the provider fell back to MockPlacesProvider, which then
also returned [] — giving every new match "No nearby food options / bag only".

Fix: MockPlacesProvider now applies fixed offsets from the *caller's* lat/lng
so it returns realistic-looking fixtures for ANY city.  GooglePlacesProvider
4xx / 5xx / 401 / timeout paths all fall back to MockPlacesProvider (not []).

These five tests constitute the mandatory regression suite from the Engineering
Lead brief.  They would all have FAILED against the pre-fix codebase.

Test IDs:
  1. test_mock_provider_austin_returns_non_empty_list
  2. test_mock_provider_austin_places_have_austin_coordinates
  3. test_new_austin_match_plan_has_food_options
  4. test_new_austin_match_bag_fallback_false_healthy_gap
  5. test_find_nearby_food_mock_mode_any_city
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── Austin, TX venue — deliberately NOT Dallas demo coords ────────────────────
AUSTIN_LAT = 30.2849
AUSTIN_LNG = -97.7341
AUSTIN_VENUE = "Austin Tennis Center"

# Non-Dallas tournament / match UUIDs — freshly generated, not seeded fixtures.
AUSTIN_TID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
AUSTIN_MID_1 = "a1b2c3d4-e5f6-7890-abcd-ef1234567891"
AUSTIN_MID_2 = "a1b2c3d4-e5f6-7890-abcd-ef1234567892"

_PLAN_PATH = f"/v1/tournaments/{AUSTIN_TID}/plans/generate"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _match(mid: str, start: str, display_order: int) -> dict:
    """Minimal match row dict accepted by MatchRow(**...)."""
    return {
        "id": mid,
        "tournament_id": AUSTIN_TID,
        "scheduled_start": start,
        "estimated_duration_minutes": None,
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "doubles_format": None,
        "age_bracket": "14U",
        "display_order": display_order,
        "round_label": "QF",
        "opponent_label": None,
        "court_label": "Court 3",
        "created_at": "2026-06-01T00:00:00+00:00",
        "updated_at": "2026-06-01T00:00:00+00:00",
        "opponent_player_id": None,
    }


def _two_matches_healthy_gap() -> list[dict]:
    """Two matches with a ~4-hour gap — guarantees non-bag food strategy."""
    return [
        _match(AUSTIN_MID_1, "2026-06-15T09:00:00+00:00", 1),
        _match(AUSTIN_MID_2, "2026-06-15T13:00:00+00:00", 2),
    ]


def _make_austin_db(matches: list[dict]) -> MagicMock:
    """Dispatching MagicMock DB for the generate_plan route with Austin venue."""
    matches_chain = MagicMock()
    (
        matches_chain.select.return_value
        .eq.return_value
        .order.return_value
        .order.return_value
        .execute.return_value.data
    ) = matches

    tournaments_chain = MagicMock()
    (
        tournaments_chain.select.return_value
        .eq.return_value
        .limit.return_value
        .execute.return_value.data
    ) = [{"venue_lat": AUSTIN_LAT, "venue_lng": AUSTIN_LNG, "venue_name": AUSTIN_VENUE}]

    plans_chain = MagicMock()
    plans_chain.upsert.return_value.execute.return_value.data = [{"id": str(uuid4())}]

    # Cache tables (places + LLM) — return empty so they don't interfere.
    empty_chain = MagicMock()
    empty_chain.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []  # noqa: E501
    empty_chain.upsert.return_value.execute.return_value.data = []

    db = MagicMock()

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
            "tournament_places_cache": empty_chain,
            "llm_explanation_cache": empty_chain,
        }.get(name, MagicMock())

    db.table.side_effect = _dispatch
    return db


# ── Unit tests (places layer) ──────────────────────────────────────────────────


def test_mock_provider_austin_returns_non_empty_list() -> None:
    """MockPlacesProvider returns ≥3 places for Austin, TX — NOT [] like pre-fix.

    Pre-fix: Dallas bbox gate → search_nearby(30.28, -97.73, ...) returned [].
    Post-fix: offsets applied to caller's lat/lng → 5 fixture places returned.
    """
    from playfuel_api.services.places import MockPlacesProvider

    results = list(MockPlacesProvider().search_nearby(AUSTIN_LAT, AUSTIN_LNG, 4828, 6))
    assert len(results) >= 3, (
        f"Expected ≥3 places for Austin TX ({AUSTIN_LAT}, {AUSTIN_LNG}); "
        f"got {len(results)} — this is the geo-agnostic regression. "
        "Pre-fix: bbox gate returned []. Post-fix: offset-from-caller returns results."
    )


def test_mock_provider_austin_places_have_austin_coordinates() -> None:
    """Fixture places returned for Austin are offset from Austin, not from Dallas.

    Pre-fix: any results would have had Dallas-centred coordinates (~32.78, -96.80).
    Post-fix: coordinates are offset from the CALLER'S lat/lng (Austin: ~30.28, -97.73).
    """
    from playfuel_api.services.places import MockPlacesProvider

    results = list(MockPlacesProvider().search_nearby(AUSTIN_LAT, AUSTIN_LNG, 4828, 6))
    assert len(results) >= 1, "Need at least 1 result to check coordinates"
    for place in results:
        assert place.lat is not None, f"{place.name} must have a lat"
        assert place.lng is not None, f"{place.name} must have a lng"
        # Offset templates are ≤ ±0.01° — place should be within 0.05° of Austin
        assert abs(place.lat - AUSTIN_LAT) < 0.05, (
            f"Place '{place.name}' lat={place.lat:.4f} is not near Austin "
            f"({AUSTIN_LAT}). Pre-fix would return Dallas-centred coords here."
        )
        assert abs(place.lng - AUSTIN_LNG) < 0.05, (
            f"Place '{place.name}' lng={place.lng:.4f} is not near Austin "
            f"({AUSTIN_LNG}). Pre-fix would return Dallas-centred coords here."
        )


# ── Route-level end-to-end regression tests ───────────────────────────────────


def test_new_austin_match_plan_has_food_options(client_with_auth, mock_db) -> None:
    """Brand-new tournament (non-Dallas UUID) + Austin match → food_options non-empty.

    This is the end-to-end reproduction of the bug the user reported three times:
    new matches outside the Dallas demo showed "No nearby food options / bag only".

    Steps:
      - Tournament UUID: AUSTIN_TID  (not the Dallas demo b0eebc99-... UUID)
      - Venue: Austin, TX (30.2849, -97.7341)
      - Two matches: 9 am + 1 pm (healthy 4-hour gap)
      - MockPlacesProvider wired via find_nearby_food (PLACES_PROVIDER=mock)

    Asserts:
      - 200 response
      - singlesPlans non-empty (plan generated)
      - foodOptions on plan is non-empty (≥1 restaurant listed)
    """
    from playfuel_api.services.places import MockPlacesProvider
    from playfuel_api.services.llm import TemplateProvider

    db = _make_austin_db(_two_matches_healthy_gap())
    mock_db.table.side_effect = db.table.side_effect

    austin_places = list(MockPlacesProvider().search_nearby(AUSTIN_LAT, AUSTIN_LNG, 4828, 6))
    assert len(austin_places) >= 3, (
        "Precondition: MockPlacesProvider must return ≥3 Austin places before the route test"
    )

    with (
        patch("playfuel_api.routes.plans.get_or_fetch_weather", new_callable=AsyncMock) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food", return_value=austin_places),
        patch("playfuel_api.routes.plans.get_llm_provider", return_value=TemplateProvider()),
    ):
        mock_wx.return_value = None
        resp = client_with_auth.post(_PLAN_PATH)

    assert resp.status_code == 200, (
        f"Expected 200 for new Austin tournament/match, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert len(body["singlesPlans"]) >= 1, "Expected ≥1 singlesPlans for 2 matches"

    # Check the first match plan (9am match — has a 4h gap to the 1pm match)
    first_plan = body["singlesPlans"][0]
    assert "foodOptions" in first_plan, "foodOptions key must exist on plan"
    food_options = first_plan.get("foodOptions") or []
    assert len(food_options) >= 1, (
        f"Expected ≥1 food option for new Austin match; got {len(food_options)}. "
        "Pre-fix: geo-agnostic bug returned [] → bag-only fallback → user sees "
        "'No nearby food options, bag food'."
    )


def test_new_austin_match_bag_fallback_false_healthy_gap(client_with_auth, mock_db) -> None:
    """Austin match with healthy 4-hour gap → bagFallbackOnly must be False.

    bagFallbackOnly=True is the user-visible bug ('no nearby food options').
    With a 4-hour gap between matches and ≥3 mock places from Austin coords,
    the rules engine should produce a non-bag food strategy and set
    bagFallbackOnly=False on the generated plan.

    Pre-fix: MockPlacesProvider returned [] for Austin → assemble_food_options
    got empty raw_places → bag_fallback_only=True on every match regardless of gap.
    """
    from playfuel_api.services.places import MockPlacesProvider
    from playfuel_api.services.llm import TemplateProvider

    db = _make_austin_db(_two_matches_healthy_gap())
    mock_db.table.side_effect = db.table.side_effect

    austin_places = list(MockPlacesProvider().search_nearby(AUSTIN_LAT, AUSTIN_LNG, 4828, 6))

    with (
        patch("playfuel_api.routes.plans.get_or_fetch_weather", new_callable=AsyncMock) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food", return_value=austin_places),
        patch("playfuel_api.routes.plans.get_llm_provider", return_value=TemplateProvider()),
    ):
        mock_wx.return_value = None
        resp = client_with_auth.post(_PLAN_PATH)

    assert resp.status_code == 200
    body = resp.json()
    first_plan = body["singlesPlans"][0]

    bag_fallback_only = first_plan.get("bagFallbackOnly", True)
    assert bag_fallback_only is False, (
        "bagFallbackOnly must be False for a match with ≥3 nearby food places "
        "and a 4-hour gap. "
        "Pre-fix: MockPlacesProvider returned [] for Austin coords → "
        "bag_fallback_only=True (user saw 'No nearby food options, bag food')."
    )


# ── find_nearby_food factory test ─────────────────────────────────────────────


def test_find_nearby_food_mock_mode_any_city() -> None:
    """find_nearby_food with mock provider returns ≥3 results for any lat/lng.

    This exercises the full factory path:
      settings.places_provider = 'mock' → MockPlacesProvider.search_nearby()
      → geo-agnostic offset logic → returns fixtures for ANY city.

    Pre-fix: factory only gated on key presence; MockPlacesProvider had a bbox
    gate that returned [] for non-Dallas coords — so even 'mock' mode failed for
    new tournaments.
    Post-fix: MockPlacesProvider is geo-agnostic; 'mock' mode works for any city.
    """
    from playfuel_api.settings import get_settings
    from playfuel_api.services.places import find_nearby_food

    # Force mock provider via settings patch so the test is self-contained
    # regardless of GOOGLE_PLACES_API_KEY presence in the environment.
    with patch.object(get_settings(), "places_provider", "mock"):
        results = find_nearby_food(AUSTIN_LAT, AUSTIN_LNG, tournament_id=None, db_client=None)

    assert len(results) >= 3, (
        f"find_nearby_food(mock, Austin) returned {len(results)} results; expected ≥3. "
        "Pre-fix: MockPlacesProvider bbox gate returned [] for Austin coords."
    )
    assert all(r.provider == "mock" for r in results), (
        "All results must have provider='mock' when PLACES_PROVIDER=mock"
    )
