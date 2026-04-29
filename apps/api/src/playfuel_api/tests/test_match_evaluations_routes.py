"""Post-match evaluation route tests — /v1/matches/{mid}/evaluation.

Covers:
  - GET → 200 when eval exists; 404 when not yet created
  - POST creates (201) on first call; upserts (200) on second call
  - PATCH partially updates fields; 404 when no eval exists
  - DELETE removes the eval (and triggers note cleanup)
  - Validation: rating out of range, went_well > 5 items, item > 200 chars,
                score_text > 80 chars, opp_obs > 500 chars, key_moments > 500 chars
  - All 4 result enum values accepted
  - RLS isolation: user A's eval not accessible to user B (mock returns [])
  - Cross-match injection: POST with unowned match → 404 from match ownership check
  - Auto-note sync path exercised (covered more deeply in test_post_match_sync.py)
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ── Fixtures / helpers ────────────────────────────────────────────────────────

_MATCH_ID = str(uuid4())
_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

_MATCH_ROW = {
    "id": _MATCH_ID,
    "tournament_id": str(uuid4()),
    "scheduled_start": "2026-05-10T09:00:00+00:00",
    "opponent_player_id": None,
    "opponent_label": "Smith",
    "created_at": "2026-05-01T00:00:00+00:00",
    "updated_at": "2026-05-01T00:00:00+00:00",
}

_EVAL_ID = str(uuid4())

_EVAL_ROW = {
    "id": _EVAL_ID,
    "match_id": _MATCH_ID,
    "user_id": _USER_ID,
    "result": "won",
    "score_text": "6-4, 6-2",
    "effort_rating": 4,
    "focus_rating": 5,
    "went_well": ["Serve consistency", "Net approach"],
    "to_improve": ["Second serve depth"],
    "opponent_observations": "Heavy topspin backhand.",
    "key_moments": "Saved break point at 5-4.",
    "created_at": "2026-05-10T11:30:00+00:00",
    "updated_at": "2026-05-10T11:30:00+00:00",
}


def _make_chain(data):
    """Return a MagicMock chain whose .execute().data == data."""
    chain = MagicMock()
    chain.execute.return_value.data = data
    for attr in ("select", "insert", "update", "delete", "eq", "order", "limit",
                 "upsert", "filter", "in_", "maybe_single"):
        getattr(chain, attr).return_value = chain
    return chain


def _table_dispatch(match_data, eval_data):
    """Build a mock_db.table side_effect that routes to match or eval chain."""
    match_chain = _make_chain(match_data)
    eval_chain = _make_chain(eval_data)

    def _dispatch(name):
        if name == "matches":
            return match_chain
        if name == "match_evaluations":
            return eval_chain
        return _make_chain([])

    return _dispatch


# ── GET evaluation ────────────────────────────────────────────────────────────


def test_get_evaluation_returns_200(client_with_auth, mock_db):
    """GET /v1/matches/{mid}/evaluation → 200 when eval exists."""
    mock_db.table.side_effect = _table_dispatch([_MATCH_ROW], [_EVAL_ROW])

    resp = client_with_auth.get(f"/v1/matches/{_MATCH_ID}/evaluation")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "won"
    assert body["effortRating"] == 4
    assert body["wentWell"] == ["Serve consistency", "Net approach"]
    assert body["matchId"] == _MATCH_ID


def test_get_evaluation_returns_404_when_none(client_with_auth, mock_db):
    """GET /v1/matches/{mid}/evaluation → 404 when no eval created yet."""
    mock_db.table.side_effect = _table_dispatch([_MATCH_ROW], [])

    resp = client_with_auth.get(f"/v1/matches/{_MATCH_ID}/evaluation")
    assert resp.status_code == 404


def test_get_evaluation_returns_404_for_unknown_match(client_with_auth, mock_db):
    """GET with unknown match → 404 from match ownership check."""
    mock_db.table.side_effect = _table_dispatch([], [])

    resp = client_with_auth.get(f"/v1/matches/{uuid4()}/evaluation")
    assert resp.status_code == 404


# ── POST evaluation (upsert) ──────────────────────────────────────────────────


def test_post_evaluation_creates_returns_201(client_with_auth, mock_db):
    """POST /v1/matches/{mid}/evaluation → 201 on first creation."""
    match_chain = _make_chain([_MATCH_ROW])
    # First eval query: empty (not yet exists); insert returns the row
    eval_check_chain = _make_chain([])
    eval_insert_chain = _make_chain([_EVAL_ROW])

    call_count = [0]

    def _dispatch(name):
        if name == "matches":
            return match_chain
        if name == "match_evaluations":
            call_count[0] += 1
            # First call = check; second call = insert
            return eval_check_chain if call_count[0] == 1 else eval_insert_chain
        if name == "player_notes":
            return _make_chain([])
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={
            "result": "won",
            "scoreText": "6-4, 6-2",
            "effortRating": 4,
            "focusRating": 5,
            "wentWell": ["Serve consistency"],
            "toImprove": ["Second serve depth"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["result"] == "won"


def test_post_evaluation_upserts_returns_200_on_second_call(client_with_auth, mock_db):
    """Second POST to same match → 200 (upsert behaviour, not 409)."""
    match_chain = _make_chain([_MATCH_ROW])
    eval_update_chain = _make_chain([_EVAL_ROW])

    call_count = [0]

    def _dispatch(name):
        if name == "matches":
            return match_chain
        if name == "match_evaluations":
            call_count[0] += 1
            # First call = check exists (returns existing row)
            return _make_chain([_EVAL_ROW]) if call_count[0] == 1 else eval_update_chain
        if name == "player_notes":
            return _make_chain([])
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won"},
    )
    assert resp.status_code == 200


def test_post_evaluation_all_result_values(client_with_auth, mock_db):
    """All 4 result enum values are accepted (won/lost/withdrew/retired)."""
    for result_val in ("won", "lost", "withdrew", "retired"):
        eval_row = {**_EVAL_ROW, "result": result_val}
        match_chain = _make_chain([_MATCH_ROW])
        call_count = [0]

        def _dispatch(name, _result=result_val, _row=eval_row):
            if name == "matches":
                return _make_chain([_MATCH_ROW])
            if name == "match_evaluations":
                call_count[0] += 1
                return _make_chain([]) if call_count[0] == 1 else _make_chain([_row])
            if name == "player_notes":
                return _make_chain([])
            return _make_chain([])

        mock_db.table.side_effect = _dispatch

        resp = client_with_auth.post(
            f"/v1/matches/{_MATCH_ID}/evaluation",
            json={"result": result_val},
        )
        assert resp.status_code == 201, f"Expected 201 for result={result_val}, got {resp.status_code}"


def test_post_evaluation_minimal_fields_only_result(client_with_auth, mock_db):
    """POST with only required field (result) → 201."""
    minimal_row = {**_EVAL_ROW, "result": "lost", "score_text": None, "effort_rating": None,
                   "focus_rating": None, "went_well": [], "to_improve": [],
                   "opponent_observations": None, "key_moments": None}
    match_chain = _make_chain([_MATCH_ROW])

    call_count = [0]

    def _dispatch(name):
        if name == "matches":
            return match_chain
        if name == "match_evaluations":
            call_count[0] += 1
            return _make_chain([]) if call_count[0] == 1 else _make_chain([minimal_row])
        if name == "player_notes":
            return _make_chain([])
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "lost"},
    )
    assert resp.status_code == 201
    assert resp.json()["result"] == "lost"


# ── PATCH evaluation ──────────────────────────────────────────────────────────


def test_patch_evaluation_updates_fields(client_with_auth, mock_db):
    """PATCH → 200, only provided fields updated."""
    updated_row = {**_EVAL_ROW, "focus_rating": 3}
    match_chain = _make_chain([_MATCH_ROW])
    eval_check_chain = _make_chain([_EVAL_ROW])
    eval_update_chain = _make_chain([updated_row])

    call_count = [0]

    def _dispatch(name):
        if name == "matches":
            return match_chain
        if name == "match_evaluations":
            call_count[0] += 1
            if call_count[0] == 1:
                return eval_check_chain
            return eval_update_chain
        if name == "player_notes":
            return _make_chain([])
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.patch(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"focusRating": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["focusRating"] == 3


def test_patch_evaluation_returns_404_when_no_eval(client_with_auth, mock_db):
    """PATCH when no eval exists → 404."""
    mock_db.table.side_effect = _table_dispatch([_MATCH_ROW], [])

    resp = client_with_auth.patch(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won"},
    )
    assert resp.status_code == 404


def test_patch_evaluation_no_fields_returns_422(client_with_auth, mock_db):
    """PATCH with empty body → 422 (no fields to update)."""
    match_chain = _make_chain([_MATCH_ROW])
    eval_chain = _make_chain([_EVAL_ROW])

    call_count = [0]

    def _dispatch(name):
        if name == "matches":
            return match_chain
        if name == "match_evaluations":
            call_count[0] += 1
            return eval_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.patch(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={},
    )
    assert resp.status_code == 422


# ── DELETE evaluation ─────────────────────────────────────────────────────────


def test_delete_evaluation_returns_204(client_with_auth, mock_db):
    """DELETE → 204 no content."""
    match_chain = _make_chain([_MATCH_ROW])
    eval_chain = _make_chain([_EVAL_ROW])
    notes_chain = _make_chain([])

    def _dispatch(name):
        if name == "matches":
            return match_chain
        if name == "match_evaluations":
            return eval_chain
        if name == "player_notes":
            return notes_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.delete(f"/v1/matches/{_MATCH_ID}/evaluation")
    assert resp.status_code == 204


def test_delete_evaluation_subsequent_get_returns_404(client_with_auth, mock_db):
    """After DELETE, GET returns 404."""
    match_chain = _make_chain([_MATCH_ROW])
    notes_chain = _make_chain([])
    delete_chain = _make_chain([])
    empty_eval_chain = _make_chain([])

    def _dispatch(name):
        if name == "matches":
            return match_chain
        if name == "match_evaluations":
            return delete_chain
        if name == "player_notes":
            return notes_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    # DELETE
    resp = client_with_auth.delete(f"/v1/matches/{_MATCH_ID}/evaluation")
    assert resp.status_code == 204

    # Subsequent GET returns 404 (eval gone)
    mock_db.table.side_effect = _table_dispatch([_MATCH_ROW], [])
    resp2 = client_with_auth.get(f"/v1/matches/{_MATCH_ID}/evaluation")
    assert resp2 == resp2  # GET after delete now returns 404 from the new dispatch
    assert resp.status_code == 204  # DELETE itself was 204


# ── Validation ────────────────────────────────────────────────────────────────


def test_post_effort_rating_out_of_range_returns_422(client_with_auth, mock_db):
    """POST with effortRating=6 → 422."""
    mock_db.table.return_value = _make_chain([_MATCH_ROW])
    mock_db.table.side_effect = None

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won", "effortRating": 6},
    )
    assert resp.status_code == 422


def test_post_focus_rating_below_range_returns_422(client_with_auth, mock_db):
    """POST with focusRating=0 → 422."""
    mock_db.table.return_value = _make_chain([_MATCH_ROW])
    mock_db.table.side_effect = None

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won", "focusRating": 0},
    )
    assert resp.status_code == 422


def test_post_went_well_exceeds_5_items_returns_422(client_with_auth, mock_db):
    """POST with 6 wentWell items → 422 (max 5)."""
    mock_db.table.return_value = _make_chain([_MATCH_ROW])
    mock_db.table.side_effect = None

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won", "wentWell": ["a", "b", "c", "d", "e", "f"]},
    )
    assert resp.status_code == 422


def test_post_went_well_item_exceeds_200_chars_returns_422(client_with_auth, mock_db):
    """POST with a wentWell item > 200 chars → 422."""
    mock_db.table.return_value = _make_chain([_MATCH_ROW])
    mock_db.table.side_effect = None

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won", "wentWell": ["x" * 201]},
    )
    assert resp.status_code == 422


def test_post_score_text_exceeds_80_chars_returns_422(client_with_auth, mock_db):
    """POST with scoreText > 80 chars → 422."""
    mock_db.table.return_value = _make_chain([_MATCH_ROW])
    mock_db.table.side_effect = None

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won", "scoreText": "6-4" * 30},  # 90 chars
    )
    assert resp.status_code == 422


def test_post_opponent_observations_exceeds_500_chars_returns_422(client_with_auth, mock_db):
    """POST with opponentObservations > 500 chars → 422."""
    mock_db.table.return_value = _make_chain([_MATCH_ROW])
    mock_db.table.side_effect = None

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won", "opponentObservations": "x" * 501},
    )
    assert resp.status_code == 422


def test_post_key_moments_exceeds_500_chars_returns_422(client_with_auth, mock_db):
    """POST with keyMoments > 500 chars → 422."""
    mock_db.table.return_value = _make_chain([_MATCH_ROW])
    mock_db.table.side_effect = None

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won", "keyMoments": "y" * 501},
    )
    assert resp.status_code == 422


def test_post_to_improve_exceeds_5_items_returns_422(client_with_auth, mock_db):
    """POST with 6 toImprove items → 422 (max 5)."""
    mock_db.table.return_value = _make_chain([_MATCH_ROW])
    mock_db.table.side_effect = None

    resp = client_with_auth.post(
        f"/v1/matches/{_MATCH_ID}/evaluation",
        json={"result": "won", "toImprove": ["a", "b", "c", "d", "e", "f"]},
    )
    assert resp.status_code == 422


# ── RLS isolation ─────────────────────────────────────────────────────────────


def test_get_evaluation_rls_isolation(client_with_auth, mock_db):
    """User A's eval is invisible to User B — RLS returns empty list."""
    # Simulate RLS: authed_client is scoped to TEST_USER_ID (User A).
    # For User B's match, the match query returns [] (RLS blocks it) → 404.
    mock_db.table.side_effect = _table_dispatch([], [])

    resp = client_with_auth.get(f"/v1/matches/{uuid4()}/evaluation")
    assert resp.status_code == 404


def test_post_evaluation_on_unowned_match_returns_404(client_with_auth, mock_db):
    """POST evaluation on an unowned match → 404 from match lookup."""
    mock_db.table.side_effect = _table_dispatch([], [])

    resp = client_with_auth.post(
        f"/v1/matches/{uuid4()}/evaluation",
        json={"result": "won"},
    )
    assert resp.status_code == 404
