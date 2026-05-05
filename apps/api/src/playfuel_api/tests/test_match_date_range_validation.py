"""Match date-range validation tests — backend spec §4.2 (add-match-date-picker-constraint).

Validates that POST /v1/tournaments/{tid}/matches and PUT /v1/tournaments/{tid}/matches/{mid}
reject scheduled_start values that fall outside the parent tournament's date range.

Acceptance criteria exercised here:
  test_create_match_before_tournament_start_returns_422
  test_create_match_after_tournament_end_returns_422
  test_create_match_on_start_date_succeeds
  test_create_match_on_end_date_succeeds
  test_create_match_on_single_day_tournament_succeeds
  test_create_match_one_day_after_single_day_tournament_returns_422
  test_update_match_to_out_of_range_date_returns_422

Timezone note (OQ-DATE-1):
  Comparison is date-level only. scheduled_start.date() is used directly — correct for
  UTC-aligned timestamps and naive datetimes (typical iOS payload). A match at 11 PM local
  in a UTC-5 venue sent as a naive datetime reads as 2026-06-16, not 2026-06-17, so the
  boundary is accurate in practice. A venue_tz field would close the UTC-midnight edge case.

Test pattern: mock_db + client_with_auth from conftest.py.
Dispatch pattern mirrors test_draw_size_and_round.py::_wire_match_create.
"""
from __future__ import annotations

from unittest.mock import MagicMock

# ── Shared constants ──────────────────────────────────────────────────────────

_TID = "b8eebc99-9c0b-4ef8-bb6d-6bb9bd380a88"
_MID = "c8eebc99-9c0b-4ef8-bb6d-6bb9bd380a88"

# Multi-day tournament: June 14–16 2026
_T_START = "2026-06-14"
_T_END = "2026-06-16"

_MATCH_PATH = f"/v1/tournaments/{_TID}/matches"
_MATCH_DETAIL_PATH = f"/v1/tournaments/{_TID}/matches/{_MID}"

# Minimal valid match body (round=64 is in VALID_ROUNDS; format omitted → singles default)
_BASE_MATCH_BODY = {
    "round": 64,
}

_MATCH_ROW = {
    "id": _MID,
    "tournament_id": _TID,
    "round": 64,
    "round_label": "R64",
    "format": "singles",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _wire_create(
    mock_db: MagicMock,
    *,
    start: str,
    end: str | None,
    ok: bool,
) -> None:
    """Wire mock_db for POST /matches with full tournament date fields.

    Dispatches by table name:
      'tournaments' → draw_size + start_date + end_date (for draw_size + date range checks)
      'matches'     → the inserted match row (only reached on success path)

    The 'matches' chain must support the insert path fully. On the 422 (out-of-range)
    path it is never called, but the dispatcher must not raise a KeyError when
    mock_db.table("matches") is accessed by MagicMock fallback.
    """
    t_data = {"draw_size": 64, "start_date": start}
    if end is not None:
        t_data["end_date"] = end

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        t_data
    ]

    matches_chain = MagicMock()
    match_return = [dict(_MATCH_ROW)] if ok else []
    matches_chain.insert.return_value.execute.return_value.data = match_return

    def _dispatch(name: str) -> MagicMock:
        return {"tournaments": tournaments_chain, "matches": matches_chain}.get(
            name, MagicMock()
        )

    mock_db.table.side_effect = _dispatch


def _wire_update(
    mock_db: MagicMock,
    *,
    start: str,
    end: str | None,
) -> None:
    """Wire mock_db for PUT /matches/{mid} when scheduled_start is being changed.

    update_match flow (with scheduled_start in payload):
      1. client.table("tournaments").select("start_date,end_date")... → date range check
      2. client.table("matches").update(...)... → the actual update (only if date OK)

    For the 422 case the matches table is never reached, but the dispatcher
    must not crash on MagicMock fallback.
    """
    t_data = {"start_date": start}
    if end is not None:
        t_data["end_date"] = end

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        t_data
    ]

    matches_chain = MagicMock()
    matches_chain.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
        {**_MATCH_ROW, "scheduled_start": "2026-06-16T21:00:00"}
    ]

    def _dispatch(name: str) -> MagicMock:
        return {"tournaments": tournaments_chain, "matches": matches_chain}.get(
            name, MagicMock()
        )

    mock_db.table.side_effect = _dispatch


# ── CREATE tests ──────────────────────────────────────────────────────────────


def test_create_match_before_tournament_start_returns_422(client_with_auth, mock_db):
    """POST with scheduled_start one day before tournament start → 422.

    Tournament: 2026-06-14 through 2026-06-16.
    Match: 2026-06-13 (before start_date) → rejected.
    """
    _wire_create(mock_db, start=_T_START, end=_T_END, ok=False)

    resp = client_with_auth.post(
        _MATCH_PATH,
        json={**_BASE_MATCH_BODY, "scheduled_start": "2026-06-13T09:00:00"},
    )

    assert resp.status_code == 422, resp.text
    assert "tournament date range" in resp.json()["detail"]
    assert "2026-06-14" in resp.json()["detail"]


