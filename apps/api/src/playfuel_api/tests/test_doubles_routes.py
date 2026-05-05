"""Doubles integration — route-level tests (DOUBLES_SPEC_V1.md §A.2 + §D.1).

Acceptance criteria exercised here (from the Engineering brief §4–§6):

  §4  POST /v1/tournaments/{tid}/matches — doubles_format validation:
      a) singles + doubles_format=null        → 201 ✓
      b) singles + doubles_format="best_of_3" → 400 ✗
      c) doubles + doubles_format=null        → 400 ✗
      d) doubles + doubles_format="bogus"     → 400 ✗
      e) doubles + doubles_format="best_of_3" → 201 ✓
      f) doubles + doubles_format="pro_set_8" → 201 ✓

  §5  POST /v1/tournaments/{tid}/plans/generate — envelope shape (arrays v2.0):
      g) singles-only tournament → singlesPlans non-empty, doublesPlans == []
      h) singles plan has matchType == 'singles'
      i) doubles-only tournament → singlesPlans == [], doublesPlans non-empty
      j) doubles plan has matchType == 'doubles'

Uses the same mock_db / client_with_auth fixtures from conftest.py.
All mock paths prevent real Supabase network calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Shared UUIDs ──────────────────────────────────────────────────────────────

TID = "b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID1 = "c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID2 = "d2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

_MATCH_PATH = f"/v1/tournaments/{TID}/matches"
_PLAN_PATH = f"/v1/tournaments/{TID}/plans/generate"


# ── Helper: build a mock_db wired for the matches.insert call ─────────────────


def _wire_match_insert(mock_db: MagicMock, return_row: dict, draw_size: int = 32) -> None:
    """Configure mock_db so POST /matches works (tournaments draw_size lookup + matches insert).

    Updated for draw-size-spec: create_match now fetches tournaments.draw_size first,
    then inserts into matches. Both table calls need wired mock chains.
    """
    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"draw_size": draw_size}
    ]

    matches_chain = MagicMock()
    # Round progression uniqueness check: no existing match in this stream → []
    # Chain: .select("id").eq.eq.eq.limit(1).execute().data
    (
        matches_chain.select.return_value
        .eq.return_value
        .eq.return_value
        .eq.return_value
        .limit.return_value
        .execute.return_value.data
    ) = []
    matches_chain.insert.return_value.execute.return_value.data = [return_row]

    mock_db.table.side_effect = lambda name: {
        "tournaments": tournaments_chain,
        "matches": matches_chain,
    }.get(name, MagicMock())


# ── Helper: build a mock_db for the plan generate route ──────────────────────


def _make_plan_mock_db(matches: list[dict]) -> MagicMock:
    """Return a per-table dispatching MagicMock for the plans/generate route."""
    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = matches

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"venue_lat": 32.776664, "venue_lng": -96.796988, "venue_name": "SMU Tennis Center"},
    ]

    plans_chain = MagicMock()
    plans_chain.insert.return_value.execute.return_value.data = [{}]

    mock_db = MagicMock()

    def _dispatch(name: str) -> MagicMock:
        return {"matches": matches_chain, "tournaments": tournaments_chain, "plans": plans_chain}.get(
            name, MagicMock()
        )

    mock_db.table.side_effect = _dispatch
    return mock_db


def _base_match(format_: str, doubles_fmt: str | None, display_order: int = 1) -> dict:
    return {
        "id": MID1,
        "tournament_id": TID,
        "scheduled_start": "2026-05-15T14:00:00+00:00",
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


# ─────────────────────────────────────────────────────────────────────────────
# §4 — Doubles-format validation on POST /matches
# ─────────────────────────────────────────────────────────────────────────────


def test_match_create_singles_no_doubles_format_returns_201(client_with_auth, mock_db):
    """§4a: format='singles', doubles_format=null → 201 Created."""
    _wire_match_insert(
        mock_db,
        return_row={
            "id": MID1,
            "tournament_id": TID,
            "scheduled_start": "2026-05-15T14:00:00+00:00",
            "format": "singles",
            "doubles_format": None,
        },
    )
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={"scheduled_start": "2026-05-15T14:00:00+00:00", "format": "singles", "round": 32},
    )
    assert resp.status_code == 201, resp.text


def test_match_create_singles_with_doubles_format_returns_400(client_with_auth, mock_db):
    """§4b: format='singles', doubles_format='best_of_3' → 400 Bad Request."""
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={
            "scheduled_start": "2026-05-15T14:00:00+00:00",
            "format": "singles",
            "doubles_format": "best_of_3",
            "round": 32,
        },
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json().get("detail", "")
    assert "doubles_format" in detail.lower() or "null" in detail.lower(), (
        f"400 detail should mention doubles_format constraint. Got: {detail!r}"
    )


def test_match_create_doubles_no_format_returns_400(client_with_auth, mock_db):
    """§4c: format='doubles', doubles_format=null → 400 Bad Request."""
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={
            "scheduled_start": "2026-05-15T14:00:00+00:00",
            "format": "doubles",
            "round": 32,
            # doubles_format intentionally omitted → null
        },
    )
    assert resp.status_code == 400, resp.text
    detail = resp.json().get("detail", "")
    assert "doubles_format" in detail.lower() or "best_of_3" in detail.lower(), (
        f"400 detail should mention doubles_format requirement. Got: {detail!r}"
    )


def test_match_create_doubles_bogus_format_returns_400(client_with_auth, mock_db):
    """§4d: format='doubles', doubles_format='bogus' → 400 Bad Request."""
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={
            "scheduled_start": "2026-05-15T14:00:00+00:00",
            "format": "doubles",
            "doubles_format": "bogus",
            "round": 32,
        },
    )
    assert resp.status_code == 400, resp.text


def test_match_create_doubles_best_of_3_returns_201(client_with_auth, mock_db):
    """§4e: format='doubles', doubles_format='best_of_3' → 201 Created."""
    _wire_match_insert(
        mock_db,
        return_row={
            "id": MID1,
            "tournament_id": TID,
            "scheduled_start": "2026-05-15T14:00:00+00:00",
            "format": "doubles",
            "doubles_format": "best_of_3",
        },
    )
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={
            "scheduled_start": "2026-05-15T14:00:00+00:00",
            "format": "doubles",
            "doubles_format": "best_of_3",
            "round": 32,
        },
    )
    assert resp.status_code == 201, resp.text


def test_match_create_doubles_pro_set_8_returns_201(client_with_auth, mock_db):
    """§4f: format='doubles', doubles_format='pro_set_8' → 201 Created."""
    _wire_match_insert(
        mock_db,
        return_row={
            "id": MID1,
            "tournament_id": TID,
            "scheduled_start": "2026-05-15T14:00:00+00:00",
            "format": "doubles",
            "doubles_format": "pro_set_8",
        },
    )
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={
            "scheduled_start": "2026-05-15T14:00:00+00:00",
            "format": "doubles",
            "doubles_format": "pro_set_8",
            "round": 32,
        },
    )
    assert resp.status_code == 201, resp.text


# ─────────────────────────────────────────────────────────────────────────────
# §5 — Plan generate envelope shape
# ─────────────────────────────────────────────────────────────────────────────


def test_generate_plan_singles_only_doubles_plan_is_null(client_with_auth, mock_db):
    """§5g+h: Singles-only tournament → singlesPlans non-empty, doublesPlans == []."""
    singles_match = _base_match("singles", None)
    singles_match2 = {
        **singles_match,
        "id": MID2,
        "scheduled_start": "2026-05-15T18:00:00+00:00",
        "display_order": 2,
    }

    db = _make_plan_mock_db([singles_match, singles_match2])
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

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "singlesPlans" in body, f"Expected 'singlesPlans' key. Got: {list(body.keys())}"
    assert "doublesPlans" in body, f"Expected 'doublesPlans' key. Got: {list(body.keys())}"
    assert len(body["singlesPlans"]) > 0, "singlesPlans must be non-empty for singles-only tournament"
    assert body["doublesPlans"] == [], "doublesPlans must be [] for singles-only tournament"


def test_generate_plan_singles_match_type_field(client_with_auth, mock_db):
    """§5h: singlesPlans[0].matchType == 'singles'."""
    singles_match = _base_match("singles", None)
    singles_match2 = {
        **singles_match,
        "id": MID2,
        "scheduled_start": "2026-05-15T18:00:00+00:00",
        "display_order": 2,
    }

    db = _make_plan_mock_db([singles_match, singles_match2])
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

    assert resp.status_code == 200, resp.text
    plan = resp.json()["singlesPlans"][0]
    assert plan["matchType"] == "singles", (
        f"Expected matchType='singles'. Got: {plan.get('matchType')!r}"
    )


def test_generate_plan_doubles_only_singles_plan_is_null(client_with_auth, mock_db):
    """§5i: Doubles-only tournament → singlesPlans == [], doublesPlans non-empty."""
    doubles_match = _base_match("doubles", "best_of_3")
    doubles_match2 = {
        **doubles_match,
        "id": MID2,
        "scheduled_start": "2026-05-15T18:00:00+00:00",
        "display_order": 2,
    }

    db = _make_plan_mock_db([doubles_match, doubles_match2])
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

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["singlesPlans"] == [], "singlesPlans must be [] for doubles-only tournament"
    assert len(body["doublesPlans"]) > 0, "doublesPlans must be non-empty for doubles-only tournament"


def test_generate_plan_doubles_match_type_field(client_with_auth, mock_db):
    """§5j: doublesPlans[0].matchType == 'doubles'."""
    doubles_match = _base_match("doubles", "best_of_3")
    doubles_match2 = {
        **doubles_match,
        "id": MID2,
        "scheduled_start": "2026-05-15T18:00:00+00:00",
        "display_order": 2,
    }

    db = _make_plan_mock_db([doubles_match, doubles_match2])
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

    assert resp.status_code == 200, resp.text
    plan = resp.json()["doublesPlans"][0]
    assert plan["matchType"] == "doubles", (
        f"Expected matchType='doubles'. Got: {plan.get('matchType')!r}"
    )
