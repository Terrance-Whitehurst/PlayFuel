"""Round progression — backend tests (round-progression-and-formats.md §J.1-2).

Tests the _validate_round_progression helper wired into create_match and
update_match in routes/matches.py.

The API enforces the NO-DUPLICATE invariant: two matches in the same
(tournament_id, format) stream cannot share a round value.

Linear progression (R64→R32→...) is iOS-side UX only — NOT enforced here.
The API accepts any valid round value (within draw_size) in any order.

Tests:
  RP-1  CREATE R64 singles (no prior match)                             → 201
  RP-2  CREATE second R64 singles in same tournament                    → 422, message
  RP-3  CREATE R64 doubles when R64 singles already exists              → 201 (stream isolation)
  RP-4  CREATE R64 singles in a different tournament (T2)               → 201 (cross-TID isolation)
  RP-5  UPDATE R32 → R64 when R64 already exists in same stream         → 422, message
  RP-6  UPDATE same match R32 → R32 (value unchanged)                   → 200 (no self-conflict)
  RP-7  CREATE R32 when no R64 yet in stream (skip-ahead)               → 201 (not server-enforced)
  RP-8  CREATE without format field                                      → 201 (check skipped)
"""
from __future__ import annotations

from unittest.mock import MagicMock

# ── Shared UUIDs ──────────────────────────────────────────────────────────────

_TID = "a9eebc99-9c0b-4ef8-bb6d-6bb9bd380a99"
_TID2 = "b9eebc99-9c0b-4ef8-bb6d-6bb9bd380a99"
_MID = "c9eebc99-9c0b-4ef8-bb6d-6bb9bd380a99"
_MID2 = "d9eebc99-9c0b-4ef8-bb6d-6bb9bd380a99"

_MATCH_CREATE_PATH = f"/v1/tournaments/{_TID}/matches"
_MATCH_CREATE_T2 = f"/v1/tournaments/{_TID2}/matches"
_MATCH_UPDATE_PATH = f"/v1/tournaments/{_TID}/matches/{_MID}"


# ── Row fixture ───────────────────────────────────────────────────────────────


def _base_row(round_: int, fmt: str = "singles") -> dict:
    return {
        "id": _MID,
        "tournament_id": _TID,
        "scheduled_start": "2026-07-01T09:00:00+00:00",
        "format": fmt,
        "round": round_,
        "round_label": None,
        "is_done": False,
        "done_at": None,
    }


# ── Mock helpers ──────────────────────────────────────────────────────────────


def _wire_create(
    mock_db: MagicMock,
    *,
    draw_size: int = 64,
    round_already_exists: bool = False,
    match_row: dict | None = None,
) -> None:
    """Wire mock_db for POST /{tid}/matches with round progression check.

    Call sequence in create_match (relevant DB calls):
      1. client.table("tournaments").select(...)  → draw_size (no start_date → skip date check)
      2. client.table("matches").select("id").eq.eq.eq.limit(1).execute()  → uniqueness check
      3. client.table("matches").insert(payload).execute()  → insert

    Steps 2 and 3 both go through "matches" dispatch.  They use different
    methods (.select vs .insert) on the same matches_chain, so they don't
    interfere with each other.
    """
    if match_row is None:
        match_row = _base_row(64)

    tournaments_chain = MagicMock()
    # No start_date in return → _validate_scheduled_start_in_range is skipped
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"draw_size": draw_size}
    ]

    matches_chain = MagicMock()
    # Uniqueness check: .select("id").eq.eq.eq.limit(1).execute().data
    existing = [{"id": _MID2}] if round_already_exists else []
    (
        matches_chain.select.return_value
        .eq.return_value
        .eq.return_value
        .eq.return_value
        .limit.return_value
        .execute.return_value.data
    ) = existing
    # Insert
    matches_chain.insert.return_value.execute.return_value.data = [match_row]

    def _dispatch(name: str) -> MagicMock:
        return {"tournaments": tournaments_chain, "matches": matches_chain}.get(
            name, MagicMock()
        )

    mock_db.table.side_effect = _dispatch


