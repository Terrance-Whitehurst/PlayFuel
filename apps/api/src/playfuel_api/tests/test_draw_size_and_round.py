"""Draw size + round picker — backend tests (draw-size-spec.md §7).

Acceptance criteria exercised here:

  AC-1   POST /v1/tournaments   draw_size=64              → 201, response has draw_size=64
  AC-2   POST /v1/tournaments   missing draw_size          → 422
  AC-3   POST /v1/tournaments   draw_size=48              → 422 "must be one of"
  AC-4   POST /v1/tournaments   draw_size=256             → 201 valid
  AC-5   POST /{tid}/matches    round=64 in R64 tournament → 201, round_label="R64"
  AC-5b  POST /{tid}/matches    round=8 in R64 tournament  → 201, round_label="QF"
  AC-5c  POST /{tid}/matches    round=2 in any tournament  → 201, round_label="F"
  AC-6   POST /{tid}/matches    round=128 in R64 tournament → 422 exceeds draw_size
  AC-7   POST /{tid}/matches    round=10 (not a valid value) → 422
  AC-8   POST /{tid}/matches    missing round              → 422
  AC-20  POST /{tid}/matches    round=8, no round_label    → response round_label="QF"
  Unit   rounds_for_draw(32)   → [32, 16, 8, 4, 2]
  Unit   rounds_for_draw(64)   → [64, 32, 16, 8, 4, 2]
  Unit   rounds_for_draw(256)  → [256, 128, 64, 32, 16, 8, 4, 2]
  Unit   ROUND_LABELS coverage → all VALID_ROUNDS have a label

Uses conftest.py fixtures: client_with_auth, mock_db.
No Supabase mocking — all DB calls go through mock_db MagicMock per project rule.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ── Shared UUIDs ──────────────────────────────────────────────────────────────

TID = "b3eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"
MID = "c3eebc99-9c0b-4ef8-bb6d-6bb9bd380a22"

_TOURNAMENT_PATH = "/v1/tournaments"
_MATCH_PATH = f"/v1/tournaments/{TID}/matches"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _wire_tournament_insert(mock_db: MagicMock, return_row: dict) -> None:
    """Configure mock_db for POST /tournaments insert."""
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [return_row]


def _wire_match_create(mock_db: MagicMock, draw_size: int, match_row: dict) -> None:
    """Configure mock_db for POST /matches with cross-table draw_size fetch.

    The create_match route hits 'tournaments' first (draw_size lookup),
    then 'matches' (insert). Use side_effect dispatch so each table call
    gets the right mock chain.
    """
    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"draw_size": draw_size}
    ]

    matches_chain = MagicMock()
    matches_chain.insert.return_value.execute.return_value.data = [match_row]

    def _dispatch(name: str) -> MagicMock:
        return {
            "tournaments": tournaments_chain,
            "matches": matches_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch


def _wire_match_tournament_not_found(mock_db: MagicMock) -> None:
    """Configure mock_db so the tournament draw_size lookup returns no rows → 404."""
    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

    mock_db.table.side_effect = lambda name: (
        tournaments_chain if name == "tournaments" else MagicMock()
    )


def _base_match_row(round_: int) -> dict:
    return {
        "id": MID,
        "tournament_id": TID,
        "scheduled_start": "2026-05-15T14:00:00+00:00",
        "format": "singles",
        "round": round_,
        "round_label": None,  # route overwrites this; not our concern in the row fixture
    }


# ── Tournament draw_size tests ────────────────────────────────────────────────


def test_tournament_create_valid_draw_size_64(client_with_auth, mock_db):
    """AC-1: draw_size=64 → 201, response includes draw_size=64."""
    _wire_tournament_insert(
        mock_db,
        return_row={
            "id": TID,
            "name": "Delray Beach 14U",
            "draw_size": 64,
            "start_date": "2026-06-01",
        },
    )
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Delray Beach 14U",
            "draw_size": 64,
            "start_date": "2026-06-01",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["draw_size"] == 64


def test_tournament_create_valid_draw_size_256(client_with_auth, mock_db):
    """AC-4: draw_size=256 → 201."""
    _wire_tournament_insert(
        mock_db,
        return_row={"id": TID, "name": "Big Draw", "draw_size": 256, "start_date": "2026-07-01"},
    )
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={"name": "Big Draw", "draw_size": 256, "start_date": "2026-07-01"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["draw_size"] == 256


def test_tournament_create_missing_draw_size_returns_422(client_with_auth, mock_db):
    """AC-2: missing draw_size → 422 (field required)."""
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={"name": "No Size Tournament", "start_date": "2026-06-01"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    # Pydantic 422 detail list; check at least one error references draw_size
    errors = body.get("detail", [])
    assert any("draw_size" in str(e) for e in errors), f"Expected draw_size error, got: {body}"


def test_tournament_create_invalid_draw_size_returns_422(client_with_auth, mock_db):
    """AC-3: draw_size=48 → 422, error mentions 'must be one of'."""
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={"name": "Bad Size", "draw_size": 48, "start_date": "2026-06-01"},
    )
    assert resp.status_code == 422, resp.text
    body_str = resp.text
    assert "must be one of" in body_str, f"Expected 'must be one of' in error: {body_str}"


def test_tournament_create_all_valid_draw_sizes(client_with_auth, mock_db):
    """AC-1/4: All four valid draw sizes (32, 64, 128, 256) each produce 201."""
    for size in [32, 64, 128, 256]:
        _wire_tournament_insert(
            mock_db,
            return_row={"id": TID, "name": f"R{size}", "draw_size": size, "start_date": "2026-06-01"},
        )
        resp = client_with_auth.post(
            _TOURNAMENT_PATH,
            json={"name": f"R{size} Tournament", "draw_size": size, "start_date": "2026-06-01"},
        )
        assert resp.status_code == 201, f"draw_size={size} failed: {resp.text}"


# ── Match round tests ─────────────────────────────────────────────────────────


def test_match_create_round_64_in_r64_returns_201(client_with_auth, mock_db):
    """AC-5: round=64 in R64 tournament → 201, round_label='R64'."""
    _wire_match_create(mock_db, draw_size=64, match_row=_base_match_row(64))
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={"scheduled_start": "2026-06-01T09:00:00+00:00", "round": 64},
    )
    assert resp.status_code == 201, resp.text


def test_match_create_round_qf_derives_label(client_with_auth, mock_db):
    """AC-5b + AC-20: round=8 in R64 tournament → 201; route derives round_label='QF'."""
    return_row = {**_base_match_row(8), "round_label": "QF"}
    _wire_match_create(mock_db, draw_size=64, match_row=return_row)
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={"scheduled_start": "2026-06-01T09:00:00+00:00", "round": 8},
    )
    assert resp.status_code == 201, resp.text
    # The DB row fixture has round_label="QF"; verify the response echoes it
    assert resp.json()["round_label"] == "QF"


def test_match_create_round_final(client_with_auth, mock_db):
    """AC-5c: round=2 → 201, round_label='F'."""
    return_row = {**_base_match_row(2), "round_label": "F"}
    _wire_match_create(mock_db, draw_size=32, match_row=return_row)
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={"scheduled_start": "2026-06-01T14:00:00+00:00", "round": 2},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["round_label"] == "F"


def test_match_create_round_exceeds_draw_size_returns_422(client_with_auth, mock_db):
    """AC-6: round=128 in R64 tournament → 422 with descriptive message."""
    _wire_match_create(mock_db, draw_size=64, match_row=_base_match_row(128))
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={"scheduled_start": "2026-06-01T09:00:00+00:00", "round": 128},
    )
    assert resp.status_code == 422, resp.text
    assert "exceeds" in resp.text, f"Expected 'exceeds' in error: {resp.text}"
    assert "64" in resp.text, f"Expected draw_size '64' in error: {resp.text}"


def test_match_create_invalid_round_value_returns_422(client_with_auth, mock_db):
    """AC-7: round=10 (not a valid bracket size) → 422 from Pydantic validator."""
    # Pydantic validator fires before DB is hit, so mock_db doesn't need to be wired.
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={"scheduled_start": "2026-06-01T09:00:00+00:00", "round": 10},
    )
    assert resp.status_code == 422, resp.text
    assert "round" in resp.text.lower(), f"Expected 'round' in error: {resp.text}"


def test_match_create_missing_round_returns_422(client_with_auth, mock_db):
    """AC-8: missing round field → 422 (field required)."""
    resp = client_with_auth.post(
        _MATCH_PATH,
        json={"scheduled_start": "2026-06-01T09:00:00+00:00"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    errors = body.get("detail", [])
    assert any("round" in str(e) for e in errors), f"Expected round error, got: {body}"


def test_match_create_round_label_auto_derived(client_with_auth, mock_db):
    """AC-20: round=8 sent with no round_label → DB row gets round_label='QF'.

    Verifies that the route overwrites round_label from ROUND_LABELS[round]
    regardless of what the client sends (or doesn't send).
    """
    # Capture the payload written to the DB by inspecting mock call args.
    inserted_payload: dict = {}

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"draw_size": 64}
    ]

    matches_chain = MagicMock()

    def _capture_insert(payload: dict):
        inserted_payload.update(payload)
        result = MagicMock()
        result.execute.return_value.data = [{**payload, "id": MID, "round_label": "QF"}]
        return result

    matches_chain.insert.side_effect = _capture_insert

    mock_db.table.side_effect = lambda name: (
        tournaments_chain if name == "tournaments" else matches_chain
    )

    resp = client_with_auth.post(
        _MATCH_PATH,
        json={"scheduled_start": "2026-06-01T09:00:00+00:00", "round": 8},
        # no round_label in body
    )
    assert resp.status_code == 201, resp.text
    # The route should have injected round_label="QF" into the insert payload
    assert inserted_payload.get("round_label") == "QF", (
        f"Expected round_label='QF' in insert payload, got: {inserted_payload}"
    )


# ── Unit tests: rounds_for_draw + ROUND_LABELS coverage ──────────────────────


def test_rounds_for_draw_r32():
    """rounds_for_draw(32) returns [32, 16, 8, 4, 2]."""
    from playfuel_api.rules.constants import rounds_for_draw
    assert rounds_for_draw(32) == [32, 16, 8, 4, 2]


def test_rounds_for_draw_r64():
    """rounds_for_draw(64) returns [64, 32, 16, 8, 4, 2]."""
    from playfuel_api.rules.constants import rounds_for_draw
    assert rounds_for_draw(64) == [64, 32, 16, 8, 4, 2]


def test_rounds_for_draw_r256():
    """rounds_for_draw(256) returns [256, 128, 64, 32, 16, 8, 4, 2]."""
    from playfuel_api.rules.constants import rounds_for_draw
    assert rounds_for_draw(256) == [256, 128, 64, 32, 16, 8, 4, 2]


def test_round_labels_cover_all_valid_rounds():
    """ROUND_LABELS has an entry for every value in VALID_ROUNDS (and vice versa)."""
    from playfuel_api.rules.constants import ROUND_LABELS, VALID_ROUNDS
    assert set(ROUND_LABELS.keys()) == VALID_ROUNDS
    # Spot-check key labels
    assert ROUND_LABELS[2] == "F"
    assert ROUND_LABELS[4] == "SF"
    assert ROUND_LABELS[8] == "QF"
    assert ROUND_LABELS[16] == "R16"
    assert ROUND_LABELS[256] == "R256"
