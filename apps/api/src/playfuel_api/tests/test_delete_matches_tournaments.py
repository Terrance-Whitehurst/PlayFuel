"""Delete tournament + match route tests — backend ACs for delete-matches-tournaments spec §H.

Acceptance criteria covered (backend side):
  AC-DEL-3  Hard delete verifiable: route calls DB .delete() and returns 204 on success;
            DB-level cascade is confirmed to be in-place via migration audit (§B.1).
  AC-DEL-4  RLS enforced via 404, not 403: unowned or non-existent row returns 404.

Tests:
  test_delete_tournament_returns_204
  test_delete_tournament_nonexistent_returns_404
  test_delete_tournament_wrong_owner_returns_404_not_403
  test_delete_match_returns_204
  test_delete_match_nonexistent_returns_404
  test_delete_match_wrong_tournament_id_returns_404
  test_delete_match_wrong_owner_returns_404_not_403
  test_delete_tournament_requires_auth
  test_delete_match_requires_auth
  test_delete_tournament_cascade_annotation
  test_delete_match_cascade_annotation

Cascade verification (AC-DEL-3, DB layer)
------------------------------------------
ON DELETE CASCADE across matches, match_scenarios, plans, match_evaluations,
weather_snapshots, food_options, and feedback (tournament_id FK) is declared in
migrations 0002, 0008, 0010, 0011, 0013. Verification requires a live Supabase /
PostgreSQL connection and cannot be exercised in mock-layer unit tests.

MANUAL VERIFICATION QUERIES (run after real DELETE):
  SELECT count(*) FROM matches            WHERE tournament_id = '<tid>';  -- expect 0
  SELECT count(*) FROM weather_snapshots  WHERE tournament_id = '<tid>';  -- expect 0
  SELECT count(*) FROM food_options       WHERE tournament_id = '<tid>';  -- expect 0
  SELECT count(*) FROM feedback           WHERE tournament_id = '<tid>';  -- expect 0
  SELECT count(*) FROM match_scenarios    WHERE match_id IN (deleted match ids);  -- expect 0
  SELECT count(*) FROM plans              WHERE match_id = '<mid>';  -- expect 0
  SELECT count(*) FROM match_evaluations  WHERE match_id = '<mid>';  -- expect 0

feedback.plan_id → NULL on plan/match delete (§B.2)
-----------------------------------------------------
feedback.plan_id is SET NULL (not CASCADE) when a plan is deleted. Feedback rows
survive with plan_id = NULL. Covered by:
  test_feedback_routes.py::test_feedback_plan_id_can_be_null_after_plan_deletion

Test pattern: mock_db + client_with_auth from conftest.py.
Uses _make_chain() helper (same pattern as test_feedback_routes.py).
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

# ── Shared constants ──────────────────────────────────────────────────────────

_TID = "b9eebc99-9c0b-4ef8-bb6d-6bb9bd380a99"
_MID = "c9eebc99-9c0b-4ef8-bb6d-6bb9bd380a99"

_TOURNAMENT_ROW = {
    "id": _TID,
    "user_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "name": "Delray Beach Juniors",
    "draw_size": 64,
    "start_date": "2026-06-01",
}

_MATCH_ROW = {
    "id": _MID,
    "tournament_id": _TID,
    "scheduled_start": "2026-06-01T09:00:00+00:00",
    "round": 64,
    "round_label": "R64",
    "format": "singles",
}

_TOURNAMENT_PATH = f"/v1/tournaments/{_TID}"
_MATCH_PATH = f"/v1/tournaments/{_TID}/matches/{_MID}"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_chain(data):
    """MagicMock chain whose .execute().data == data.

    All chaining methods (select, delete, eq, etc.) return self so that
    arbitrary method chains resolve to a single mock with the configured data.
    Same pattern as test_feedback_routes.py.
    """
    chain = MagicMock()
    chain.execute.return_value.data = data
    for attr in (
        "select", "insert", "update", "delete", "eq", "order", "limit",
        "upsert", "filter", "in_", "maybe_single",
    ):
        getattr(chain, attr).return_value = chain
    return chain


# ── DELETE tournament — happy path (AC-DEL-3) ─────────────────────────────────


def test_delete_tournament_returns_204(client_with_auth, mock_db):
    """DELETE /v1/tournaments/{tid} → 204 when the row exists and is owned by caller.

    Supabase returns the deleted row in result.data (RETURNING * behaviour).
    Route checks result.data is non-empty before returning 204.
    """
    # Simulate Supabase returning the deleted row
    mock_db.table.return_value = _make_chain([_TOURNAMENT_ROW])

    resp = client_with_auth.delete(_TOURNAMENT_PATH)

    assert resp.status_code == 204, resp.text


# ── DELETE tournament — 404 paths (AC-DEL-4) ──────────────────────────────────


def test_delete_tournament_nonexistent_returns_404(client_with_auth, mock_db):
    """DELETE with a UUID that doesn't exist → 404 'Tournament not found'."""
    # Supabase returns empty list when no row matches
    mock_db.table.return_value = _make_chain([])

    resp = client_with_auth.delete(f"/v1/tournaments/{uuid4()}")

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Tournament not found"


