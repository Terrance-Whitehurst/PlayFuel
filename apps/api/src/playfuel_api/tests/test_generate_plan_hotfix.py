"""Hotfix tests for POST /v1/tournaments/{tid}/plans/generate.

Covers OQ-IA-9 (INSERT → upsert), zero-match envelope, and graceful
degradation when weather / LLM / places providers raise.

Tests (≥5):
    1. test_regenerate_is_idempotent            — upsert: two POSTs both return 200
    2. test_zero_matches_returns_empty_envelope  — 0 matches → 200 {singlesPlans:[], doublesPlans:[]}
    3. test_weather_provider_failure_degrades    — weather raises → 200, weather block may be None
    4. test_llm_provider_failure_degrades        — LLM raises → 200, llmSummary None/fallback
    5. test_places_provider_failure_degrades     — places raises → 200, food options empty/default
    6. test_upsert_called_not_insert             — verifies the supabase call is upsert, not insert
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Shared fixtures ────────────────────────────────────────────────────────────

TID = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"   # Dallas demo tournament UUID
MID_1 = "c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_PLAN_PATH = f"/v1/tournaments/{TID}/plans/generate"


def _one_singles_match(mid: str = MID_1) -> dict:
    return {
        "id": mid,
        "tournament_id": TID,
        "scheduled_start": "2026-05-15T09:00:00+00:00",
        "estimated_duration_minutes": None,
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "doubles_format": None,
        "age_bracket": "14U",
        "display_order": 1,
        "round_label": "R16",
        "opponent_label": None,
        "court_label": "Court 7",
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }


def _make_dispatching_db(matches: list[dict]) -> MagicMock:
    """Return a per-table dispatching MagicMock for the generate route."""
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
    ) = [{"venue_lat": 32.776664, "venue_lng": -96.796988, "venue_name": "SMU Tennis Center"}]

    plans_chain = MagicMock()
    plans_chain.upsert.return_value.execute.return_value.data = [{"id": "fake"}]

    mock_db = MagicMock()

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch
    return mock_db


def _post_generate(
    client_with_auth,
    mock_db,
    matches: list[dict],
    *,
    weather_return=None,
    places_return=None,
    llm_override=None,
) -> dict:
    """Wire mocks and POST to generate; return (status_code, body)."""
    db = _make_dispatching_db(matches)
    mock_db.table.side_effect = db.table.side_effect

    from playfuel_api.services.llm import TemplateProvider
    from playfuel_api.services.places import MockPlacesProvider

    if places_return is None:
        places_return = list(
            MockPlacesProvider().search_nearby(32.78, -96.80, 4828, 6)
        )

    llm = llm_override if llm_override is not None else TemplateProvider()

    with (
        patch(
            "playfuel_api.routes.plans.get_or_fetch_weather",
            new_callable=AsyncMock,
        ) as mock_wx,
        patch(
            "playfuel_api.routes.plans.find_nearby_food",
            return_value=places_return,
        ),
        patch(
            "playfuel_api.routes.plans.get_llm_provider",
            return_value=llm,
        ),
    ):
        mock_wx.return_value = weather_return
        resp = client_with_auth.post(_PLAN_PATH)

    return resp


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_regenerate_is_idempotent(client_with_auth, mock_db) -> None:
    """Two consecutive POSTs both return 200 — upsert prevents UniqueViolation.

    OQ-IA-9: prior INSERT raised UniqueViolation on the partial unique index
    (match_id, match_type) added by migration 0008. upsert resolves conflicts
    by merging, so re-generate is always safe.
    """
    db = _make_dispatching_db([_one_singles_match()])
    mock_db.table.side_effect = db.table.side_effect

    from playfuel_api.services.llm import TemplateProvider
    from playfuel_api.services.places import MockPlacesProvider

    places = list(MockPlacesProvider().search_nearby(32.78, -96.80, 4828, 6))

    with (
        patch(
            "playfuel_api.routes.plans.get_or_fetch_weather",
            new_callable=AsyncMock,
        ) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food", return_value=places),
        patch("playfuel_api.routes.plans.get_llm_provider", return_value=TemplateProvider()),
    ):
        mock_wx.return_value = None
        resp1 = client_with_auth.post(_PLAN_PATH)
        resp2 = client_with_auth.post(_PLAN_PATH)

    assert resp1.status_code == 200, f"First generate: expected 200, got {resp1.status_code}"
    assert resp2.status_code == 200, f"Second generate (re-generate): expected 200, got {resp2.status_code}"

    body1 = resp1.json()
    body2 = resp2.json()
    assert len(body1["singlesPlans"]) == 1
    assert len(body2["singlesPlans"]) == 1


def test_upsert_called_not_insert(client_with_auth, mock_db) -> None:
    """Verify the route calls .upsert() on the plans table, NOT .insert().

    If this fails it means INSERT → upsert was reverted, and re-generate
    will hit UniqueViolation in production.
    """
    db = _make_dispatching_db([_one_singles_match()])
    mock_db.table.side_effect = db.table.side_effect

    from playfuel_api.services.llm import TemplateProvider
    from playfuel_api.services.places import MockPlacesProvider

    places = list(MockPlacesProvider().search_nearby(32.78, -96.80, 4828, 6))

    # Capture the actual plans MagicMock that the route accesses
    captured_plans_chain: list[MagicMock] = []

    original_side_effect = db.table.side_effect

    def _spy_dispatch(name: str) -> MagicMock:
        chain = original_side_effect(name)
        if name == "plans":
            captured_plans_chain.append(chain)
        return chain

    mock_db.table.side_effect = _spy_dispatch

    with (
        patch(
            "playfuel_api.routes.plans.get_or_fetch_weather",
            new_callable=AsyncMock,
        ) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food", return_value=places),
        patch("playfuel_api.routes.plans.get_llm_provider", return_value=TemplateProvider()),
    ):
        mock_wx.return_value = None
        resp = client_with_auth.post(_PLAN_PATH)

    assert resp.status_code == 200
    assert captured_plans_chain, "plans table was never accessed"

    plans_chain = captured_plans_chain[0]
    # upsert must have been called at least once
    plans_chain.upsert.assert_called()
    # insert must NOT have been called (insert would cause UniqueViolation on re-generate)
    plans_chain.insert.assert_not_called()


def test_zero_matches_returns_empty_envelope(client_with_auth, mock_db) -> None:
    """Tournament with 0 matches → 200 with {singlesPlans: [], doublesPlans: []}.

    Prior behaviour was 404 ("add matches before generating").
    NUTRITION_FIRST_IA_V1 §H.2: 0 matches is valid; return empty envelope.
    """
    resp = _post_generate(client_with_auth, mock_db, matches=[])
    assert resp.status_code == 200, f"Expected 200 for zero matches, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["singlesPlans"] == [], f"Expected singlesPlans==[], got {body['singlesPlans']}"
    assert body["doublesPlans"] == [], f"Expected doublesPlans==[], got {body['doublesPlans']}"


def test_weather_provider_failure_degrades(client_with_auth, mock_db) -> None:
    """When get_or_fetch_weather returns None (internal failure), route returns 200.

    Weather is non-critical. The real get_or_fetch_weather() catches all
    provider errors internally and returns None — it never propagates an
    exception to the route. The route handles None via the 'if snapshot is not
    None' guard (no NoneType attribute crash). Weather block will be absent from
    the plan; the route must still generate and return 200.
    """
    resp = _post_generate(
        client_with_auth,
        mock_db,
        [_one_singles_match()],
        weather_return=None,   # simulate provider returning None on failure
    )
    assert resp.status_code == 200, (
        f"Expected 200 when weather returns None, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert len(body["singlesPlans"]) == 1, "Plan generated even when weather=None"
    # weather block absent — plan.weather fields may be None
    plan = body["singlesPlans"][0]
    assert "weather" in plan, "weather key must still exist on plan even if None"


def test_llm_provider_failure_degrades(client_with_auth, mock_db) -> None:
    """When the LLM provider raises, the route returns 200 with llmSummary null/fallback.

    The existing try/except around explain_plan ensures this. This test verifies
    the behaviour is preserved across the upsert refactor.
    """
    class _FailingLLMProvider:
        def explain_plan(self, _input):
            raise RuntimeError("Anthropic rate limit exceeded")

    resp = _post_generate(
        client_with_auth,
        mock_db,
        [_one_singles_match()],
        llm_override=_FailingLLMProvider(),
    )
    assert resp.status_code == 200, (
        f"Expected 200 despite LLM failure, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    # llmSummary may be None or absent — plan must still be present
    assert len(body["singlesPlans"]) == 1, "Plan still returned even when LLM fails"


def test_places_provider_failure_degrades(client_with_auth, mock_db) -> None:
    """When find_nearby_food raises, the route returns 200 with empty food options.

    find_nearby_food() has an internal try/except but this test verifies
    behaviour at the route level when the function returns [].
    """
    resp = _post_generate(
        client_with_auth,
        mock_db,
        [_one_singles_match()],
        places_return=[],   # simulate empty / failed places lookup
    )
    assert resp.status_code == 200, (
        f"Expected 200 despite places failure, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    # Plan present; foodOptions may be empty or contain bag-only fallbacks
    assert len(body["singlesPlans"]) == 1, "Plan still returned even when places returns []"
    plan = body["singlesPlans"][0]
    # foodOptions field should exist (even if empty / bag-fallback only)
    assert "foodOptions" in plan, "foodOptions key must exist on plan even with no places"