def _wire_update(
    mock_db: MagicMock,
    *,
    round_already_exists: bool = False,
    match_row: dict | None = None,
) -> None:
    """Wire mock_db for PUT /{tid}/matches/{mid} with round progression check.

    Update body contains `round` and `format` but NOT `scheduled_start`, so the
    tournaments table is never queried.  DB call sequence:
      1. client.table("matches").select("id").eq.eq.eq.neq.limit(1).execute()
         → uniqueness check (with self-exclusion via neq)
      2. client.table("matches").update(payload).eq.eq.execute()
         → actual update

    Both calls go through "matches" dispatch but use .select vs .update, so
    they don't interfere.
    """
    if match_row is None:
        match_row = _base_row(64)

    matches_chain = MagicMock()
    # Uniqueness check with self-exclusion: .select("id").eq.eq.eq.neq.limit(1).execute().data
    existing = [{"id": _MID2}] if round_already_exists else []
    (
        matches_chain.select.return_value
        .eq.return_value
        .eq.return_value
        .eq.return_value
        .neq.return_value
        .limit.return_value
        .execute.return_value.data
    ) = existing
    # Actual update: .update(payload).eq.eq.execute().data
    (
        matches_chain.update.return_value
        .eq.return_value
        .eq.return_value
        .execute.return_value.data
    ) = [match_row]

    mock_db.table.side_effect = lambda name: {"matches": matches_chain}.get(
        name, MagicMock()
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_rp1_create_first_singles_r64_returns_201(client_with_auth, mock_db):
    """RP-1: First R64 singles match (stream empty) → 201 Created."""
    _wire_create(mock_db, draw_size=64, round_already_exists=False)
    resp = client_with_auth.post(
        _MATCH_CREATE_PATH,
        json={
            "scheduled_start": "2026-07-01T09:00:00+00:00",
            "round": 64,
            "format": "singles",
        },
    )
    assert resp.status_code == 201, resp.text


def test_rp2_duplicate_singles_r64_returns_422(client_with_auth, mock_db):
    """RP-2: Second R64 singles in same tournament → 422 with verbatim error snippet."""
    _wire_create(mock_db, draw_size=64, round_already_exists=True)
    resp = client_with_auth.post(
        _MATCH_CREATE_PATH,
        json={
            "scheduled_start": "2026-07-01T09:00:00+00:00",
            "round": 64,
            "format": "singles",
        },
    )
    assert resp.status_code == 422, resp.text
    body_str = resp.text
    assert "already exists for singles" in body_str, (
        f"Expected 'already exists for singles' in error: {body_str}"
    )
    assert "64" in body_str, f"Expected round number '64' in error: {body_str}"


def test_rp3_singles_and_doubles_r64_are_independent(client_with_auth, mock_db):
    """RP-3: R64 singles exists; creating R64 doubles in same tournament → 201.

    The uniqueness check queries (tournament_id, format='doubles', round=64).
    Since format='doubles' is a different stream, the existing singles match
    is invisible to this check.  Mock simulates 'no duplicate found in doubles
    stream' → 201.
    """
    _wire_create(
        mock_db,
        draw_size=64,
        round_already_exists=False,  # doubles stream has no R64 yet
        match_row={**_base_row(64, fmt="doubles"), "doubles_format": "best_of_3"},
    )
    resp = client_with_auth.post(
        _MATCH_CREATE_PATH,
        json={
            "scheduled_start": "2026-07-01T09:00:00+00:00",
            "round": 64,
            "format": "doubles",
            "doubles_format": "best_of_3",
        },
    )
    assert resp.status_code == 201, resp.text


def test_rp4_cross_tournament_isolation(client_with_auth, mock_db):
    """RP-4: R64 singles in T2 succeeds even though T1 already has R64 singles.

    The uniqueness check queries with tournament_id=T2.  T1's match is not
    visible to that query.  Mock returns [] for T2 → 201.
    """
    _wire_create(mock_db, draw_size=64, round_already_exists=False)
    resp = client_with_auth.post(
        _MATCH_CREATE_T2,  # different tournament
        json={
            "scheduled_start": "2026-07-01T09:00:00+00:00",
            "round": 64,
            "format": "singles",
        },
    )
    assert resp.status_code == 201, resp.text


def test_rp5_update_round_to_existing_round_returns_422(client_with_auth, mock_db):
    """RP-5: Update a match's round to a value that already exists in the same stream → 422."""
    _wire_update(mock_db, round_already_exists=True)
    resp = client_with_auth.put(
        _MATCH_UPDATE_PATH,
        json={"round": 64, "format": "singles"},
    )
    assert resp.status_code == 422, resp.text
    body_str = resp.text
    assert "already exists for singles" in body_str, (
        f"Expected 'already exists for singles' in error: {body_str}"
    )


def test_rp6_update_same_round_value_returns_200(client_with_auth, mock_db):
    """RP-6: Update a match's round to its current value (unchanged) → 200.

    The neq("id", mid) in the uniqueness check excludes the match itself, so
    it can't conflict with its own existing round value.
    """
    _wire_update(
        mock_db,
        round_already_exists=False,   # self-exclusion means the match doesn't find itself
        match_row=_base_row(32),
    )
    resp = client_with_auth.put(
        _MATCH_UPDATE_PATH,
        json={"round": 32, "format": "singles"},
    )
    assert resp.status_code == 200, resp.text


def test_rp7_create_r32_without_prior_r64_returns_201(client_with_auth, mock_db):
    """RP-7: Create R32 when no R64 exists yet in the stream → 201.

    Linear progression is iOS UX only.  The API does not enforce that R64 must
    precede R32.  A parent who forgot to log the first round can backfill.
    """
    _wire_create(mock_db, draw_size=64, round_already_exists=False, match_row=_base_row(32))
    resp = client_with_auth.post(
        _MATCH_CREATE_PATH,
        json={
            "scheduled_start": "2026-07-01T09:00:00+00:00",
            "round": 32,
            "format": "singles",
        },
    )
    assert resp.status_code == 201, resp.text


def test_rp8_create_without_format_skips_check(client_with_auth, mock_db):
    """RP-8: format absent from request body → uniqueness check skipped → 201.

    _validate_round_progression returns early when match_format is None so no
    matches.select call is made.  Mock only needs tournaments + matches.insert.
    """
    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"draw_size": 64}
    ]
    matches_chain = MagicMock()
    matches_chain.insert.return_value.execute.return_value.data = [_base_row(64)]

    def _dispatch(name: str) -> MagicMock:
        return {"tournaments": tournaments_chain, "matches": matches_chain}.get(
            name, MagicMock()
        )

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        _MATCH_CREATE_PATH,
        json={
            "scheduled_start": "2026-07-01T09:00:00+00:00",
            "round": 64,
            # "format" intentionally absent → body.format == None → check skipped
        },
    )
    assert resp.status_code == 201, resp.text
