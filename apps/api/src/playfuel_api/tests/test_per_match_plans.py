"""Tests for per-match plan generation (NUTRITION_FIRST_IA_V1.md §E).

Each match now gets its own Plan entry. The generate_plan route returns:
    { singlesPlans: [Plan, ...], doublesPlans: [Plan, ...] }

Tests (≥6):
    1. Tournament with 2 singles + 1 doubles → singlesPlans.length == 2, doublesPlans.length == 1
    2. Tournament with only singles → doublesPlans == []
    3. Tournament with only doubles → singlesPlans == []
    4. Each Plan has matchId populated and unique
    5. Each Plan has nextAction present (either real or recovery_fallback)
    6. Plans within each array ordered by underlying match scheduled_start ASC
    7. singlesPlans[0].matchType == 'singles'
    8. doublesPlans[0].matchType == 'doubles'
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Shared UUIDs ──────────────────────────────────────────────────────────────

TID = "e0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID_S1 = "e1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID_S2 = "e2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID_D1 = "e3eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

_PLAN_PATH = f"/v1/tournaments/{TID}/plans/generate"


# ── Mock DB helpers ───────────────────────────────────────────────────────────


def _base_match(
    match_id: str,
    format_: str,
    doubles_fmt: str | None,
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
        "format": format_,
        "doubles_format": doubles_fmt,
        "age_bracket": "14U",
        "display_order": display_order,
        "round_label": None,
        "opponent_label": None,
        "court_label": None,
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }


def _make_mock_db(matches: list[dict]) -> MagicMock:
    """Return a per-table dispatching MagicMock for the plans/generate route."""
    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = matches

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"venue_lat": 32.776664, "venue_lng": -96.796988, "venue_name": "SMU Tennis Center"},
    ]

    plans_chain = MagicMock()
    # upsert — OQ-IA-9 fix: route now uses upsert, not insert
    plans_chain.upsert.return_value.execute.return_value.data = [{}]

    mock_db = MagicMock()

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch
    return mock_db


def _run_generate(client_with_auth, mock_db, matches: list[dict]) -> dict:
    """Wire mock_db and POST to generate; return parsed JSON body."""
    db = _make_mock_db(matches)
    mock_db.table.side_effect = db.table.side_effect

    from playfuel_api.services.llm import TemplateProvider
    from playfuel_api.services.places import MockPlacesProvider

    with (
        patch(
            "playfuel_api.routes.plans.get_or_fetch_weather", new_callable=AsyncMock
        ) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food") as mock_places,
        patch(
            "playfuel_api.routes.plans.get_llm_provider",
            return_value=TemplateProvider(),
        ),
    ):
        mock_wx.return_value = None
        mock_places.return_value = list(
            MockPlacesProvider().search_nearby(32.78, -96.80, 4828, 6)
        )
        resp = client_with_auth.post(_PLAN_PATH)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    return resp.json()


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_mixed_tournament_produces_two_singles_one_doubles(client_with_auth, mock_db) -> None:
    """2 singles + 1 doubles → singlesPlans.length == 2, doublesPlans.length == 1."""
    matches = [
        _base_match(MID_S1, "singles", None, "2026-05-15T09:00:00+00:00", 1),
        _base_match(MID_S2, "singles", None, "2026-05-15T13:00:00+00:00", 2),
        _base_match(MID_D1, "doubles", "best_of_3", "2026-05-15T16:00:00+00:00", 3),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    assert len(body["singlesPlans"]) == 2, (
        f"Expected 2 singlesPlans, got {len(body['singlesPlans'])}"
    )
    assert len(body["doublesPlans"]) == 1, (
        f"Expected 1 doublesPlans, got {len(body['doublesPlans'])}"
    )


def test_singles_only_doubles_plans_is_empty_array(client_with_auth, mock_db) -> None:
    """Singles-only tournament → doublesPlans == [] (empty array, not null)."""
    matches = [
        _base_match(MID_S1, "singles", None, "2026-05-15T09:00:00+00:00", 1),
        _base_match(MID_S2, "singles", None, "2026-05-15T13:00:00+00:00", 2),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    assert body["doublesPlans"] == [], (
        f"Expected doublesPlans==[], got {body['doublesPlans']}"
    )
    assert len(body["singlesPlans"]) == 2


def test_doubles_only_singles_plans_is_empty_array(client_with_auth, mock_db) -> None:
    """Doubles-only tournament → singlesPlans == []."""
    matches = [
        _base_match(MID_D1, "doubles", "best_of_3", "2026-05-15T09:00:00+00:00", 1),
        _base_match(MID_S2, "doubles", "pro_set_8", "2026-05-15T13:00:00+00:00", 2),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    assert body["singlesPlans"] == [], (
        f"Expected singlesPlans==[], got {body['singlesPlans']}"
    )
    assert len(body["doublesPlans"]) == 2


def test_each_plan_has_match_id_populated_and_unique(client_with_auth, mock_db) -> None:
    """Each Plan in the arrays has matchId populated and unique."""
    matches = [
        _base_match(MID_S1, "singles", None, "2026-05-15T09:00:00+00:00", 1),
        _base_match(MID_S2, "singles", None, "2026-05-15T13:00:00+00:00", 2),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    all_plans = body["singlesPlans"] + body["doublesPlans"]
    match_ids = [p.get("matchId") for p in all_plans]

    # All populated
    assert all(mid is not None for mid in match_ids), (
        f"All plans must have matchId. Got: {match_ids}"
    )
    # All unique
    assert len(set(match_ids)) == len(match_ids), (
        f"matchIds must be unique across plans. Got: {match_ids}"
    )


def test_each_plan_has_next_action_present(client_with_auth, mock_db) -> None:
    """Each Plan has nextAction populated (either a real event or recovery_fallback)."""
    matches = [
        _base_match(MID_S1, "singles", None, "2026-05-15T09:00:00+00:00", 1),
        _base_match(MID_S2, "singles", None, "2026-05-15T13:00:00+00:00", 2),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    for plan in body["singlesPlans"]:
        next_action = plan.get("nextAction")
        assert next_action is not None, (
            f"Plan {plan.get('matchId')} must have nextAction. Got None."
        )
        assert "title" in next_action, "nextAction must have 'title'"
        assert "detail" in next_action, "nextAction must have 'detail'"
        assert "kind" in next_action, "nextAction must have 'kind'"


def test_plans_ordered_by_scheduled_start_asc(client_with_auth, mock_db) -> None:
    """singlesPlans are ordered by match scheduled_start ASC.

    The route processes matches in the order returned by the DB query
    (display_order ASC, scheduled_start ASC). Plans are appended in that order.
    Ordering is DB-guaranteed, not re-sorted in the route.
    """
    # Pass matches in display_order / scheduled_start ASC order (mirrors DB output)
    matches = [
        _base_match(MID_S1, "singles", None, "2026-05-15T09:00:00+00:00", 1),
        _base_match(MID_S2, "singles", None, "2026-05-15T13:00:00+00:00", 2),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    plans = body["singlesPlans"]
    assert len(plans) == 2
    # Plans are in the same order as the input matches (DB order = correct order)
    assert plans[0].get("matchId") == MID_S1, (
        f"Expected first plan to have matchId={MID_S1} (9am). Got {plans[0].get('matchId')}"
    )
    assert plans[1].get("matchId") == MID_S2, (
        f"Expected second plan to have matchId={MID_S2} (1pm). Got {plans[1].get('matchId')}"
    )


def test_singles_plans_have_singles_match_type(client_with_auth, mock_db) -> None:
    """singlesPlans[0].matchType == 'singles'."""
    matches = [
        _base_match(MID_S1, "singles", None, "2026-05-15T09:00:00+00:00", 1),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    assert body["singlesPlans"][0]["matchType"] == "singles"


def test_doubles_plans_have_doubles_match_type(client_with_auth, mock_db) -> None:
    """doublesPlans[0].matchType == 'doubles'."""
    matches = [
        _base_match(MID_D1, "doubles", "best_of_3", "2026-05-15T09:00:00+00:00", 1),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    assert body["doublesPlans"][0]["matchType"] == "doubles"


def test_each_plan_has_scheduled_start_iso_utc(client_with_auth, mock_db) -> None:
    """Each Plan carries scheduledStart as ISO 8601 UTC matching the match's scheduled_start.

    feat/match-card-time: iOS MatchChip uses scheduledStart + asClockTimeFromISO to display
    device-local clock time.  Previously this field was absent, causing the chip to show —.
    """
    matches = [
        _base_match(MID_S1, "singles", None, "2026-05-15T09:00:00+00:00", 1),
        _base_match(MID_S2, "singles", None, "2026-05-15T13:00:00+00:00", 2),
    ]
    body = _run_generate(client_with_auth, mock_db, matches)

    plans = body["singlesPlans"]
    assert len(plans) == 2

    # Field must be present and non-null for every plan.
    for plan in plans:
        ss = plan.get("scheduledStart")
        assert ss is not None, (
            f"Plan {plan.get('matchId')} is missing scheduledStart. iOS MatchChip will show —."
        )
        # Must be parseable as ISO 8601 (contains 'T' separator and trailing 'Z').
        assert "T" in ss and ss.endswith("Z"), (
            f"scheduledStart must be ISO 8601 UTC (e.g. '2026-05-15T09:00:00Z'). Got: {ss!r}"
        )

    # Values match the two match inputs in order.
    assert plans[0]["scheduledStart"] == "2026-05-15T09:00:00Z", (
        f"Expected first plan scheduledStart='2026-05-15T09:00:00Z'. Got: {plans[0]['scheduledStart']!r}"
    )
    assert plans[1]["scheduledStart"] == "2026-05-15T13:00:00Z", (
        f"Expected second plan scheduledStart='2026-05-15T13:00:00Z'. Got: {plans[1]['scheduledStart']!r}"
    )
