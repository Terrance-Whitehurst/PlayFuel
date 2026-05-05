"""Phase A.1 hardening — round-trip persistence + validation rejection tests.

Complements test_tournament_intl_fields.py (Phase A smoke tests) with:

  1. Round-trip persistence: POST sets time_zone + venue_country in the insert
     payload, then GET returns them from the (mocked) DB.  Confirms that the
     fields are not silently dropped between the Pydantic model and the Supabase
     insert call — the exact regression Phase A was designed to prevent.

  2. Legacy backward compat: omitting both fields → 201 and both absent from the
     insert payload (exclude_none=True semantics).

  3. venue_country validation (INTL-SEC-1): lowercase, 3-char, and XSS payloads
     all rejected with 422 before the DB is touched.

  4. time_zone validation (INTL-SEC-2): unknown IANA identifiers rejected with
     422 before the DB is touched.

Test harness: mock_db + client_with_auth from conftest.py.  No real Supabase
network calls.  Pattern mirrors test_draw_size_and_round.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

_TOURNAMENT_PATH = "/v1/tournaments"

# Fixed UUIDs for deterministic assertions.
TID = "a1eebc99-9c0b-4ef8-bb6d-6bb9bd380b11"
_CDMX_TZ = "America/Mexico_City"
_CDMX_COUNTRY = "MX"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wire_post(mock_db: MagicMock, return_row: dict) -> None:
    """Configure the mock for POST /tournaments (insert)."""
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [return_row]


def _wire_get(mock_db: MagicMock, return_row: dict) -> None:
    """Configure the mock for GET /tournaments/{tid} (select → eq → execute)."""
    (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .execute.return_value
    ).data = [return_row]


def _post_cdmx(client_with_auth) -> "Response":  # noqa: F821
    """POST a minimal Mexico City tournament payload."""
    return client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Club Reforma Open",
            "drawSize": 32,
            "startDate": "2026-07-04",
            "timeZone": _CDMX_TZ,
            "venueCountry": _CDMX_COUNTRY,
        },
    )


# ── 1. Round-trip persistence ─────────────────────────────────────────────────

def test_round_trip_both_intl_fields_persist(client_with_auth, mock_db):
    """POST timeZone + venueCountry → insert payload has both → GET returns both.

    This is the core regression test for Phase A: confirms that time_zone and
    venue_country are NOT silently dropped (the historical bug at DTOs.swift:403).
    """
    row = {
        "id": TID,
        "name": "Club Reforma Open",
        "draw_size": 32,
        "start_date": "2026-07-04",
        "time_zone": _CDMX_TZ,
        "venue_country": _CDMX_COUNTRY,
    }
    _wire_post(mock_db, row)
    _wire_get(mock_db, row)

    # POST — confirm 201 and response fields.
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Club Reforma Open",
            "drawSize": 32,
            "startDate": "2026-07-04",
            "timeZone": _CDMX_TZ,
            "venueCountry": _CDMX_COUNTRY,
        },
    )
    assert resp.status_code == 201, resp.text
    post_body = resp.json()
    assert post_body["time_zone"] == _CDMX_TZ, (
        f"POST response missing time_zone: {post_body}"
    )
    assert post_body["venue_country"] == _CDMX_COUNTRY, (
        f"POST response missing venue_country: {post_body}"
    )

    # Assert the insert payload passed to Supabase contains the correct values
    # (not None, not missing) — the persistence regression check.
    insert_args = mock_db.table.return_value.insert.call_args
    assert insert_args is not None, "Expected insert() to be called"
    insert_payload: dict = insert_args[0][0]
    assert insert_payload.get("time_zone") == _CDMX_TZ, (
        f"time_zone missing or wrong in DB insert payload: {insert_payload}"
    )
    assert insert_payload.get("venue_country") == _CDMX_COUNTRY, (
        f"venue_country missing or wrong in DB insert payload: {insert_payload}"
    )

    # GET — confirm the fetched row round-trips both fields.
    get_resp = client_with_auth.get(f"/v1/tournaments/{TID}")
    assert get_resp.status_code == 200, get_resp.text
    get_body = get_resp.json()
    assert get_body["time_zone"] == _CDMX_TZ, (
        f"GET response missing time_zone: {get_body}"
    )
    assert get_body["venue_country"] == _CDMX_COUNTRY, (
        f"GET response missing venue_country: {get_body}"
    )


# ── 2. Legacy backward compatibility ─────────────────────────────────────────

def test_legacy_payload_intl_fields_absent_from_insert(client_with_auth, mock_db):
    """POST without timeZone/venueCountry → 201, both absent from the insert payload.

    Verifies backward compatibility: legacy iOS clients that omit the new fields
    still succeed, and exclude_none=True correctly drops them from the Supabase
    insert (no NULL writes for pre-migration rows).
    """
    legacy_row = {
        "id": TID,
        "name": "Dallas Junior Open",
        "draw_size": 64,
        "start_date": "2026-06-01",
    }
    _wire_post(mock_db, legacy_row)

    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Dallas Junior Open",
            "drawSize": 64,
            "startDate": "2026-06-01",
        },
    )
    assert resp.status_code == 201, resp.text

    insert_args = mock_db.table.return_value.insert.call_args
    assert insert_args is not None, "Expected insert() to be called"
    insert_payload: dict = insert_args[0][0]

    assert "time_zone" not in insert_payload, (
        f"time_zone should be absent from insert payload (legacy request), got: {insert_payload}"
    )
    assert "venue_country" not in insert_payload, (
        f"venue_country should be absent from insert payload (legacy request), got: {insert_payload}"
    )


# ── 3. venue_country validation (INTL-SEC-1) ─────────────────────────────────

@pytest.mark.parametrize("bad_country,label", [
    ("mx", "lowercase"),
    ("usa", "3-char ISO alpha-3"),
    ("<script>alert(1)</script>", "XSS payload"),
    ("1X", "starts with digit"),
    ("", "empty string"),
])
def test_venue_country_invalid_values_rejected_with_422(
    client_with_auth, mock_db, bad_country: str, label: str
):
    """venue_country invalid values → 422 from Pydantic before DB is touched.

    INTL-SEC-1: venue_country must be exactly 2 uppercase ASCII letters.
    Lowercase, 3-char, XSS payloads, and digit-prefixed values are all rejected.
    The DB insert mock is NOT wired — if the route reaches insert(), the test fails.
    """
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Test Tournament",
            "drawSize": 32,
            "startDate": "2026-06-01",
            "venueCountry": bad_country,
        },
    )
    assert resp.status_code == 422, (
        f"Expected 422 for venueCountry={bad_country!r} ({label}), got {resp.status_code}: {resp.text}"
    )
    # DB must NOT have been touched.
    mock_db.table.return_value.insert.assert_not_called()


def test_venue_country_valid_values_accepted(client_with_auth, mock_db):
    """Valid ISO 3166-1 alpha-2 codes (US, MX, CA, GB, AU) → 201."""
    for code in ("US", "MX", "CA", "GB", "AU"):
        _wire_post(mock_db, {"id": TID, "name": "T", "draw_size": 32, "start_date": "2026-06-01", "venue_country": code})
        mock_db.reset_mock()
        _wire_post(mock_db, {"id": TID, "name": "T", "draw_size": 32, "start_date": "2026-06-01", "venue_country": code})
        resp = client_with_auth.post(
            _TOURNAMENT_PATH,
            json={"name": "T", "drawSize": 32, "startDate": "2026-06-01", "venueCountry": code},
        )
        assert resp.status_code == 201, (
            f"Expected 201 for venueCountry={code!r}, got {resp.status_code}: {resp.text}"
        )


# ── 4. time_zone validation (INTL-SEC-2) ─────────────────────────────────────

@pytest.mark.parametrize("bad_tz,label", [
    ("America/Mexico", "no city — common typo for America/Mexico_City"),
    ("Not/A_Zone", "completely fake IANA ID"),
    ("Mars/Olympus_Mons", "nonsense zone"),
    ("Fake/City", "plausible-looking but nonexistent zone"),
])
def test_time_zone_invalid_iana_rejected_with_422(
    client_with_auth, mock_db, bad_tz: str, label: str
):
    """Unknown IANA time zone identifiers → 422 before DB is touched.

    INTL-SEC-2: time_zone must be a recognized IANA identifier per stdlib zoneinfo.
    'America/Mexico' (no city) is the canonical typo — catches the exact mistake
    a developer or iOS bug would produce for Mexico City.
    Note: deprecated aliases (US/Pacific, etc.) may still exist in some tzdata
    installs; this test uses only identifiers known to be universally invalid.
    """
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={
            "name": "Test Tournament",
            "drawSize": 32,
            "startDate": "2026-06-01",
            "timeZone": bad_tz,
        },
    )
    assert resp.status_code == 422, (
        f"Expected 422 for timeZone={bad_tz!r} ({label}), got {resp.status_code}: {resp.text}"
    )
    mock_db.table.return_value.insert.assert_not_called()


@pytest.mark.parametrize("good_tz", [
    "America/Mexico_City",
    "America/Chicago",
    "America/New_York",
    "Europe/London",
    "Asia/Tokyo",
    "America/Sao_Paulo",
    "UTC",
    "America/Los_Angeles",
])
def test_time_zone_valid_iana_identifiers_accepted(
    client_with_auth, mock_db, good_tz: str
):
    """Valid IANA identifiers (all iOS picker zones + UTC) → 201."""
    _wire_post(mock_db, {
        "id": TID, "name": "T", "draw_size": 32,
        "start_date": "2026-06-01", "time_zone": good_tz,
    })
    resp = client_with_auth.post(
        _TOURNAMENT_PATH,
        json={"name": "T", "drawSize": 32, "startDate": "2026-06-01", "timeZone": good_tz},
    )
    assert resp.status_code == 201, (
        f"Expected 201 for timeZone={good_tz!r}, got {resp.status_code}: {resp.text}"
    )