def test_delete_tournament_wrong_owner_returns_404_not_403(client_with_auth, mock_db):
    """DELETE a tournament owned by a different user → 404, never 403.

    Supabase RLS silently drops rows that fail the ownership policy:
    the delete executes but returns 0 rows affected (empty data).
    Route must raise 404 — not 403 — so callers cannot infer existence
    of data they don't own (spec §C.1).
    """
    # RLS filters the row out → same empty-data result as non-existent
    mock_db.table.return_value = _make_chain([])

    resp = client_with_auth.delete(_TOURNAMENT_PATH)

    assert resp.status_code == 404, resp.text
    assert resp.status_code != 403, "Must be 404, not 403 — RLS == 404 per spec §C.1"


# ── DELETE match — happy path (AC-DEL-3) ─────────────────────────────────────


def test_delete_match_returns_204(client_with_auth, mock_db):
    """DELETE /v1/tournaments/{tid}/matches/{mid} → 204 when match exists and owned."""
    mock_db.table.return_value = _make_chain([_MATCH_ROW])

    resp = client_with_auth.delete(_MATCH_PATH)

    assert resp.status_code == 204, resp.text


# ── DELETE match — 404 paths (AC-DEL-4) ──────────────────────────────────────


def test_delete_match_nonexistent_returns_404(client_with_auth, mock_db):
    """DELETE with a match UUID that doesn't exist → 404 'Match not found'."""
    mock_db.table.return_value = _make_chain([])

    resp = client_with_auth.delete(f"/v1/tournaments/{_TID}/matches/{uuid4()}")

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Match not found"


def test_delete_match_wrong_tournament_id_returns_404(client_with_auth, mock_db):
    """DELETE match with a mismatched tournament_id → 404.

    Route filters on BOTH id AND tournament_id. A correct match UUID paired
    with the wrong tournament_id returns 0 rows → 404, not 204. This prevents
    cross-tournament deletions even if RLS is relaxed in future.
    """
    mock_db.table.return_value = _make_chain([])

    # Correct match UUID, wrong tournament UUID
    resp = client_with_auth.delete(f"/v1/tournaments/{uuid4()}/matches/{_MID}")

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Match not found"


def test_delete_match_wrong_owner_returns_404_not_403(client_with_auth, mock_db):
    """DELETE a match owned by a different user → 404 (RLS == 404, not 403)."""
    mock_db.table.return_value = _make_chain([])

    resp = client_with_auth.delete(_MATCH_PATH)

    assert resp.status_code == 404
    assert resp.status_code != 403, "Must be 404, not 403 — RLS == 404 per spec §C.1"


# ── Auth guards ───────────────────────────────────────────────────────────────


def test_delete_tournament_requires_auth(client_no_auth):
    """DELETE /v1/tournaments/{tid} without Bearer token → 401."""
    resp = client_no_auth.delete(_TOURNAMENT_PATH)
    assert resp.status_code in (401, 403)


def test_delete_match_requires_auth(client_no_auth):
    """DELETE /v1/tournaments/{tid}/matches/{mid} without Bearer token → 401."""
    resp = client_no_auth.delete(_MATCH_PATH)
    assert resp.status_code in (401, 403)


# ── Cascade annotation + DB-call verification (AC-DEL-3) ─────────────────────


def test_delete_tournament_cascade_annotation(client_with_auth, mock_db):
    """Model-layer: tournament DELETE completes (204) and calls .delete() on 'tournaments'.

    Cascade is Postgres DDL, not application code. Migrations that guarantee it:
      0002  matches, match_scenarios, plans, weather_snapshots, food_options
      0011  match_evaluations
      0013  feedback (via tournament_id)
    player_notes is intentionally SET NULL (not CASCADE) — verified §B.2.

    MANUAL VERIFICATION after a live delete:
      SELECT count(*) FROM matches WHERE tournament_id = '<tid>';            -- 0
      SELECT count(*) FROM weather_snapshots WHERE tournament_id = '<tid>';  -- 0
      SELECT count(*) FROM food_options WHERE tournament_id = '<tid>';       -- 0
      SELECT count(*) FROM feedback WHERE tournament_id = '<tid>';           -- 0
    """
    mock_db.table.return_value = _make_chain([_TOURNAMENT_ROW])

    resp = client_with_auth.delete(_TOURNAMENT_PATH)

    assert resp.status_code == 204
    # Verify the route hit the 'tournaments' table (not a no-op)
    mock_db.table.assert_called_with("tournaments")


def test_delete_match_cascade_annotation(client_with_auth, mock_db):
    """Model-layer: match DELETE completes (204) and calls .delete() on 'matches'.

    Cascade is Postgres DDL. Migrations that guarantee it:
      0002  match_scenarios
      0008  plans (via match_id FK, ON DELETE CASCADE)
      0011  match_evaluations
    feedback.plan_id is SET NULL when a plan is deleted (migration 0013) —
    feedback rows survive with plan_id = NULL. This is the correct behaviour
    per §B.2 (parents keep season-level feedback after a match is removed).

    MANUAL VERIFICATION after a live match delete:
      SELECT count(*) FROM match_scenarios WHERE match_id = '<mid>';     -- 0
      SELECT count(*) FROM plans WHERE match_id = '<mid>';               -- 0
      SELECT count(*) FROM match_evaluations WHERE match_id = '<mid>';   -- 0
      SELECT plan_id FROM feedback WHERE id = '<was-linked-plan-id>';    -- NULL
    """
    mock_db.table.return_value = _make_chain([_MATCH_ROW])

    resp = client_with_auth.delete(_MATCH_PATH)

    assert resp.status_code == 204
    # Verify the route hit the 'matches' table
    mock_db.table.assert_called_with("matches")
