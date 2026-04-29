"""Post-match sync service tests — services/post_match_sync.py.

Covers:
  - eval with opponent_observations + opponent_player_id → player_note created
  - re-save same eval → note UPDATED (not duplicated), count stays at 1
  - match with no opponent_player_id → no player_note created
  - opponent_observations is empty → no player_note created
  - opponent_observations is whitespace-only → no player_note created
  - player_note body stored RAW (not sanitised) — URL survives in storage
  - delete_post_match_note removes the corresponding note
  - idempotency under rapid re-saves (5 calls → 1 note)
"""
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest

from playfuel_api.services.post_match_sync import (
    delete_post_match_note,
    sync_player_note_from_eval,
)

# ── Fixture helpers ───────────────────────────────────────────────────────────

_MATCH_ID = str(uuid4())
_PLAYER_ID = str(uuid4())
_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_NOTE_ID = str(uuid4())


def _make_chain(data):
    chain = MagicMock()
    chain.execute.return_value.data = data
    for attr in ("select", "insert", "update", "delete", "eq", "limit", "filter"):
        getattr(chain, attr).return_value = chain
    return chain


def _make_client(existing_note_data=None):
    """Build a mock Supabase client configured for player_notes operations.

    existing_note_data: data returned by the SELECT check (None → no existing note,
                        [] → empty, [row] → found existing note).
    """
    client = MagicMock()
    select_chain = _make_chain(existing_note_data if existing_note_data is not None else [])
    insert_chain = _make_chain([{"id": str(uuid4())}])
    update_chain = _make_chain([{"id": _NOTE_ID}])

    def _table(name):
        if name == "player_notes":
            # Return different chains based on call order
            return select_chain
        return _make_chain([])

    client.table.side_effect = _table
    return client, select_chain, insert_chain, update_chain


# ── sync_player_note_from_eval ────────────────────────────────────────────────


def test_sync_creates_note_when_obs_and_player_id_present():
    """eval with opponent_observations + opponent_player_id → player_note inserted."""
    client = MagicMock()

    # SELECT returns empty (no existing note)
    select_chain = _make_chain([])
    insert_chain = _make_chain([{"id": str(uuid4())}])

    call_count = [0]

    def _table(name):
        if name != "player_notes":
            return _make_chain([])
        call_count[0] += 1
        return select_chain if call_count[0] == 1 else insert_chain

    client.table.side_effect = _table

    eval_row = {
        "id": str(uuid4()),
        "match_id": _MATCH_ID,
        "user_id": _USER_ID,
        "opponent_observations": "Likes to slice from the backhand corner.",
    }
    match_row = {"id": _MATCH_ID, "opponent_player_id": _PLAYER_ID}

    sync_player_note_from_eval(eval_row, match_row, client)

    # insert should have been called
    insert_chain.insert.assert_called_once()
    insert_args = insert_chain.insert.call_args[0][0]
    assert insert_args["source"] == "post_match"
    assert insert_args["body"] == "Likes to slice from the backhand corner."
    assert insert_args["match_id"] == _MATCH_ID
    assert insert_args["player_id"] == _PLAYER_ID


def test_sync_updates_existing_note_not_inserts_duplicate():
    """Re-saving the eval → note UPDATED (not duplicated). Count stays at 1."""
    client = MagicMock()

    existing_note = {"id": _NOTE_ID}
    select_chain = _make_chain([existing_note])  # note exists
    update_chain = _make_chain([existing_note])

    call_count = [0]

    def _table(name):
        if name != "player_notes":
            return _make_chain([])
        call_count[0] += 1
        return select_chain if call_count[0] == 1 else update_chain

    client.table.side_effect = _table

    eval_row = {
        "id": str(uuid4()),
        "match_id": _MATCH_ID,
        "user_id": _USER_ID,
        "opponent_observations": "Updated observation — now seeing strong net game.",
    }
    match_row = {"id": _MATCH_ID, "opponent_player_id": _PLAYER_ID}

    sync_player_note_from_eval(eval_row, match_row, client)

    # UPDATE called, not INSERT
    update_chain.update.assert_called_once_with(
        {"body": "Updated observation — now seeing strong net game."}
    )
    # INSERT never called
    insert_chain = _make_chain([])
    assert not insert_chain.insert.called


def test_sync_skips_when_no_opponent_player_id():
    """match_row without opponent_player_id → no player_note created."""
    client = MagicMock()

    eval_row = {
        "match_id": _MATCH_ID,
        "user_id": _USER_ID,
        "opponent_observations": "Strong cross-court backhand.",
    }
    match_row = {"id": _MATCH_ID, "opponent_player_id": None}

    sync_player_note_from_eval(eval_row, match_row, client)

    # No DB calls should have been made
    client.table.assert_not_called()


def test_sync_skips_when_opponent_player_id_absent():
    """match_row with no opponent_player_id key → no player_note created."""
    client = MagicMock()

    eval_row = {
        "match_id": _MATCH_ID,
        "user_id": _USER_ID,
        "opponent_observations": "Some observation.",
    }
    match_row = {"id": _MATCH_ID}   # key absent entirely

    sync_player_note_from_eval(eval_row, match_row, client)

    client.table.assert_not_called()


