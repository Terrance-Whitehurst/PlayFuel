"""Player note route tests — /v1/players/{pid}/notes.

Covers:
  - list notes (200)
  - create with all 3 source values
  - body > 2000 chars returns 422
  - 24h edit window honored (mock created_at to >24h ago → 422)
  - match_id ownership check
  - delete note (204)
  - cascade-delete via parent player
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_PLAYER_ID = str(uuid4())
_NOTE_ID = str(uuid4())

# A note created 1 hour ago — within the 24h edit window.
_RECENT_TS = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
# A note created 48 hours ago — outside the 24h edit window.
_OLD_TS = (datetime.now(tz=timezone.utc) - timedelta(hours=48)).isoformat()

_PLAYER_ROW = {
    "id": _PLAYER_ID,
    "user_id": _USER_ID,
    "display_name": "Garcia",
    "club": None,
    "city": None,
    "notes_summary": None,
    "created_at": "2026-04-01T12:00:00+00:00",
    "updated_at": "2026-04-01T12:00:00+00:00",
}


def _note_row(source="observed", created_at=None):
    return {
        "id": _NOTE_ID,
        "player_id": _PLAYER_ID,
        "user_id": _USER_ID,
        "source": source,
        "body": "Good backhand, tends to slice under pressure.",
        "match_id": None,
        "created_at": created_at or _RECENT_TS,
    }


def _make_chain(data):
    chain = MagicMock()
    chain.execute.return_value.data = data
    for attr in ("select", "insert", "update", "delete", "eq", "order", "limit",
                 "in_", "filter"):
        getattr(chain, attr).return_value = chain
    return chain


# ── List notes ────────────────────────────────────────────────────────────────


def test_list_player_notes_returns_200(client_with_auth, mock_db):
    """GET /v1/players/{pid}/notes → 200, list of notes."""
    player_chain = _make_chain([_PLAYER_ROW])
    notes_chain = _make_chain([_note_row()])

    def _dispatch(name):
        return {"players": player_chain, "player_notes": notes_chain}.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.get(f"/v1/players/{_PLAYER_ID}/notes")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["source"] == "observed"


def test_list_notes_player_not_found_returns_404(client_with_auth, mock_db):
    """GET /v1/players/{unknown}/notes → 404 when player not found."""
    player_chain = _make_chain([])  # RLS returns empty

    mock_db.table.return_value = player_chain
    mock_db.table.side_effect = None

    resp = client_with_auth.get(f"/v1/players/{uuid4()}/notes")
    assert resp.status_code == 404


# ── Create note ───────────────────────────────────────────────────────────────


def test_create_note_source_secondhand_returns_201(client_with_auth, mock_db):
    """POST /v1/players/{pid}/notes with source=secondhand → 201."""
    player_chain = _make_chain([_PLAYER_ROW])
    note_chain = _make_chain([_note_row(source="secondhand")])

    def _dispatch(name):
        return {"players": player_chain, "player_notes": note_chain}.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/players/{_PLAYER_ID}/notes",
        json={"source": "secondhand", "body": "Heard they have a big serve."},
    )
    assert resp.status_code == 201
    assert resp.json()["source"] == "secondhand"


def test_create_note_source_observed_returns_201(client_with_auth, mock_db):
    """POST /v1/players/{pid}/notes with source=observed → 201."""
    player_chain = _make_chain([_PLAYER_ROW])
    note_chain = _make_chain([_note_row(source="observed")])

    def _dispatch(name):
        return {"players": player_chain, "player_notes": note_chain}.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/players/{_PLAYER_ID}/notes",
        json={"source": "observed", "body": "Moves well to the right."},
    )
    assert resp.status_code == 201
    assert resp.json()["source"] == "observed"


def test_create_note_source_post_match_returns_201(client_with_auth, mock_db):
    """POST /v1/players/{pid}/notes with source=post_match → 201."""
    player_chain = _make_chain([_PLAYER_ROW])
    note_chain = _make_chain([_note_row(source="post_match")])

    def _dispatch(name):
        return {"players": player_chain, "player_notes": note_chain}.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/players/{_PLAYER_ID}/notes",
        json={"source": "post_match", "body": "Lost to them 4-6, 6-4, 4-6. Strong slice backhand."},
    )
    assert resp.status_code == 201
    assert resp.json()["source"] == "post_match"


def test_create_note_body_too_long_returns_422(client_with_auth, mock_db):
    """POST /v1/players/{pid}/notes with body > 2000 chars → 422."""
    resp = client_with_auth.post(
        f"/v1/players/{_PLAYER_ID}/notes",
        json={"source": "observed", "body": "x" * 2001},
    )
    assert resp.status_code == 422


def test_create_note_invalid_source_returns_422(client_with_auth, mock_db):
    """POST /v1/players/{pid}/notes with invalid source → 422."""
    resp = client_with_auth.post(
        f"/v1/players/{_PLAYER_ID}/notes",
        json={"source": "hearsay", "body": "Strong serve."},
    )
    assert resp.status_code == 422


def test_create_note_with_match_id_not_owned_returns_404(client_with_auth, mock_db):
    """POST /v1/players/{pid}/notes with match_id not owned by caller → 404."""
    player_chain = _make_chain([_PLAYER_ROW])
    match_chain = _make_chain([])  # RLS returns empty (match not found / not owned)

    def _dispatch(name):
        return {
            "players": player_chain,
            "matches": match_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/players/{_PLAYER_ID}/notes",
        json={
            "source": "post_match",
            "body": "Good match.",
            "match_id": str(uuid4()),  # unknown match
        },
    )
    assert resp.status_code == 404
    assert "Match not found" in resp.json()["detail"]


# ── Edit note ─────────────────────────────────────────────────────────────────


def test_edit_note_within_24h_returns_200(client_with_auth, mock_db):
    """PATCH /v1/players/{pid}/notes/{nid} within 24h → 200."""
    updated_note = {**_note_row(), "body": "Updated: also strong at net."}
    player_chain = _make_chain([_PLAYER_ROW])
    # First call: get note (for timestamp check). Second call: update.
    note_get_chain = _make_chain([_note_row(created_at=_RECENT_TS)])
    note_update_chain = _make_chain([updated_note])

    call_count = [0]

    def _notes_dispatch(name):
        if name == "player_notes":
            call_count[0] += 1
            return note_get_chain if call_count[0] == 1 else note_update_chain
        if name == "players":
            return player_chain
        return MagicMock()

    mock_db.table.side_effect = _notes_dispatch

    resp = client_with_auth.patch(
        f"/v1/players/{_PLAYER_ID}/notes/{_NOTE_ID}",
        json={"body": "Updated: also strong at net."},
    )
    assert resp.status_code == 200
    assert resp.json()["body"] == "Updated: also strong at net."


def test_edit_note_after_24h_returns_422(client_with_auth, mock_db):
    """PATCH /v1/players/{pid}/notes/{nid} after 24h → 422 (edit window closed)."""
    old_note = _note_row(created_at=_OLD_TS)
    note_chain = _make_chain([old_note])

    mock_db.table.return_value = note_chain
    mock_db.table.side_effect = None

    resp = client_with_auth.patch(
        f"/v1/players/{_PLAYER_ID}/notes/{_NOTE_ID}",
        json={"body": "Too late to edit."},
    )
    assert resp.status_code == 422
    assert "24 hours" in resp.json()["detail"]


# ── Delete note ───────────────────────────────────────────────────────────────


def test_delete_note_returns_204(client_with_auth, mock_db):
    """DELETE /v1/players/{pid}/notes/{nid} → 204."""
    chain = _make_chain([])

    mock_db.table.return_value = chain
    mock_db.table.side_effect = None

    resp = client_with_auth.delete(f"/v1/players/{_PLAYER_ID}/notes/{_NOTE_ID}")
    assert resp.status_code == 204


def test_cascade_delete_via_parent_player(client_with_auth, mock_db):
    """Deleting a player cascades to notes (DB-level; mock confirms route returns 204)."""
    chain = _make_chain([])

    mock_db.table.return_value = chain
    mock_db.table.side_effect = None

    # Delete the player
    resp = client_with_auth.delete(f"/v1/players/{_PLAYER_ID}")
    assert resp.status_code == 204
    # Notes are removed by DB cascade — route itself just deletes the player row.
    # Verified at DB level via migration 0010 ON DELETE CASCADE FK.
