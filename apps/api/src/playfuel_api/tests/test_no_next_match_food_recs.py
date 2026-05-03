"""Regression tests — last-match food recommendations (fix/per-match-food-recs).

Bug: When a tournament has only one match (or for the LAST match in any
tournament), §G.5 sets food_strategy=None on all ScenarioPlan objects because
there is no next match and no gap to compute.  This caused food_buckets=[] in
the plan assembly loop → assemble_food_options(raw_places, []) returned
([], bag_fallback_only=True) → iOS showed the bag-fallback banner instead of
nearby restaurant recommendations.

Fix: In routes/plans.py, when food_buckets is empty AND raw_places is non-empty,
fall back to ["quick_pickup"] so venue food options still surface.  The timing
semantics in each ScenarioPlan (food_strategy=None) remain correct.

Named tests (3):
    test_single_match_tournament_has_food_options
    test_last_match_of_multi_match_tournament_has_food_options
    test_no_raw_places_still_yields_bag_fallback

Existing §G.5 unit tests in test_scenarios_no_next_match.py are NOT updated —
they test ScenarioPlan.food_strategy=None (scenario layer), which remains
correct and unchanged.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

TID = "f0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID_1 = "f1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID_2 = "f2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

_PLAN_PATH = f"/v1/tournaments/{TID}/plans/generate"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _match(
    match_id: str,
    scheduled_start: str,
    display_order: int,
) -> dict:
    return {
        "id": match_id,
        "tournament_id": TID,
        "scheduled_start": scheduled_start,
        "estimated_duration_minutes": None,
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "doubles_format": None,
        "age_bracket": "14U",
        "display_order": display_order,
        "round_label": None,
        "opponent_label": None,
        "court_label": None,
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }


def _make_mock_db(matches: list[dict]) -> MagicMock:
    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = matches

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"venue_lat": 26.461319, "venue_lng": -80.072948, "venue_name": "Delray Beach Tennis Center"},
    ]

    plans_chain = MagicMock()
    plans_chain.upsert.return_value.execute.return_value.data = [{}]

    llm_cache_chain = MagicMock()
    llm_cache_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    llm_cache_chain.upsert.return_value.execute.return_value.data = [{}]

    mock_db = MagicMock()

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
            "llm_explanation_cache": llm_cache_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch
    return mock_db


def _run_generate(client_with_auth, mock_db, matches: list[dict], raw_places=None) -> dict:
    """POST to generate with mocked weather + places; return parsed JSON body."""
    db = _make_mock_db(matches)
    mock_db.table.side_effect = db.table.side_effect

    from playfuel_api.services.llm import TemplateProvider
    from playfuel_api.services.places import MockPlacesProvider

    if raw_places is None:
        # MockPlacesProvider only returns fixtures within ±0.5° of Dallas (32.78, -96.80).
        # Always use Dallas coords here — venue_lat/venue_lng in the tournament fixture
        # are irrelevant since find_nearby_food is patched to return raw_places directly.
        raw_places = list(MockPlacesProvider().search_nearby(32.78, -96.80, 4828, 6))

    with (
        patch(
            "playfuel_api.routes.plans.get_or_fetch_weather", new_callable=AsyncMock
        ) as mock_wx,
        patch(
            "playfuel_api.routes.plans.find_nearby_food",
            return_value=raw_places,
        ),
        patch(
            "playfuel_api.routes.plans.get_llm_provider",
            return_value=TemplateProvider(),
        ),
    ):
        mock_wx.return_value = None
        resp = client_with_auth.post(_PLAN_PATH)

    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.text}"
    )
    return resp.json()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_single_match_tournament_has_food_options(client_with_auth, mock_db) -> None:
    """1-match tournament (last match = only match) must have food_options populated.

    §G.5 no_next_match: the match has no next match, so all ScenarioPlan objects
    have food_strategy=None.  The plan assembly layer must fall back to quick_pickup
    so nearby restaurant recommendations still surface.

    Root cause of the original bug: user added match 1, saw no food recs.
    After adding match 2, match 1 got food recs but match 2 didn't.
    """
    matches = [
        _match(MID_1, "2026-05-15T09:00:00+00:00", 1),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    plans = body["singlesPlans"]
    assert len(plans) == 1, f"Expected 1 singlesPlan, got {len(plans)}"

    plan = plans[0]
    food_options = plan.get("foodOptions") or []
    bag_fallback = plan.get("bagFallbackOnly", True)

    assert len(food_options) > 0, (
        "Single-match tournament: foodOptions must be non-empty. "
        "Got empty list — §G.5 no_next_match fallback not applied."
    )
    assert bag_fallback is False, (
        "Single-match tournament: bagFallbackOnly must be False when raw_places is available. "
        f"Got {bag_fallback!r}."
    )


def test_last_match_of_multi_match_tournament_has_food_options(
    client_with_auth, mock_db
) -> None:
    """Last match of a 2-match tournament must also have food_options populated.

    Match 1 (9am) has a next match → food_buckets derived from gap-based scenarios.
    Match 2 (1pm) has no next match → §G.5 path → food_buckets=[] without the fix.
    Both plans must have non-empty foodOptions after the fix.
    """
    matches = [
        _match(MID_1, "2026-05-15T09:00:00+00:00", 1),
        _match(MID_2, "2026-05-15T13:00:00+00:00", 2),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    plans = body["singlesPlans"]
    assert len(plans) == 2, f"Expected 2 singlesPlans, got {len(plans)}"

    # Match 1 (9am, has next match) — food recs must be present.
    plan_m1 = plans[0]
    food_m1 = plan_m1.get("foodOptions") or []
    assert len(food_m1) > 0, (
        "Match 1 (has next match): foodOptions must be non-empty. "
        f"Got {food_m1!r}."
    )

    # Match 2 (1pm, no next match — §G.5 path) — food recs must also be present.
    plan_m2 = plans[1]
    food_m2 = plan_m2.get("foodOptions") or []
    bag_m2 = plan_m2.get("bagFallbackOnly", True)

    assert len(food_m2) > 0, (
        "Match 2 (last match, §G.5 no_next_match): foodOptions must be non-empty. "
        "Got empty list — §G.5 no_next_match fallback not applied to last match."
    )
    assert bag_m2 is False, (
        f"Last match bagFallbackOnly must be False when raw_places is available. Got {bag_m2!r}."
    )


def test_no_raw_places_still_yields_bag_fallback(client_with_auth, mock_db) -> None:
    """When raw_places is empty, bag_fallback_only=True must still hold.

    The no_next_match fallback is conditioned on raw_places being non-empty.
    If Google Places returns nothing (no venue coords, quota exhausted, etc.),
    the plan correctly falls back to bag food with bagFallbackOnly=True.
    This is the correct defensive behavior — don't show an empty restaurant
    list when no places are available.
    """
    matches = [
        _match(MID_1, "2026-05-15T09:00:00+00:00", 1),
    ]
    # Pass empty raw_places list — simulates no Places results.
    body = _run_generate(client_with_auth, mock_db, matches, raw_places=[])

    plans = body["singlesPlans"]
    assert len(plans) == 1

    plan = plans[0]
    food_options = plan.get("foodOptions") or []
    bag_fallback = plan.get("bagFallbackOnly", False)

    assert food_options == [], (
        f"No raw_places: foodOptions must be empty. Got {food_options!r}."
    )
    assert bag_fallback is True, (
        f"No raw_places: bagFallbackOnly must be True. Got {bag_fallback!r}."
    )