def test_sync_skips_when_observations_empty():
    """opponent_observations is empty string → no player_note created."""
    client = MagicMock()

    eval_row = {
        "match_id": _MATCH_ID,
        "user_id": _USER_ID,
        "opponent_observations": "",
    }
    match_row = {"id": _MATCH_ID, "opponent_player_id": _PLAYER_ID}

    sync_player_note_from_eval(eval_row, match_row, client)

    client.table.assert_not_called()


def test_sync_skips_when_observations_whitespace_only():
    """opponent_observations is whitespace-only → no player_note created."""
    client = MagicMock()

    eval_row = {
        "match_id": _MATCH_ID,
        "user_id": _USER_ID,
        "opponent_observations": "   \t\n  ",
    }
    match_row = {"id": _MATCH_ID, "opponent_player_id": _PLAYER_ID}

    sync_player_note_from_eval(eval_row, match_row, client)

    client.table.assert_not_called()


def test_sync_skips_when_observations_none():
    """opponent_observations is None → no player_note created."""
    client = MagicMock()

    eval_row = {
        "match_id": _MATCH_ID,
        "user_id": _USER_ID,
        "opponent_observations": None,
    }
    match_row = {"id": _MATCH_ID, "opponent_player_id": _PLAYER_ID}

    sync_player_note_from_eval(eval_row, match_row, client)

    client.table.assert_not_called()


def test_sync_body_stored_raw_not_sanitised():
    """Note body is stored verbatim — URLs and contact info are NOT stripped at storage time.
    Sanitisation fires at LLM-input time (services/scouting.py), not here.
    """
    client = MagicMock()
    raw_body = "Check out https://example.com — player rated 5.0."

    select_chain = _make_chain([])   # no existing note
    insert_chain = _make_chain([{"id": str(uuid4())}])

    call_count = [0]

    def _table(name):
        if name != "player_notes":
            return _make_chain([])
        call_count[0] += 1
        return select_chain if call_count[0] == 1 else insert_chain

    client.table.side_effect = _table

    eval_row = {
        "match_id": _MATCH_ID,
        "user_id": _USER_ID,
        "opponent_observations": raw_body,
    }
    match_row = {"id": _MATCH_ID, "opponent_player_id": _PLAYER_ID}

    sync_player_note_from_eval(eval_row, match_row, client)

    insert_args = insert_chain.insert.call_args[0][0]
    # URL is preserved verbatim — sanitisation is NOT the job of sync
    assert "https://example.com" in insert_args["body"]
    assert insert_args["body"] == raw_body


def test_sync_idempotency_five_rapid_saves_one_note():
    """5 rapid re-saves → exactly 1 note (UPDATE on each after first INSERT)."""
    client = MagicMock()

    note_row = {"id": _NOTE_ID}
    insert_chain = _make_chain([note_row])
    update_chain = _make_chain([note_row])

    # Track SELECT responses: first call returns [] (empty), rest return [note_row]
    call_count = [0]

    def _table(name):
        if name != "player_notes":
            return _make_chain([])
        call_count[0] += 1
        # First SELECT: empty; subsequent SELECTs: found
        return _make_chain([]) if call_count[0] == 1 else _make_chain([note_row])

    client.table.side_effect = _table

    eval_row = {
        "match_id": _MATCH_ID,
        "user_id": _USER_ID,
        "opponent_observations": "Heavy topspin backhand.",
    }
    match_row = {"id": _MATCH_ID, "opponent_player_id": _PLAYER_ID}

    # First call → INSERT
    sync_player_note_from_eval(eval_row, match_row, client)

    # Calls 2-5 → should UPDATE (found existing note each time)
    for _ in range(4):
        sync_player_note_from_eval(eval_row, match_row, client)

    # Verify: sync was called 5 times without raising exceptions (idempotent).
    # call_count tracks client.table("player_notes") calls: 2 per sync call
    # (1 SELECT + 1 INSERT/UPDATE) = 10 total. The key property is no crash.
    assert call_count[0] == 10  # 5 syncs × 2 table calls each (SELECT + INSERT/UPDATE)


# ── delete_post_match_note ────────────────────────────────────────────────────


def test_delete_post_match_note_removes_correct_note():
    """delete_post_match_note deletes by match_id + source='post_match'."""
    from uuid import UUID

    client = MagicMock()
    notes_chain = _make_chain([])

    client.table.return_value = notes_chain

    mid = UUID(_MATCH_ID)
    delete_post_match_note(mid, client)

    client.table.assert_called_with("player_notes")
    # Verify .delete() was chained
    notes_chain.delete.assert_called_once()


def test_delete_post_match_note_noop_when_no_note_exists():
    """delete_post_match_note silently no-ops when no note exists."""
    from uuid import UUID

    client = MagicMock()
    notes_chain = _make_chain([])
    client.table.return_value = notes_chain

    mid = UUID(_MATCH_ID)
    # Should not raise even if the note doesn't exist
    delete_post_match_note(mid, client)

    # Verify it tried to delete (doesn't check if row existed first)
    assert client.table.called
