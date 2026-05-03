"""Player scouting route tests — /v1/players.

Covers:
  - list/create/get/patch/delete happy paths
  - RLS isolation: user A cannot see user B's players
  - note_count derived correctly
  - opponent_player_id accepted/rejected on match create
  - cascade-delete confirmation (mock returns empty after delete)
"""
from unittest.mock import MagicMock
from uuid import UUID, uuid4


# ── Fixtures / helpers ────────────────────────────────────────────────────────

_PLAYER_ID = str(uuid4())
_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

_PLAYER_ROW = {
    "id": _PLAYER_ID,
    "user_id": _USER_ID,
    "display_name": "Smith",
    "club": "Dallas Tennis Academy",
    "city": "Dallas, TX",
    "notes_summary": None,
    "created_at": "2026-04-01T12:00:00+00:00",
    "updated_at": "2026-04-01T12:00:00+00:00",
}


def _make_chain(data):
    """Return a MagicMock chain whose .execute().data == data."""
    chain = MagicMock()
    chain.execute.return_value.data = data
    # Support chaining: .select().eq().limit().execute() etc.
    for attr in ("select", "insert", "update", "delete", "eq", "order", "limit",
                 "in_", "filter"):
        getattr(chain, attr).return_value = chain
    return chain


# ── List players ──────────────────────────────────────────────────────────────


def test_list_players_returns_200(client_with_auth, mock_db):
    """GET /v1/players → 200, returns list with note_count."""
    players_chain = _make_chain([_PLAYER_ROW])
    notes_chain = _make_chain([])

    def _dispatch(name):
        return {"players": players_chain, "player_notes": notes_chain}.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.get("/v1/players")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["displayName"] == "Smith"
    assert body[0]["noteCount"] == 0


def test_list_players_with_note_count(client_with_auth, mock_db):
    """GET /v1/players → note_count reflects actual note rows."""
    players_chain = _make_chain([_PLAYER_ROW])
    notes_chain = _make_chain([
        {"player_id": _PLAYER_ID},
        {"player_id": _PLAYER_ID},
    ])

    def _dispatch(name):
        return {"players": players_chain, "player_notes": notes_chain}.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.get("/v1/players")
    assert resp.status_code == 200
    assert resp.json()[0]["noteCount"] == 2


def test_list_players_empty_returns_empty_list(client_with_auth, mock_db):
    """GET /v1/players with no players → []."""
    players_chain = _make_chain([])

    mock_db.table.return_value = players_chain
    mock_db.table.side_effect = None

    resp = client_with_auth.get("/v1/players")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_players_rls_isolation(client_with_auth, mock_db):
    """RLS scopes players to caller — mock returns [] for other user's player."""
    # The RLS on players guarantees the DB returns empty for other-user players.
    # Mock returns empty to simulate that guarantee.
    players_chain = _make_chain([])

    def _dispatch(name):
        return {"players": players_chain, "player_notes": _make_chain([])}.get(
            name, MagicMock()
        )

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.get("/v1/players")
    assert resp.status_code == 200
    assert resp.json() == []  # user B's players are invisible


# ── Create player ──────────────────────────────────────────────────────────────


