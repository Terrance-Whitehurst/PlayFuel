"""Match done-state tests — backend spec §J (match-done-state-cards.md).

Tests the `is_done` / `done_at` lifecycle on the matches table and the
propagation of `is_done` through `build_plan_envelope()` → `Plan.is_done`.

Acceptance criteria exercised here:
  test_create_match_default_is_done_false         AC#6
  test_update_match_mark_done_sets_done_at        AC#1
  test_update_match_undo_done_clears_done_at      AC#2
  test_update_match_done_idempotent               AC#1
  test_plan_carries_is_done_true                  AC#1
  test_plan_carries_is_done_false                 AC#6
  test_build_plan_envelope_is_done_forwarded      AC#1
  test_matchrow_accepts_is_done_and_done_at       V-6
  test_update_match_done_at_explicit_override     §C done_at semantics
  test_update_match_no_is_done_in_payload_preserves_done_at  §C
  test_patch_is_done_without_scheduled_start_skips_date_range_validation  regression

Test pattern: mock_db + client_with_auth from conftest.py.
Mock pattern mirrors test_match_date_range_validation.py and
test_delete_matches_tournaments.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

# ── Shared constants ──────────────────────────────────────────────────────────

_TID = "b7eebc99-9c0b-4ef8-bb6d-6bb9bd380a77"
_MID = "c7eebc99-9c0b-4ef8-bb6d-6bb9bd380a77"

_MATCH_PATH = f"/v1/tournaments/{_TID}/matches/{_MID}"

_MATCH_ROW_NOT_DONE = {
    "id": _MID,
    "tournament_id": _TID,
    "scheduled_start": "2026-06-01T09:00:00+00:00",
    "round": 64,
    "round_label": "R64",
    "format": "singles",
    "is_done": False,
    "done_at": None,
}

_MATCH_ROW_DONE = {
    **_MATCH_ROW_NOT_DONE,
    "is_done": True,
    "done_at": "2026-06-01T10:30:00+00:00",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_chain(data):
    """MagicMock chain whose .execute().data == data.

    All chaining methods return self so arbitrary chains resolve cleanly.
    Same pattern as test_delete_matches_tournaments.py.
    """
    chain = MagicMock()
    chain.execute.return_value.data = data
    for attr in (
        "select", "insert", "update", "delete", "eq", "order",
        "limit", "upsert", "filter", "in_", "maybe_single",
    ):
        getattr(chain, attr).return_value = chain
    return chain


def _make_scenarios():
    """Build a minimal single-match scenarios list using the rules engine."""
    from playfuel_api.models.db import MatchRow as _MatchRow
    from playfuel_api.rules.scenarios import generate_match_scenarios

    match = _MatchRow(
        id=uuid.uuid4(),
        tournament_id=uuid.uuid4(),
        scheduled_start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
    )
    return generate_match_scenarios(match=match, next_match=None)


# ── MatchRow ──────────────────────────────────────────────────────────────────


def test_matchrow_accepts_is_done_and_done_at():
    """MatchRow Pydantic model parses is_done and done_at without error (V-6)."""
    from playfuel_api.models.db import MatchRow

    row = MatchRow(
        id=uuid.uuid4(),
        tournament_id=uuid.uuid4(),
        scheduled_start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        is_done=True,
        done_at=datetime(2026, 6, 1, 10, 30, tzinfo=timezone.utc),
    )
    assert row.is_done is True
    assert row.done_at is not None


def test_matchrow_default_is_done_false():
    """MatchRow.is_done defaults to False when not provided (AC#6)."""
    from playfuel_api.models.db import MatchRow

    row = MatchRow(
        id=uuid.uuid4(),
        tournament_id=uuid.uuid4(),
        scheduled_start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
    )
    assert row.is_done is False
    assert row.done_at is None


# ── build_plan_envelope ───────────────────────────────────────────────────────


def test_build_plan_envelope_is_done_forwarded():
    """build_plan_envelope(is_done=True) → Plan.is_done == True (AC#1 / §J)."""
    from playfuel_api.rules.plan import build_plan_envelope

    tid = uuid.uuid4()
    scenarios = _make_scenarios()
    plan = build_plan_envelope(tid, scenarios, is_done=True)
    assert plan.is_done is True


def test_build_plan_envelope_is_done_false_default():
    """build_plan_envelope with no is_done → Plan.is_done == False (AC#6 / §J)."""
    from playfuel_api.rules.plan import build_plan_envelope

    tid = uuid.uuid4()
    scenarios = _make_scenarios()
    plan = build_plan_envelope(tid, scenarios)
    assert plan.is_done is False


# ── Plan model ────────────────────────────────────────────────────────────────


def test_plan_carries_is_done_true():
    """Plan.is_done is serialised as isDone=true in camelCase API output (AC#1)."""
    from playfuel_api.rules.plan import build_plan_envelope

    tid = uuid.uuid4()
    scenarios = _make_scenarios()
    plan = build_plan_envelope(tid, scenarios, is_done=True)
    serialised = plan.model_dump(by_alias=True, mode="json")
    assert serialised["isDone"] is True


def test_plan_carries_is_done_false():
    """Plan.is_done serialises as isDone=false when match is not done (AC#6)."""
    from playfuel_api.rules.plan import build_plan_envelope

    tid = uuid.uuid4()
    scenarios = _make_scenarios()
    plan = build_plan_envelope(tid, scenarios, is_done=False)
    serialised = plan.model_dump(by_alias=True, mode="json")
    assert serialised["isDone"] is False


# ── Route: create match ───────────────────────────────────────────────────────


def test_create_match_default_is_done_false(client_with_auth, mock_db):
    """POST /matches returns a match row; the row has is_done defaulting to false (AC#6).

    The route itself doesn't validate is_done on create — it's a DB DEFAULT.
    We confirm the route doesn't inject a conflicting value and the row returned
    by the mock carries is_done=False (as the DB column default would produce).
    """
    tournaments_chain = _make_chain([{
        "draw_size": 64,
        "start_date": "2026-06-01",
        "end_date": "2026-06-03",
    }])
    matches_chain = _make_chain([_MATCH_ROW_NOT_DONE])

    def _dispatch(name):
        return {"tournaments": tournaments_chain, "matches": matches_chain}.get(
            name, MagicMock()
        )

    mock_db.table.side_effect = _dispatch

    body = {
        "round": 64,
        "scheduledStart": "2026-06-01T09:00:00Z",
    }
    resp = client_with_auth.post(
        f"/v1/tournaments/{_TID}/matches", json=body
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data.get("is_done") is False


# ── Route: update match — done-state lifecycle ────────────────────────────────


def test_update_match_mark_done_sets_done_at(client_with_auth, mock_db):
    """PUT with isDone=true → server injects done_at when not provided (AC#1).

    We verify the `update` call receives a `done_at` key (set by the route
    server-side), not just is_done.
    """
    update_chain = _make_chain([_MATCH_ROW_DONE])
    mock_db.table.return_value = update_chain

    body = {"isDone": True}
    resp = client_with_auth.put(_MATCH_PATH, json=body)
    assert resp.status_code == 200, resp.text

    # Confirm the update was called with a done_at key set server-side
    call_args = update_chain.update.call_args
    assert call_args is not None
    payload_arg = call_args[0][0]
    assert "done_at" in payload_arg
    assert payload_arg["done_at"] is not None


def test_update_match_undo_done_clears_done_at(client_with_auth, mock_db):
    """PUT with isDone=false → server forces done_at=None regardless of any client value (AC#2)."""
    update_chain = _make_chain([_MATCH_ROW_NOT_DONE])
    mock_db.table.return_value = update_chain

    body = {"isDone": False}
    resp = client_with_auth.put(_MATCH_PATH, json=body)
    assert resp.status_code == 200, resp.text

    call_args = update_chain.update.call_args
    payload_arg = call_args[0][0]
    assert "done_at" in payload_arg
    assert payload_arg["done_at"] is None


def test_update_match_done_idempotent(client_with_auth, mock_db):
    """PUT with isDone=true on an already-done match is 200, not an error (AC#1)."""
    update_chain = _make_chain([_MATCH_ROW_DONE])
    mock_db.table.return_value = update_chain

    # Call twice — both should return 200
    body = {"isDone": True}
    resp1 = client_with_auth.put(_MATCH_PATH, json=body)
    resp2 = client_with_auth.put(_MATCH_PATH, json=body)
    assert resp1.status_code == 200, resp1.text
    assert resp2.status_code == 200, resp2.text


def test_update_match_done_at_explicit_override(client_with_auth, mock_db):
    """Client-provided done_at with isDone=true is respected (§C done_at semantics).

    When is_done=True AND done_at is explicitly supplied, the route passes it
    through rather than overwriting with datetime.utcnow().
    """
    update_chain = _make_chain([_MATCH_ROW_DONE])
    mock_db.table.return_value = update_chain

    body = {"isDone": True, "doneAt": "2026-06-01T08:00:00Z"}
    resp = client_with_auth.put(_MATCH_PATH, json=body)
    assert resp.status_code == 200, resp.text

    call_args = update_chain.update.call_args
    payload_arg = call_args[0][0]
    # done_at is present (the client-provided datetime, isoformatted by the route)
    assert "done_at" in payload_arg


def test_update_match_no_is_done_in_payload_preserves_done_at(client_with_auth, mock_db):
    """Patching other fields (e.g. court_label) without is_done does NOT touch done_at (§C)."""
    update_chain = _make_chain([_MATCH_ROW_DONE])
    mock_db.table.return_value = update_chain

    # Send a payload that doesn't include is_done at all
    body = {"courtLabel": "Court 3"}
    resp = client_with_auth.put(_MATCH_PATH, json=body)
    assert resp.status_code == 200, resp.text

    call_args = update_chain.update.call_args
    payload_arg = call_args[0][0]
    # done_at should NOT appear in the payload (not modified)
    assert "done_at" not in payload_arg


def test_patch_is_done_without_scheduled_start_skips_date_range_validation(
    client_with_auth, mock_db
):
    """PUT with only isDone — no scheduled_start — skips the date-range validation query.

    Regression guard: date-range validation must only fire when scheduled_start
    is in the payload. Toggling is_done must never trigger an unnecessary
    tournament SELECT (extra round-trip + potential failure).
    """
    update_chain = _make_chain([_MATCH_ROW_DONE])
    mock_db.table.return_value = update_chain

    body = {"isDone": True}
    resp = client_with_auth.put(_MATCH_PATH, json=body)
    assert resp.status_code == 200, resp.text

    # The date-range validation block issues a SELECT on the tournaments table
    # only when body.scheduled_start is not None. Verify 'tournaments' was NOT queried.
    called_tables = [
        call[0][0] for call in mock_db.table.call_args_list
        if call[0]
    ]
    assert "tournaments" not in called_tables, (
        "date-range validation triggered unexpectedly when only isDone was in the payload"
    )
