"""ACCOMMODATIONS_V1.md — API round-trip tests for tournament accommodation fields.

Tests:
    test_tournament_create_persists_accommodation_fields
        POST with all four accommodation fields (camelCase iOS payload) →
        201; fields round-trip; insert payload contains snake_case keys.

    test_tournament_create_camelcase_accommodation_decode_succeeds
        Explicit camelCase decode coverage — accommodationLat/Lng/Address/Kind
        are accepted via alias_generator=to_camel (food-bug root cause #3).

    test_tournament_create_omitted_accommodation_fields_absent_from_insert
        POST without accommodation fields → 201; fields absent from insert payload.

    test_tournament_create_accommodation_lat_only_returns_422   — §I.1 T-13
        Pydantic pair validator rejects lat without lng.

    test_tournament_create_accommodation_lng_only_returns_422   — §I.1 T-13 mirror
        Pydantic pair validator rejects lng without lat.

    test_tournament_update_clears_accommodation_with_explicit_nulls
        PUT with explicit null for all four fields → payload includes nulls (OQ-ACC-7).

    test_tournament_update_partial_update_leaves_accommodation_untouched
        PUT with only name changed → accommodation fields NOT in payload (OQ-ACC-7 regression).

    test_tournament_create_invalid_accommodation_kind_rejected
        Invalid kind (not 'home' | 'hotel') → 422.

Patterns mirror test_tournament_intl_fields.py: mock_db + client_with_auth from conftest.py.
No real Supabase network calls; no real JWT validation.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

_TOURNAMENT_PATH = "/v1/tournaments"
_TID = "f0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


def _wire_insert(mock_db: MagicMock, return_row: dict) -> None:
    """Configure mock_db for POST /tournaments insert."""
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [return_row]


def _wire_update(mock_db: MagicMock, return_row: dict) -> None:
    """Configure mock_db chain for PUT /tournaments/{tid} update."""
    (
        mock_db.table.return_value
        .update.return_value
        .eq.return_value
        .execute.return_value.data
    ) = [return_row]


# ── POST round-trip ───────────────────────────────────────────────────────────


def test_tournament_create_persists_accommodation_fields(client_with_auth, mock_db):
    """201 round-trip: all four accommodation fields with camelCase iOS payload."""
    return_row = {
        "id": _TID,
        "name": "Dallas Junior Slam",
        "draw_size": 32,
        "start_date": "2026-07-04",
        "accommodation_lat": 32.78,
        "accommodation_lng": -96.80,
        "accommodation_address": "100 Main St, Dallas, TX",
        "accommodation_kind": "hotel",
    }
    _wire_insert(mock_db, return_row)

    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Dallas Junior Slam",
            "drawSize": 32,
            "startDate": "2026-07-04",
            "accommodationLat": 32.78,
            "accommodationLng": -96.80,
            "accommodationAddress": "100 Main St, Dallas, TX",
            "accommodationKind": "hotel",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["accommodation_lat"] == pytest.approx(32.78)
    assert body["accommodation_lng"] == pytest.approx(-96.80)
    assert body["accommodation_address"] == "100 Main St, Dallas, TX"
    assert body["accommodation_kind"] == "hotel"

    # Verify insert payload has snake_case keys with correct values.
    insert_args = mock_db.table.return_value.insert.call_args
    assert insert_args is not None, "Expected insert() to be called"
    inserted_payload = insert_args[0][0]
    assert inserted_payload.get("accommodation_lat") == pytest.approx(32.78), inserted_payload
    assert inserted_payload.get("accommodation_lng") == pytest.approx(-96.80), inserted_payload
    assert inserted_payload.get("accommodation_address") == "100 Main St, Dallas, TX"
    assert inserted_payload.get("accommodation_kind") == "hotel"


def test_tournament_create_camelcase_accommodation_decode_succeeds(client_with_auth, mock_db):
    """Explicit camelCase decode coverage: alias_generator=to_camel must be in scope.

    This test isolates the food-bug root cause #3 pattern:
    if alias_generator is missing from TournamentCreate, all four camelCase keys
    decode as None, lat/lng pair check passes (None, None), insert receives no
    accommodation fields, and no 422 is raised — a silent data loss.
    """
    return_row = {
        "id": _TID,
        "name": "Home Event",
        "draw_size": 64,
        "start_date": "2026-08-01",
        "accommodation_lat": 33.10,
        "accommodation_lng": -97.10,
        "accommodation_kind": "home",
    }
    _wire_insert(mock_db, return_row)

    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Home Event",
            "drawSize": 64,
            "startDate": "2026-08-01",
            "accommodationLat": 33.10,
            "accommodationLng": -97.10,
            "accommodationKind": "home",
        },
    )
    assert resp.status_code == 201, resp.text

    insert_args = mock_db.table.return_value.insert.call_args
    inserted_payload = insert_args[0][0]
    # If alias_generator is missing, these will be None (silent failure).
    assert inserted_payload.get("accommodation_lat") == pytest.approx(33.10), (
        f"accommodation_lat decoded as None — alias_generator=to_camel missing! "
        f"insert payload: {inserted_payload}"
    )
    assert inserted_payload.get("accommodation_lng") == pytest.approx(-97.10), (
        f"accommodation_lng decoded as None — alias_generator=to_camel missing! "
        f"insert payload: {inserted_payload}"
    )
    assert inserted_payload.get("accommodation_kind") == "home", (
        f"accommodation_kind decoded as None — alias_generator=to_camel missing! "
        f"insert payload: {inserted_payload}"
    )


def test_tournament_create_omitted_accommodation_fields_absent_from_insert(
    client_with_auth, mock_db
):
    """POST without accommodation fields → 201; fields absent from insert payload."""
    _wire_insert(
        mock_db,
        return_row={
            "id": _TID,
            "name": "Venue-Local Tournament",
            "draw_size": 32,
            "start_date": "2026-06-15",
        },
    )

    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Venue-Local Tournament",
            "drawSize": 32,
            "startDate": "2026-06-15",
        },
    )
    assert resp.status_code == 201, resp.text

    insert_args = mock_db.table.return_value.insert.call_args
    inserted_payload = insert_args[0][0]
    # exclude_none=True on create — null optional fields must not appear.
    assert "accommodation_lat" not in inserted_payload, (
        f"accommodation_lat should be absent for venue-local tournament: {inserted_payload}"
    )
    assert "accommodation_lng" not in inserted_payload, (
        f"accommodation_lng should be absent for venue-local tournament: {inserted_payload}"
    )
    assert "accommodation_address" not in inserted_payload
    assert "accommodation_kind" not in inserted_payload


# ── Pair validator tests (T-13) ───────────────────────────────────────────────


def test_tournament_create_accommodation_lat_only_returns_422(client_with_auth, mock_db):
    """§I.1 T-13 — accommodationLat without accommodationLng → 422 (pair validator)."""
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Bad Pair",
            "drawSize": 32,
            "startDate": "2026-06-15",
            "accommodationLat": 32.78,
            # accommodationLng intentionally omitted
        },
    )
    assert resp.status_code == 422, resp.text
    # DB insert must never be called.
    mock_db.table.return_value.insert.assert_not_called()


def test_tournament_create_accommodation_lng_only_returns_422(client_with_auth, mock_db):
    """accommodationLng without accommodationLat → 422 (pair validator mirrors T-13)."""
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Bad Pair",
            "drawSize": 32,
            "startDate": "2026-06-15",
            "accommodationLng": -96.80,
            # accommodationLat intentionally omitted
        },
    )
    assert resp.status_code == 422, resp.text
    mock_db.table.return_value.insert.assert_not_called()


def test_tournament_create_invalid_accommodation_kind_rejected(client_with_auth, mock_db):
    """Invalid accommodationKind (not 'home' | 'hotel') → 422."""
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Bad Kind",
            "drawSize": 32,
            "startDate": "2026-06-15",
            "accommodationLat": 32.78,
            "accommodationLng": -96.80,
            "accommodationKind": "airbnb",  # not in Literal['home', 'hotel']
        },
    )
    assert resp.status_code == 422, resp.text
    mock_db.table.return_value.insert.assert_not_called()


# ── PUT (OQ-ACC-7) tests ──────────────────────────────────────────────────────


def test_tournament_update_clears_accommodation_with_explicit_nulls(
    client_with_auth, mock_db
):
    """OQ-ACC-7 fix: PUT with explicit null for accommodation fields clears them in DB.

    With exclude_unset=True, explicit null values ARE included in the payload,
    allowing the parent to clear accommodation once set.
    """
    _wire_update(
        mock_db,
        return_row={
            "id": _TID,
            "name": "Cleared Tournament",
            "draw_size": 32,
            "start_date": "2026-07-04",
            "accommodation_lat": None,
            "accommodation_lng": None,
            "accommodation_address": None,
            "accommodation_kind": None,
        },
    )

    resp = client_with_auth.put(
        f"{_TOURNAMENT_PATH}/{_TID}",
        json={
            "accommodationLat": None,
            "accommodationLng": None,
            "accommodationAddress": None,
            "accommodationKind": None,
        },
    )
    assert resp.status_code == 200, resp.text

    update_args = mock_db.table.return_value.update.call_args
    assert update_args is not None, "Expected update() to be called"
    update_payload = update_args[0][0]
    # With exclude_unset=True, explicit nulls ARE included (OQ-ACC-7 fix).
    assert "accommodation_lat" in update_payload, (
        f"accommodation_lat should be in update payload (explicit null): {update_payload}"
    )
    assert update_payload["accommodation_lat"] is None
    assert "accommodation_lng" in update_payload
    assert update_payload["accommodation_lng"] is None
    assert "accommodation_address" in update_payload
    assert update_payload["accommodation_address"] is None
    assert "accommodation_kind" in update_payload
    assert update_payload["accommodation_kind"] is None


def test_tournament_update_partial_update_leaves_accommodation_untouched(
    client_with_auth, mock_db
):
    """OQ-ACC-7 regression: PUT with only name → accommodation fields NOT in payload.

    With exclude_unset=True, fields omitted from the request body are excluded
    from the DB update payload — partial update semantics are preserved.
    """
    _wire_update(
        mock_db,
        return_row={
            "id": _TID,
            "name": "Renamed Tournament",
            "draw_size": 32,
            "start_date": "2026-07-04",
        },
    )

    resp = client_with_auth.put(
        f"{_TOURNAMENT_PATH}/{_TID}",
        json={"name": "Renamed Tournament"},
    )
    assert resp.status_code == 200, resp.text

    update_args = mock_db.table.return_value.update.call_args
    assert update_args is not None
    update_payload = update_args[0][0]
    # Only 'name' should be in the payload — accommodation fields were not sent.
    assert update_payload == {"name": "Renamed Tournament"}, (
        f"Expected only {{name}} in update payload, got: {update_payload}"
    )
    assert "accommodation_lat" not in update_payload
    assert "accommodation_lng" not in update_payload
    assert "accommodation_address" not in update_payload
    assert "accommodation_kind" not in update_payload