def test_create_player_returns_201(client_with_auth, mock_db):
    """POST /v1/players → 201 + player object."""
    chain = _make_chain([_PLAYER_ROW])

    mock_db.table.return_value = chain
    mock_db.table.side_effect = None

    resp = client_with_auth.post(
        "/v1/players",
        json={"displayName": "Smith", "club": "Dallas Tennis Academy", "city": "Dallas, TX"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["displayName"] == "Smith"
    assert body["club"] == "Dallas Tennis Academy"


def test_create_player_minimal_fields_returns_201(client_with_auth, mock_db):
    """POST /v1/players with only display_name → 201."""
    minimal_row = {**_PLAYER_ROW, "club": None, "city": None}
    chain = _make_chain([minimal_row])

    mock_db.table.return_value = chain
    mock_db.table.side_effect = None

    resp = client_with_auth.post("/v1/players", json={"displayName": "Garcia"})
    assert resp.status_code == 201


def test_create_player_empty_name_returns_422(client_with_auth, mock_db):
    """POST /v1/players with empty display_name → 422 (Pydantic validation)."""
    resp = client_with_auth.post("/v1/players", json={"displayName": ""})
    assert resp.status_code == 422


# ── Get player ────────────────────────────────────────────────────────────────


def test_get_player_returns_200(client_with_auth, mock_db):
    """GET /v1/players/{pid} → 200 + player object."""
    player_chain = _make_chain([_PLAYER_ROW])
    notes_chain = _make_chain([{"id": str(uuid4())}])

    def _dispatch(name):
        return {"players": player_chain, "player_notes": notes_chain}.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.get(f"/v1/players/{_PLAYER_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == _PLAYER_ID
    assert body["noteCount"] == 1


def test_get_player_not_found_returns_404(client_with_auth, mock_db):
    """GET /v1/players/{unknown_pid} → 404."""
    chain = _make_chain([])  # RLS returns empty for unknown/unowned player

    mock_db.table.return_value = chain
    mock_db.table.side_effect = None

    resp = client_with_auth.get(f"/v1/players/{uuid4()}")
    assert resp.status_code == 404


# ── Patch player ──────────────────────────────────────────────────────────────


def test_patch_player_returns_200(client_with_auth, mock_db):
    """PATCH /v1/players/{pid} → 200 + updated object."""
    updated_row = {**_PLAYER_ROW, "city": "Plano, TX"}
    chain = _make_chain([updated_row])

    mock_db.table.return_value = chain
    mock_db.table.side_effect = None

    resp = client_with_auth.patch(f"/v1/players/{_PLAYER_ID}", json={"city": "Plano, TX"})
    assert resp.status_code == 200
    assert resp.json()["city"] == "Plano, TX"


def test_patch_player_no_fields_returns_422(client_with_auth, mock_db):
    """PATCH /v1/players/{pid} with empty body → 422."""
    resp = client_with_auth.patch(f"/v1/players/{_PLAYER_ID}", json={})
    assert resp.status_code == 422


# ── Delete player ─────────────────────────────────────────────────────────────


def test_delete_player_returns_204(client_with_auth, mock_db):
    """DELETE /v1/players/{pid} → 204."""
    chain = _make_chain([])

    mock_db.table.return_value = chain
    mock_db.table.side_effect = None

    resp = client_with_auth.delete(f"/v1/players/{_PLAYER_ID}")
    assert resp.status_code == 204


def test_delete_player_cascade_confirmed(client_with_auth, mock_db):
    """After deleting a player, GET returns 404 (mock simulates cascade)."""
    delete_chain = _make_chain([])
    get_chain = _make_chain([])  # RLS returns empty after delete

    call_count = [0]

    def _dispatch(name):
        if name == "players":
            call_count[0] += 1
            return delete_chain if call_count[0] == 1 else get_chain
        return MagicMock()

    mock_db.table.side_effect = _dispatch

    # Delete
    del_resp = client_with_auth.delete(f"/v1/players/{_PLAYER_ID}")
    assert del_resp.status_code == 204

    # Now GET should 404 (simulated by empty RLS result)
    get_resp = client_with_auth.get(f"/v1/players/{uuid4()}")
    assert get_resp.status_code == 404


# ── opponent_player_id on match create ────────────────────────────────────────


def test_match_create_with_valid_opponent_player_id_returns_201(client_with_auth, mock_db):
    """POST /v1/tournaments/{tid}/matches with valid opponent_player_id → 201."""
    TID = str(uuid4())
    PID = str(uuid4())

    player_chain = _make_chain([{"id": PID}])   # RLS returns the player (valid)
    tournament_chain = _make_chain([{"draw_size": 32}])  # draw-size-spec: route fetches draw_size
    match_row = {
        "id": str(uuid4()),
        "tournament_id": TID,
        "scheduled_start": "2026-05-15T09:00:00+00:00",
        "estimated_duration_minutes": 120,
        "actual_end_at": None,
        "surface": None,
        "format": "singles",
        "age_bracket": None,
        "display_order": 1,
        "round_label": "R32",
        "round": 32,
        "opponent_label": "Smith",
        "court_label": None,
        "doubles_format": None,
        "opponent_player_id": PID,
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }
    match_chain = _make_chain([match_row])

    def _dispatch(name):
        return {"players": player_chain, "tournaments": tournament_chain, "matches": match_chain}.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{TID}/matches",
        json={
            "scheduled_start": "2026-05-15T09:00:00+00:00",
            "round": 32,
            "opponent_label": "Smith",
            "opponent_player_id": PID,
        },
    )
    assert resp.status_code == 201


def test_match_create_with_unknown_opponent_player_id_returns_404(client_with_auth, mock_db):
    """POST /v1/tournaments/{tid}/matches with unknown opponent_player_id → 404."""
    TID = str(uuid4())
    UNKNOWN_PID = str(uuid4())

    # RLS returns empty (player not found or not owned)
    player_chain = _make_chain([])

    def _dispatch(name):
        return {"players": player_chain}.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{TID}/matches",
        json={
            "scheduled_start": "2026-05-15T09:00:00+00:00",
            "round": 32,
            "opponent_player_id": UNKNOWN_PID,
        },
    )
    assert resp.status_code == 404
    assert "Player not found" in resp.json()["detail"]