def test_create_match_after_tournament_end_returns_422(client_with_auth, mock_db):
    """POST with scheduled_start one day after tournament end → 422.

    Tournament: 2026-06-14 through 2026-06-16.
    Match: 2026-06-17 (after end_date) → rejected.
    """
    _wire_create(mock_db, start=_T_START, end=_T_END, ok=False)

    resp = client_with_auth.post(
        _MATCH_PATH,
        json={**_BASE_MATCH_BODY, "scheduled_start": "2026-06-17T09:00:00"},
    )

    assert resp.status_code == 422, resp.text
    assert "tournament date range" in resp.json()["detail"]
    assert "2026-06-16" in resp.json()["detail"]


def test_create_match_on_start_date_succeeds(client_with_auth, mock_db):
    """POST with scheduled_start == tournament start_date → 201.

    Start of first day is explicitly valid (inclusive left bound).
    """
    _wire_create(mock_db, start=_T_START, end=_T_END, ok=True)

    resp = client_with_auth.post(
        _MATCH_PATH,
        json={**_BASE_MATCH_BODY, "scheduled_start": "2026-06-14T08:00:00"},
    )

    assert resp.status_code == 201, resp.text


def test_create_match_on_end_date_succeeds(client_with_auth, mock_db):
    """POST with scheduled_start on tournament end_date → 201.

    End of last day is explicitly valid (inclusive right bound).
    """
    _wire_create(mock_db, start=_T_START, end=_T_END, ok=True)

    resp = client_with_auth.post(
        _MATCH_PATH,
        json={**_BASE_MATCH_BODY, "scheduled_start": "2026-06-16T21:00:00"},
    )

    assert resp.status_code == 201, resp.text


def test_create_match_on_single_day_tournament_succeeds(client_with_auth, mock_db):
    """POST with scheduled_start == start_date == end_date → 201.

    Single-day tournament (start == end). Match on that day is accepted.
    end_date is present and equal to start_date (not null).
    """
    _wire_create(mock_db, start="2026-06-15", end="2026-06-15", ok=True)

    resp = client_with_auth.post(
        _MATCH_PATH,
        json={**_BASE_MATCH_BODY, "scheduled_start": "2026-06-15T09:00:00"},
    )

    assert resp.status_code == 201, resp.text


def test_create_match_on_single_day_tournament_null_end_succeeds(client_with_auth, mock_db):
    """POST with scheduled_start == start_date when end_date is NULL → 201.

    When end_date is null, server treats it as a single-day tournament (end == start).
    Match on start_date is valid.
    """
    _wire_create(mock_db, start="2026-06-15", end=None, ok=True)

    resp = client_with_auth.post(
        _MATCH_PATH,
        json={**_BASE_MATCH_BODY, "scheduled_start": "2026-06-15T09:00:00"},
    )

    assert resp.status_code == 201, resp.text


def test_create_match_one_day_after_single_day_tournament_returns_422(
    client_with_auth, mock_db
):
    """POST with scheduled_start = start_date + 1 on a single-day tournament → 422.

    Both start_date == end_date == 2026-06-15. Match on 2026-06-16 is outside.
    Also covers the null end_date path (server falls back to end = start).
    """
    _wire_create(mock_db, start="2026-06-15", end=None, ok=False)

    resp = client_with_auth.post(
        _MATCH_PATH,
        json={**_BASE_MATCH_BODY, "scheduled_start": "2026-06-16T09:00:00"},
    )

    assert resp.status_code == 422, resp.text
    assert "tournament date range" in resp.json()["detail"]


# ── UPDATE test ───────────────────────────────────────────────────────────────


def test_update_match_to_out_of_range_date_returns_422(client_with_auth, mock_db):
    """PUT /matches/{mid} with scheduled_start outside tournament range → 422.

    Tournament: 2026-06-14 through 2026-06-16.
    Update payload: scheduled_start = 2026-06-18 (two days after end) → rejected.

    The route fetches the tournament date range only when scheduled_start is
    included in the update payload — this test confirms that fetch + check fires.
    """
    _wire_update(mock_db, start=_T_START, end=_T_END)

    resp = client_with_auth.put(
        _MATCH_DETAIL_PATH,
        json={"scheduled_start": "2026-06-18T09:00:00"},
    )

    assert resp.status_code == 422, resp.text
    assert "tournament date range" in resp.json()["detail"]
    assert "2026-06-16" in resp.json()["detail"]
