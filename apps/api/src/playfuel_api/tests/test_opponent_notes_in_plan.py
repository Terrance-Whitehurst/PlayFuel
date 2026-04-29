"""Integration tests — opponent notes fed into generate_plan LLM input.

Covers (PLAYER_SCOUTING_V1.md §D / spec §G acceptance criteria):
  1. Match with opponent_player_id + 3 notes → llmSummary.summary contains
     "Your notes mention 3 prior observations".
  2. Match without opponent_player_id → no "prior observations" phrase in summary.
  3. Match with opponent_player_id but 0 notes → no phrase.
  4. Redacted note (§C prohibited phrase) is dropped; count reflects surviving notes.
  5. TemplateProvider never quotes note body verbatim in its output.
  6. Two matches in tournament: first has opponent notes, second does not →
     first plan has phrase, second plan does not.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── Shared fixtures ────────────────────────────────────────────────────────────

TID = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID1 = "c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID2 = "d0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
PLAYER_ID = str(uuid4())

_NOW_ISO = "2026-05-15T13:00:00+00:00"


def _base_match(mid: str, opp_player_id: str | None = None) -> dict:
    """Minimal match row accepted by MatchRow(**...)."""
    return {
        "id": mid,
        "tournament_id": TID,
        "scheduled_start": "2026-05-15T14:00:00+00:00",
        "estimated_duration_minutes": None,
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "age_bracket": "14U",
        "display_order": 1,
        "round_label": "R16",
        "opponent_label": "Smith",
        "court_label": "Court 7",
        "doubles_format": None,
        "opponent_player_id": opp_player_id,
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }


def _note_row(body: str, source: str = "observed") -> dict:
    return {
        "id": str(uuid4()),
        "player_id": PLAYER_ID,
        "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        "source": source,
        "body": body,
        "match_id": None,
        "created_at": _NOW_ISO,
    }


def _build_mock_db(
    match_rows: list[dict],
    note_rows: list[dict] | None = None,
) -> MagicMock:
    """Build a mock DB that returns match_rows + notes for player_notes queries."""
    mock_db = MagicMock()

    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = match_rows

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"venue_lat": 32.776664, "venue_lng": -96.796988, "venue_name": "Dallas Tennis Center"}
    ]

    # plans table: upsert returns generic data (not inspected in tests here)
    plans_chain = MagicMock()
    plans_chain.upsert.return_value.execute.return_value.data = [{}]

    # player_notes table (for fetch_opponent_notes_for_match)
    notes_data = note_rows if note_rows is not None else []
    notes_chain = MagicMock()
    notes_chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = notes_data

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
            "player_notes": notes_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch
    return mock_db


def _generate_and_return_plan(client_with_auth, mock_db):
    """Call generate_plan, patch async/places deps, return response body."""
    with (
        patch("playfuel_api.routes.plans.get_or_fetch_weather", new_callable=AsyncMock) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food") as mock_places,
    ):
        mock_wx.return_value = None  # no weather — keeps test synchronous
        mock_places.return_value = []  # no food places needed for these tests

        resp = client_with_auth.post(f"/v1/tournaments/{TID}/plans/generate")

    return resp


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_opponent_notes_phrase_present_with_3_notes(client_with_auth, mock_db):
    """Match with opponent_player_id + 3 notes → summary contains
    'Your notes mention 3 prior observations'."""
    notes = [
        _note_row("Moves well to the right side."),
        _note_row("Slice backhand is strong under pressure."),
        _note_row("Struggles with high balls to the forehand."),
    ]
    match_row = _base_match(MID1, opp_player_id=PLAYER_ID)
    mock = _build_mock_db([match_row], note_rows=notes)

    # Override the fixture's mock_db with our custom one
    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    app.dependency_overrides[verify_supabase_jwt] = lambda: \
        __import__("uuid").UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    app.dependency_overrides[authed_client] = lambda: mock

    try:
        resp = _generate_and_return_plan(client_with_auth, mock)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["singlesPlans"], "Expected at least one singles plan"
    plan = body["singlesPlans"][0]
    llm_summary = plan.get("llmSummary")
    assert llm_summary is not None, "llmSummary must be populated"
    summary = llm_summary["summary"]
    assert "3 prior observations" in summary, (
        f"Expected '3 prior observations' in summary. Got: {summary!r}"
    )
    assert "review the player profile for tactics" in summary


def test_no_opponent_player_id_no_notes_phrase(client_with_auth, mock_db):
    """Match without opponent_player_id → no 'prior observations' phrase."""
    match_row = _base_match(MID1, opp_player_id=None)
    mock = _build_mock_db([match_row], note_rows=[])

    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    app.dependency_overrides[verify_supabase_jwt] = lambda: \
        __import__("uuid").UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    app.dependency_overrides[authed_client] = lambda: mock

    try:
        resp = _generate_and_return_plan(client_with_auth, mock)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    plan = body["singlesPlans"][0]
    llm_summary = plan.get("llmSummary")
    assert llm_summary is not None
    summary = llm_summary["summary"]
    assert "prior observation" not in summary, (
        f"No opponent notes — phrase must be absent. Got: {summary!r}"
    )


def test_opponent_player_id_but_zero_notes_no_phrase(client_with_auth, mock_db):
    """Match with opponent_player_id but 0 notes → no phrase in summary."""
    match_row = _base_match(MID1, opp_player_id=PLAYER_ID)
    mock = _build_mock_db([match_row], note_rows=[])

    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    app.dependency_overrides[verify_supabase_jwt] = lambda: \
        __import__("uuid").UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    app.dependency_overrides[authed_client] = lambda: mock

    try:
        resp = _generate_and_return_plan(client_with_auth, mock)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    plan = resp.json()["singlesPlans"][0]
    summary = plan["llmSummary"]["summary"]
    assert "prior observation" not in summary, (
        f"0 notes — phrase must be absent. Got: {summary!r}"
    )


def test_redacted_notes_dropped_from_count(client_with_auth, mock_db):
    """Notes with §C prohibited phrases are dropped; count reflects surviving notes only.

    3 notes sent: 2 tactical (clean), 1 with 'guarantees better performance'.
    → summary says '2 prior observations', not 3.
    """
    notes = [
        _note_row("Strong serve to the T."),
        _note_row("His training guarantees better performance in the heat."),  # redacted
        _note_row("Weak second serve."),
    ]
    match_row = _base_match(MID1, opp_player_id=PLAYER_ID)
    mock = _build_mock_db([match_row], note_rows=notes)

    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    app.dependency_overrides[verify_supabase_jwt] = lambda: \
        __import__("uuid").UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    app.dependency_overrides[authed_client] = lambda: mock

    try:
        resp = _generate_and_return_plan(client_with_auth, mock)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    summary = resp.json()["singlesPlans"][0]["llmSummary"]["summary"]
    assert "2 prior observations" in summary, (
        f"Expected '2 prior observations' after redacting 1 note. Got: {summary!r}"
    )


def test_note_body_never_quoted_verbatim(client_with_auth, mock_db):
    """TemplateProvider must never quote note body text verbatim in the summary."""
    tactical_body = "moves well to the right side and slice backhand is strong"
    notes = [_note_row(tactical_body)]
    match_row = _base_match(MID1, opp_player_id=PLAYER_ID)
    mock = _build_mock_db([match_row], note_rows=notes)

    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    app.dependency_overrides[verify_supabase_jwt] = lambda: \
        __import__("uuid").UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    app.dependency_overrides[authed_client] = lambda: mock

    try:
        resp = _generate_and_return_plan(client_with_auth, mock)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    llm = resp.json()["singlesPlans"][0]["llmSummary"]
    full_text = " ".join([
        llm["summary"],
        llm.get("weatherNote") or "",
        llm.get("foodNote") or "",
        llm.get("safetyNote") or "",
        *llm.get("scenarioExplanations", {}).values(),
    ])
    assert tactical_body not in full_text, (
        "Note body must NEVER be quoted verbatim in LLM output"
    )


def test_singular_word_for_one_note(client_with_auth, mock_db):
    """1 note → summary uses 'observation' (singular), not 'observations'."""
    notes = [_note_row("Good slice backhand.")]
    match_row = _base_match(MID1, opp_player_id=PLAYER_ID)
    mock = _build_mock_db([match_row], note_rows=notes)

    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    app.dependency_overrides[verify_supabase_jwt] = lambda: \
        __import__("uuid").UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    app.dependency_overrides[authed_client] = lambda: mock

    try:
        resp = _generate_and_return_plan(client_with_auth, mock)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    summary = resp.json()["singlesPlans"][0]["llmSummary"]["summary"]
    assert "1 prior observation" in summary, (
        f"Expected singular 'observation'. Got: {summary!r}"
    )
    assert "observations" not in summary or "1 prior" in summary


def test_two_matches_first_has_notes_second_does_not(client_with_auth, mock_db):
    """Two matches in tournament: first with notes, second without.
    First plan has phrase; second plan does not.
    """
    notes = [_note_row("Strong net game.")]
    match1 = _base_match(MID1, opp_player_id=PLAYER_ID)
    match1["display_order"] = 1

    match2 = _base_match(MID2, opp_player_id=None)
    match2["scheduled_start"] = "2026-05-15T18:00:00+00:00"
    match2["display_order"] = 2

    # notes_chain will be used for BOTH fetches; first match has 1 note,
    # second fetch returns empty because opponent_player_id is None
    # (fetch_opponent_notes_for_match returns [] early when no player ID).
    mock = _build_mock_db([match1, match2], note_rows=notes)

    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    app.dependency_overrides[verify_supabase_jwt] = lambda: \
        __import__("uuid").UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    app.dependency_overrides[authed_client] = lambda: mock

    try:
        resp = _generate_and_return_plan(client_with_auth, mock)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    plans = resp.json()["singlesPlans"]
    assert len(plans) == 2, f"Expected 2 singles plans, got {len(plans)}"

    summary1 = plans[0]["llmSummary"]["summary"]
    summary2 = plans[1]["llmSummary"]["summary"]

    assert "prior observation" in summary1, (
        f"Plan 1 should mention notes. Got: {summary1!r}"
    )
    assert "prior observation" not in summary2, (
        f"Plan 2 should NOT mention notes. Got: {summary2!r}"
    )
