"""Phase A international rollout — smoke tests for time_zone + venue_country.

Tests:
    test_tournament_create_persists_time_zone_and_venue_country
        POST /v1/tournaments with timeZone + venueCountry (camelCase, matching iOS
        payload shape) → 201, both fields round-trip in the response, and the
        mocked Supabase insert was called with snake_case keys time_zone + venue_country.

    test_tournament_create_omitted_intl_fields_default_to_none
        POST /v1/tournaments WITHOUT timeZone / venueCountry (legacy iOS behavior)
        → 201, both fields absent from the insert payload (exclude_none=True drops them),
        response does not include them (Supabase returns whatever the mock returns).

Patterns mirror test_draw_size_and_round.py: mock_db + client_with_auth from conftest.py.
No real Supabase network calls; no real JWT validation.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

_TOURNAMENT_PATH = "/v1/tournaments"

TID = "f0eebc99-9c0b-4ef8-bb6d-6bb9bd380a99"


def _wire_tournament_insert(mock_db: MagicMock, return_row: dict) -> None:
    """Configure mock_db for POST /tournaments insert."""
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [return_row]


# ─────────────────────────────────────────────────────────────────────────────

def test_tournament_create_persists_time_zone_and_venue_country(
    client_with_auth, mock_db
):
    """201 round-trip: camelCase timeZone + venueCountry → snake_case in DB insert."""
    _wire_tournament_insert(
        mock_db,
        return_row={
            "id": TID,
            "name": "Club Reforma Open",
            "draw_size": 32,
            "start_date": "2026-07-04",
            "time_zone": "America/Mexico_City",
            "venue_country": "MX",
        },
    )

    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Club Reforma Open",
            "drawSize": 32,
            "startDate": "2026-07-04",
            "timeZone": "America/Mexico_City",
            "venueCountry": "MX",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["time_zone"] == "America/Mexico_City"
    assert body["venue_country"] == "MX"

    # Verify the mocked Supabase insert received snake_case keys.
    insert_call_args = mock_db.table.return_value.insert.call_args
    assert insert_call_args is not None, "Expected insert() to be called"
    inserted_payload = insert_call_args[0][0]  # first positional arg to insert()
    assert inserted_payload.get("time_zone") == "America/Mexico_City", (
        f"Expected time_zone='America/Mexico_City' in insert payload, got: {inserted_payload}"
    )
    assert inserted_payload.get("venue_country") == "MX", (
        f"Expected venue_country='MX' in insert payload, got: {inserted_payload}"
    )


def test_tournament_create_omitted_intl_fields_default_to_none(
    client_with_auth, mock_db
):
    """Legacy iOS payload without timeZone/venueCountry → 201, fields absent from insert."""
    _wire_tournament_insert(
        mock_db,
        return_row={
            "id": TID,
            "name": "Dallas Junior Open",
            "draw_size": 64,
            "start_date": "2026-06-01",
        },
    )

    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Dallas Junior Open",
            "drawSize": 64,
            "startDate": "2026-06-01",
        },
    )

    assert resp.status_code == 201, resp.text

    # With exclude_none=True, absent optional fields must NOT appear in the insert payload.
    insert_call_args = mock_db.table.return_value.insert.call_args
    assert insert_call_args is not None, "Expected insert() to be called"
    inserted_payload = insert_call_args[0][0]
    assert "time_zone" not in inserted_payload, (
        f"time_zone should be absent from insert payload for legacy request, got: {inserted_payload}"
    )
    assert "venue_country" not in inserted_payload, (
        f"venue_country should be absent from insert payload for legacy request, got: {inserted_payload}"
    )


# ── 3. preferred_language field (INTL-SEC-5 / Phase C-infrastructure) ──────────

@pytest.mark.parametrize("lang,label", [
    ("en", "English baseline"),
    ("es", "Spanish Tier-1"),
])
def test_preferred_language_valid_values_accepted(
    client_with_auth, mock_db, lang: str, label: str
):
    """Tier-1 language codes 'en' and 'es' → 201, field persisted in insert payload."""
    return_row = {
        "id": TID, "name": "T", "draw_size": 32,
        "start_date": "2026-06-01", "preferred_language": lang,
    }
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [return_row]
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "T", "drawSize": 32, "startDate": "2026-06-01",
            "preferredLanguage": lang,
        },
    )
    assert resp.status_code == 201, (
        f"Expected 201 for preferredLanguage={lang!r} ({label}), got {resp.status_code}: {resp.text}"
    )
    insert_args = mock_db.table.return_value.insert.call_args
    assert insert_args is not None
    insert_payload: dict = insert_args[0][0]
    assert insert_payload.get("preferred_language") == lang, (
        f"preferred_language not in insert payload for {lang!r}: {insert_payload}"
    )


@pytest.mark.parametrize("bad_lang,label", [
    ("fr", "French — not in Tier-1 Literal yet"),
    ("de", "German — not in Tier-1 Literal yet"),
    ("pt", "Portuguese — not in Tier-1 Literal yet"),
    ("EN", "uppercase — Literal is case-sensitive"),
    ("en-US", "BCP-47 tag — Literal only accepts bare ISO 639-1"),
    ("spanish", "full word — not a valid ISO 639-1 code"),
])
def test_preferred_language_out_of_allowlist_rejected_with_422(
    client_with_auth, mock_db, bad_lang: str, label: str
):
    """Language codes outside Literal['en','es'] → 422 before DB is touched.

    INTL-SEC-5: the Pydantic Literal enforcement is the primary injection-prevention
    gate. Any value not in the explicit allowlist is rejected at the API boundary.
    """
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Test", "drawSize": 32, "startDate": "2026-06-01",
            "preferredLanguage": bad_lang,
        },
    )
    assert resp.status_code == 422, (
        f"Expected 422 for preferredLanguage={bad_lang!r} ({label}), "
        f"got {resp.status_code}: {resp.text}"
    )
    mock_db.table.return_value.insert.assert_not_called()


def test_preferred_language_omitted_absent_from_insert(client_with_auth, mock_db):
    """Legacy payload without preferredLanguage → 201, field absent from insert payload."""
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [{
        "id": TID, "name": "Legacy", "draw_size": 32, "start_date": "2026-06-01",
    }]
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={"name": "Legacy", "drawSize": 32, "startDate": "2026-06-01"},
    )
    assert resp.status_code == 201, resp.text
    insert_args = mock_db.table.return_value.insert.call_args
    assert insert_args is not None
    insert_payload: dict = insert_args[0][0]
    assert "preferred_language" not in insert_payload, (
        f"preferred_language should be absent from insert payload for legacy request, "
        f"got: {insert_payload}"
    )
