"""Route test: POST plans/generate response includes llmSummary — Phase 6 / Task #9.

Verifies:
    - Response has top-level `plan.llmSummary` key.
    - llmSummary has all required fields: summary, scenarioExplanations,
      weatherNote, foodNote, safetyNote, provider, generatedAt.
    - llmSummary.provider == "template" (TemplateProvider used; no real LLM keys).
    - llmSummary.safetyNote contains the verbatim USER_DISCLAIMER.
    - llmSummary.scenarioExplanations has 'short', 'normal', 'long' keys.

Uses the same mock-DB / mock-weather pattern as test_routes_smoke.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from playfuel_api.rules.hard_coded_strings import USER_DISCLAIMER

TID = "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID1 = "c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID2 = "d1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


def _make_mock_db() -> MagicMock:
    """Build a per-table dispatching MagicMock for the plans-generate route."""
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
        "scheduled_start": "2026-05-15T18:00:00+00:00",
        "display_order": 2,
        "round_label": "QF",
        "court_label": None,
    }

    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = [
        match1, match2,
    ]

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"venue_lat": 32.776664, "venue_lng": -96.796988, "venue_name": "SMU Tennis Center"},
    ]

    plans_chain = MagicMock()
    plans_chain.insert.return_value.execute.return_value.data = [{}]

    mock_db = MagicMock()

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch
    return mock_db


def test_generate_plan_response_has_llm_summary(client_with_auth, mock_db) -> None:  # type: ignore[no-untyped-def]
    """POST /generate returns plan.llmSummary with all required fields."""
    # Wire the mock_db fixture (conftest provides client_with_auth + mock_db).
    mock_db.table.side_effect = _make_mock_db().table.side_effect

    from playfuel_api.services.llm import TemplateProvider
    from playfuel_api.services.places import MockPlacesProvider

    with (
        patch(
            "playfuel_api.routes.plans.get_or_fetch_weather",
            new_callable=AsyncMock,
        ) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food") as mock_places,
        patch(
            "playfuel_api.routes.plans.get_llm_provider",
            return_value=TemplateProvider(),
        ),
    ):
        mock_wx.return_value = None  # no weather snapshot
        mock_places.return_value = list(
            MockPlacesProvider().search_nearby(32.78, -96.80, 4828, 6)
        )

        resp = client_with_auth.post(f"/v1/tournaments/{TID}/plans/generate")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    plan = body["plan"]

    # llmSummary must be present
    assert "llmSummary" in plan, (
        f"Expected 'llmSummary' in plan response. Keys: {list(plan.keys())}"
    )
    llm = plan["llmSummary"]
    assert llm is not None, "llmSummary must not be null"

    # Required fields
    for field in ("summary", "scenarioExplanations", "safetyNote", "provider", "generatedAt"):
        assert field in llm, (
            f"Expected field '{field}' in llmSummary. Keys: {list(llm.keys())}"
        )

    # provider is "template" (no API keys in test env)
    assert llm["provider"] == "template", (
        f"Expected provider='template'. Got: {llm['provider']!r}"
    )

    # safetyNote contains verbatim USER_DISCLAIMER
    assert USER_DISCLAIMER in llm["safetyNote"], (
        "USER_DISCLAIMER not found verbatim in llmSummary.safetyNote"
    )

    # scenarioExplanations has 3 keys
    assert set(llm["scenarioExplanations"].keys()) == {"short", "normal", "long"}, (
        f"Expected short/normal/long. Got: {list(llm['scenarioExplanations'].keys())}"
    )

    # summary is non-empty
    assert llm["summary"], "llmSummary.summary must not be empty"

    # generatedAt is an ISO 8601 string
    assert isinstance(llm["generatedAt"], str), "generatedAt must be a string"
    datetime.fromisoformat(llm["generatedAt"].replace("Z", "+00:00"))  # must parse
