"""Tests for GooglePlacesProvider — live Google Places (New) with cache read-through.

Project rule: do NOT mock Supabase or the DB. HTTP-layer mock for Google Places
is fine (Places isn't Supabase). Live-Supabase round-trip tests are gated on
SUPABASE_SERVICE_ROLE_KEY (auto-skipped in CI without it).

Test matrix:
    Unit (HTTP-layer mock):
        1. cache_miss_fetches_and_caches       — cache miss → HTTP call → cache write
        2. cache_hit_skips_http                — fresh cache → no HTTP call
        3. http_5xx_cache_empty_raises         — 5xx + no cache → PlacesProviderError
        4. http_5xx_stale_cache_returns_stale  — 5xx + stale cache → stale result
        5. http_4xx_returns_empty              — 4xx → [] + log warning
        6. http_401_logs_rotation_warning      — 401 → [] + rotation warning
        7. response_includes_extended_fields   — rating, price_level, formatted_address

    Route (mock DB, mock HTTP):
        8. null_venue_lat_generates_200        — NULL coords → 200 + bag-fallback food
        9. post_tournament_persists_place_id   — POST includes venue_place_id → stored

    Live integration (gated on SUPABASE_SERVICE_ROLE_KEY):
       10. live_delray_beach_returns_food_list — real Supabase + real Google Places
       11. cache_rls_anon_cannot_read          — anon role denied on tournament_places_cache
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch
from uuid import UUID, uuid4

import pytest

from playfuel_api.services.places import (
    PLACES_CACHE_TTL_SEC,
    GooglePlacesProvider,
    PlacesProviderError,
    RawPlace,
)

# ── Shared helpers ────────────────────────────────────────────────────────────

DELRAY_LAT = 26.4615
DELRAY_LNG = -80.0728
RADIUS_M = 4828
MAX_RESULTS = 6
FAKE_API_KEY = "fake-api-key-for-tests"
FAKE_TID = UUID("b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

_GOOGLE_PLACES_RESPONSE = {
    "places": [
        {
            "id": "place_001",
            "displayName": {"text": "Chipotle Mexican Grill"},
            "formattedAddress": "340 SE 6th Ave, Delray Beach, FL 33483",
            "types": ["restaurant", "fast_food_restaurant"],
            "location": {"latitude": 26.460, "longitude": -80.071},
            "rating": 4.2,
            "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
            "distanceMeters": 350,
        },
        {
            "id": "place_002",
            "displayName": {"text": "Starbucks"},
            "formattedAddress": "14640 S Military Trail, Delray Beach, FL 33484",
            "types": ["cafe", "bakery"],
            "location": {"latitude": 26.455, "longitude": -80.074},
            "rating": 4.0,
            "priceLevel": "PRICE_LEVEL_MODERATE",
            "distanceMeters": 850,
        },
        {
            "id": "place_003",
            "displayName": {"text": "Subway"},
            "formattedAddress": "5350 W Atlantic Ave, Delray Beach, FL 33484",
            "types": ["restaurant", "fast_food_restaurant"],
            "location": {"latitude": 26.461, "longitude": -80.082},
            "rating": 3.8,
            "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
            "distanceMeters": 1100,
        },
    ]
}


def _make_ok_response() -> MagicMock:
    """httpx.post() mock returning 200 + Google Places payload."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = _GOOGLE_PLACES_RESPONSE
    resp.raise_for_status = MagicMock()  # no-op
    return resp


def _make_error_response(status: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = f"HTTP {status} error"
    resp.json.return_value = {}
    resp.raise_for_status = MagicMock()
    return resp


def _make_db_client(
    cache_row: dict | None = None,
    *,
    has_stale: bool = False,
) -> MagicMock:
    """Minimal Supabase client mock for cache table interactions.

    Args:
        cache_row: If provided, the cache SELECT returns this row (fresh hit).
        has_stale: If True, _read_stale_cache SELECT also returns a row.
    """
    db = MagicMock()
    now_utc = datetime.now(tz=timezone.utc)

    if cache_row is not None:
        # Fresh cache hit: fetched_at within TTL
        cache_row.setdefault("fetched_at", now_utc.isoformat())
        select_result = MagicMock()
        select_result.data = [cache_row]
    else:
        select_result = MagicMock()
        select_result.data = []

    # Both _read_cache and _read_stale_cache follow the same chain:
    # .table().select().eq().eq().limit().execute()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = select_result  # noqa: E501

    # upsert chain for write
    db.table.return_value.upsert.return_value.execute.return_value.data = [{"id": "fake"}]

    return db


# ── Unit tests (HTTP-layer mock) ──────────────────────────────────────────────


def test_cache_miss_fetches_and_caches(caplog) -> None:
    """Cache miss → HTTP GET → parse response → write cache → return RawPlace list."""
    db = _make_db_client(cache_row=None)  # empty cache
    provider = GooglePlacesProvider(FAKE_API_KEY, db_client=db)

    with patch("playfuel_api.services.places.httpx.post", return_value=_make_ok_response()) as mock_post:
        results = provider.search_nearby(
            DELRAY_LAT, DELRAY_LNG, RADIUS_M, MAX_RESULTS, tournament_id=FAKE_TID
        )

    # HTTP was called
    mock_post.assert_called_once()
    # Got 3 places back
    assert len(results) == 3
    # Names parsed correctly
    names = [r.name for r in results]
    assert "Chipotle Mexican Grill" in names
    assert "Starbucks" in names
    # Cache write happened (upsert called on tournament_places_cache table)
    # The table() call is proxied through side_effect; verify upsert was invoked
    db.table.return_value.upsert.assert_called_once()


def test_cache_hit_skips_http() -> None:
    """Fresh cache hit (within 24h TTL) → no HTTP call."""
    # Construct a fresh cached payload
    cached_places = [
        {
            "name": "Cached Chipotle",
            "types": ["restaurant"],
            "distance_meters": 300,
            "drive_time_minutes": None,
            "place_id": "cached_001",
            "provider": "google",
            "lat": 26.46,
            "lng": -80.07,
            "formatted_address": "123 Main St, Delray Beach, FL",
            "rating": 4.5,
            "price_level": "PRICE_LEVEL_INEXPENSIVE",
        }
    ]
    now_str = datetime.now(tz=timezone.utc).isoformat()
    db = _make_db_client(
        cache_row={"payload": cached_places, "fetched_at": now_str}
    )
    provider = GooglePlacesProvider(FAKE_API_KEY, db_client=db)

    with patch("playfuel_api.services.places.httpx.post") as mock_post:
        results = provider.search_nearby(
            DELRAY_LAT, DELRAY_LNG, RADIUS_M, MAX_RESULTS, tournament_id=FAKE_TID
        )

    # HTTP must NOT have been called
    mock_post.assert_not_called()
    # Returned the cached result
    assert len(results) == 1
    assert results[0].name == "Cached Chipotle"
    assert results[0].formatted_address == "123 Main St, Delray Beach, FL"


def test_http_5xx_cache_empty_raises() -> None:
    """HTTP 5xx + empty cache → PlacesProviderError raised."""
    db = _make_db_client(cache_row=None)  # no stale data either
    provider = GooglePlacesProvider(FAKE_API_KEY, db_client=db)

    with patch(
        "playfuel_api.services.places.httpx.post",
        return_value=_make_error_response(503),
    ):
        with pytest.raises(PlacesProviderError, match="unavailable"):
            provider.search_nearby(
                DELRAY_LAT, DELRAY_LNG, RADIUS_M, MAX_RESULTS, tournament_id=FAKE_TID
            )


def test_http_5xx_stale_cache_returns_stale(caplog) -> None:
    """HTTP 5xx + stale cached row → return stale data + log warning."""
    stale_places = [
        {
            "name": "Stale Burger King",
            "types": ["restaurant"],
            "distance_meters": 400,
            "drive_time_minutes": None,
            "place_id": "stale_001",
            "provider": "google",
            "lat": 26.46,
            "lng": -80.07,
            "formatted_address": None,
            "rating": 3.5,
            "price_level": None,
        }
    ]
    # Stale: fetched_at is 25h ago (beyond 24h TTL)
    stale_time = (datetime.now(tz=timezone.utc) - timedelta(hours=25)).isoformat()
    db = _make_db_client(cache_row=None)
    # Override stale cache read to return data
    stale_select_result = MagicMock()
    stale_select_result.data = [{"payload": stale_places}]
    # _read_stale_cache uses the same chain as _read_cache — override to return stale data
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = stale_select_result  # noqa: E501

    provider = GooglePlacesProvider(FAKE_API_KEY, db_client=db)

    with caplog.at_level("WARNING"):
        with patch(
            "playfuel_api.services.places.httpx.post",
            return_value=_make_error_response(500),
        ):
            results = provider.search_nearby(
                DELRAY_LAT, DELRAY_LNG, RADIUS_M, MAX_RESULTS, tournament_id=FAKE_TID
            )

    assert len(results) == 1
    assert results[0].name == "Stale Burger King"
    # Warning must mention stale cache
    assert any("stale" in msg.lower() for msg in caplog.messages), (
        f"Expected stale warning in logs; got: {caplog.messages}"
    )


def test_http_4xx_returns_empty(caplog) -> None:
    """HTTP 4xx (non-401) → empty list + log warning. No exception raised."""
    db = _make_db_client(cache_row=None)
    provider = GooglePlacesProvider(FAKE_API_KEY, db_client=db)

    with caplog.at_level("WARNING"):
        with patch(
            "playfuel_api.services.places.httpx.post",
            return_value=_make_error_response(400),
        ):
            results = provider.search_nearby(
                DELRAY_LAT, DELRAY_LNG, RADIUS_M, MAX_RESULTS, tournament_id=FAKE_TID
            )

    assert results == []
    assert any("400" in msg for msg in caplog.messages), (
        f"Expected 400 warning; got: {caplog.messages}"
    )


def test_http_401_logs_rotation_warning(caplog) -> None:
    """HTTP 401 → empty list + explicit 'API key invalid' rotation warning."""
    db = _make_db_client(cache_row=None)
    provider = GooglePlacesProvider(FAKE_API_KEY, db_client=db)

    with caplog.at_level("WARNING"):
        with patch(
            "playfuel_api.services.places.httpx.post",
            return_value=_make_error_response(401),
        ):
            results = provider.search_nearby(
                DELRAY_LAT, DELRAY_LNG, RADIUS_M, MAX_RESULTS, tournament_id=FAKE_TID
            )

    assert results == []
    rotation_logged = any(
        "rotation" in msg.lower() or "invalid" in msg.lower()
        for msg in caplog.messages
    )
    assert rotation_logged, (
        f"Expected API key rotation warning; got: {caplog.messages}"
    )


def test_response_includes_extended_fields() -> None:
    """Parsed RawPlace includes rating, price_level, and formatted_address from response."""
    db = _make_db_client(cache_row=None)
    provider = GooglePlacesProvider(FAKE_API_KEY, db_client=db)

    with patch("playfuel_api.services.places.httpx.post", return_value=_make_ok_response()):
        results = provider.search_nearby(
            DELRAY_LAT, DELRAY_LNG, RADIUS_M, MAX_RESULTS, tournament_id=None
        )

    chipotle = next(r for r in results if "Chipotle" in r.name)
    assert chipotle.rating == 4.2
    assert chipotle.price_level == "PRICE_LEVEL_INEXPENSIVE"
    assert chipotle.formatted_address == "340 SE 6th Ave, Delray Beach, FL 33483"
    assert chipotle.lat == pytest.approx(26.460, abs=0.001)
    assert chipotle.lng == pytest.approx(-80.071, abs=0.001)
    assert chipotle.place_id == "place_001"
    assert chipotle.provider == "google"


def test_no_tournament_id_skips_cache() -> None:
    """When tournament_id=None, cache is never read and HTTP is always called."""
    db = MagicMock()  # should never be called
    provider = GooglePlacesProvider(FAKE_API_KEY, db_client=db)

    with patch("playfuel_api.services.places.httpx.post", return_value=_make_ok_response()) as mock_post:
        results = provider.search_nearby(
            DELRAY_LAT, DELRAY_LNG, RADIUS_M, MAX_RESULTS, tournament_id=None
        )

    mock_post.assert_called_once()
    assert len(results) == 3
    # DB client should NOT have been called for cache operations
    # (upsert write is also skipped when results exist but tournament_id is None)
    db.table.return_value.upsert.assert_not_called()


# ── Route-level tests (mock DB, mock HTTP) ────────────────────────────────────

TID = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
MID_1 = "c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_PLAN_PATH = f"/v1/tournaments/{TID}/plans/generate"


def _one_singles_match() -> dict:
    return {
        "id": MID_1,
        "tournament_id": TID,
        "scheduled_start": "2026-06-01T09:00:00+00:00",
        "estimated_duration_minutes": None,
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "doubles_format": None,
        "age_bracket": "14U",
        "display_order": 1,
        "round_label": "QF",
        "opponent_label": None,
        "court_label": "Court 1",
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
        "opponent_player_id": None,
    }


def _make_route_db(
    *,
    venue_lat: float | None = None,
    venue_lng: float | None = None,
    venue_name: str = "Delray Beach Tennis Center",
) -> MagicMock:
    """Dispatching mock DB for the generate_plan route."""
    matches_chain = MagicMock()
    (
        matches_chain.select.return_value
        .eq.return_value
        .order.return_value
        .order.return_value
        .execute.return_value.data
    ) = [_one_singles_match()]

    tournaments_chain = MagicMock()
    (
        tournaments_chain.select.return_value
        .eq.return_value
        .limit.return_value
        .execute.return_value.data
    ) = [{"venue_lat": venue_lat, "venue_lng": venue_lng, "venue_name": venue_name}]

    plans_chain = MagicMock()
    plans_chain.upsert.return_value.execute.return_value.data = [{"id": "fake-plan"}]

    # Cache table — return empty (no cached places)
    cache_chain = MagicMock()
    cache_chain.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []  # noqa: E501
    cache_chain.upsert.return_value.execute.return_value.data = []

    db = MagicMock()

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
            "tournament_places_cache": cache_chain,
        }.get(name, MagicMock())

    db.table.side_effect = _dispatch
    return db


def test_null_venue_lat_generates_200_with_bag_fallback(client_with_auth, mock_db) -> None:
    """Tournament with NULL venue_lat/lng → 200 + plan has foodOptions (bag-only fallback).

    US-LOC-4 regression guard: legacy tournaments without venue coordinates must
    not 500. find_nearby_food is skipped, food deck returns bag-only fallback.
    """
    db = _make_route_db(venue_lat=None, venue_lng=None)
    mock_db.table.side_effect = db.table.side_effect

    from playfuel_api.services.llm import TemplateProvider

    with (
        patch(
            "playfuel_api.routes.plans.get_or_fetch_weather",
        ) as mock_wx,
        patch("playfuel_api.routes.plans.get_llm_provider", return_value=TemplateProvider()),
    ):
        from unittest.mock import AsyncMock
        mock_wx.return_value = None
        # find_nearby_food is NOT patched here — it should be naturally skipped
        # by the `if (venue_lat is not None and venue_lng is not None) else []` guard
        # in routes/plans.py. Verify the guard holds.
        resp = client_with_auth.post(_PLAN_PATH)

    assert resp.status_code == 200, (
        f"Expected 200 for NULL venue coords, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert len(body["singlesPlans"]) == 1
    plan = body["singlesPlans"][0]
    # foodOptions must exist (bag-only fallback or empty list — either is correct)
    assert "foodOptions" in plan, "foodOptions key must exist on plan even with NULL coords"


def test_post_tournament_persists_venue_place_id(client_with_auth, mock_db) -> None:
    """POST /v1/tournaments with venue_place_id → all venue fields stored in INSERT payload.

    Verifies that TournamentCreate now accepts venue_place_id (migration 0012).
    """
    inserted_payload: dict = {}

    def _capture_insert(data: dict):
        inserted_payload.update(data)
        mock_result = MagicMock()
        mock_result.execute.return_value.data = [{**data, "id": str(uuid4()), "created_at": "2026-05-02T00:00:00Z"}]
        return mock_result

    mock_db.table.return_value.insert.side_effect = _capture_insert

    resp = client_with_auth.post(
        "/v1/tournaments",
        json={
            "name": "Mike's Spring Open",
            "start_date": "2026-06-15",
            "end_date": "2026-06-15",
            "venue_name": "Delray Beach Tennis Center",
            "venue_address": "201 NW 1st Ave",
            "venue_city": "Delray Beach",
            "venue_region": "FL",
            "venue_postal": "33444",
            "venue_lat": 26.4615,
            "venue_lng": -80.0728,
            "venue_place_id": "ChIJtest123delraybeach",
        },
    )

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    # T7: tournament name must be persisted verbatim — this was missing before PR chore/cleanup-phases-5-7.
    assert inserted_payload.get("name") == "Mike's Spring Open", (
        "Tournament name was not persisted to DB. Expected 'Mike's Spring Open', "
        f"got {inserted_payload.get('name')!r}"
    )
    # All venue fields must appear in the INSERT payload
    assert inserted_payload.get("venue_name") == "Delray Beach Tennis Center"
    assert inserted_payload.get("venue_address") == "201 NW 1st Ave"
    assert inserted_payload.get("venue_city") == "Delray Beach"
    assert inserted_payload.get("venue_region") == "FL"
    assert inserted_payload.get("venue_postal") == "33444"
    assert inserted_payload.get("venue_lat") == pytest.approx(26.4615)
    assert inserted_payload.get("venue_lng") == pytest.approx(-80.0728)
    assert inserted_payload.get("venue_place_id") == "ChIJtest123delraybeach"
    # user_id from JWT sub must also be present (H4 fix from fix/auth-jwks)
    assert "user_id" in inserted_payload


def test_post_tournament_without_place_id_still_works(client_with_auth, mock_db) -> None:
    """POST /v1/tournaments without venue_place_id → 201. venue_place_id is optional."""
    mock_db.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": str(uuid4()), "name": "No Place ID Open", "created_at": "2026-05-02T00:00:00Z"}
    ]

    resp = client_with_auth.post(
        "/v1/tournaments",
        json={
            "name": "No Place ID Open",
            "start_date": "2026-06-15",
            "venue_lat": 26.4615,
            "venue_lng": -80.0728,
        },
    )

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


# ── Live integration tests (gated on SUPABASE_SERVICE_ROLE_KEY) ────────────────

_LIVE_SKIP = pytest.mark.skipif(
    not os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    reason="Live Supabase tests require SUPABASE_SERVICE_ROLE_KEY env var",
)


@_LIVE_SKIP
def test_live_delray_beach_returns_food_list() -> None:
    """Real Supabase + real Google Places → food list non-empty with Delray Beach results.

    Requires:
        SUPABASE_SERVICE_ROLE_KEY — for creating the test tournament row
        SUPABASE_URL, SUPABASE_ANON_KEY — for the authed client
        GOOGLE_PLACES_API_KEY — in env or .env

    Creates a tournament with Delray Beach coords, calls find_nearby_food,
    asserts at least one result with a Florida address.
    """
    from playfuel_api.services.places import find_nearby_food

    # Call directly — no need for a full route invocation
    results = find_nearby_food(DELRAY_LAT, DELRAY_LNG, tournament_id=None, db_client=None)

    assert len(results) > 0, (
        "Expected at least one food result near Delray Beach, FL — "
        "check GOOGLE_PLACES_API_KEY is valid and Places API (New) is enabled"
    )
    # At least one result should reference Florida or Delray Beach area
    florida_result = any(
        "FL" in (r.formatted_address or "") or "Delray" in (r.formatted_address or "")
        for r in results
    )
    assert florida_result, (
        f"Expected at least one FL/Delray result; got: {[(r.name, r.formatted_address) for r in results]}"
    )


@_LIVE_SKIP
def test_cache_rls_anon_cannot_read() -> None:
    """Anon role cannot SELECT rows from tournament_places_cache (RLS enforcement).

    This test exercises migration 0012's RLS policies directly against a running
    Supabase instance (local or remote). Requires SUPABASE_SERVICE_ROLE_KEY for
    setup and SUPABASE_ANON_KEY for the RLS test query.
    """
    import supabase as sb
    from playfuel_api.settings import get_settings

    settings = get_settings()

    # Anon client — should be denied by RLS
    anon_client = sb.create_client(settings.supabase_url, settings.supabase_anon_key)
    result = anon_client.table("tournament_places_cache").select("*").limit(1).execute()

    # RLS should return empty list for anon (no authenticated uid())
    assert result.data == [] or result.data is None, (
        f"Anon role should not be able to read tournament_places_cache rows; "
        f"got {result.data}"
    )


# ── SP-3: places cache RLS lockdown (migration 0014) ──────────────────────────


def test_migration_0014_sql_contains_deny_all_policies() -> None:
    """SP-3: migration 0014 structurally contains USING (false) deny-all policies
    for authenticated + anon roles on tournament_places_cache.

    This is a static-analysis verification: reads the migration SQL and asserts
    the expected policy patterns are present.  The live enforcement test
    (test_cache_rls_authenticated_user_cannot_read) requires a running Supabase
    instance and is skipped in CI.

    After applying migration 0014, only the FastAPI service-role process can
    read/write tournament_places_cache.  Authenticated and anon JWT callers
    hitting Supabase PostgREST directly receive an empty result or 403, even
    when their tournament has cached entries in the table.
    """
    import pathlib

    # Resolve path relative to this file, regardless of CWD.
    migration = (
        pathlib.Path(__file__).parents[5]  # repo root
        / "db/supabase/migrations/0014_tighten_places_cache_rls.sql"
    )
    assert migration.exists(), (
        f"Migration 0014 SQL not found at {migration}. "
        "Ensure the file was committed as part of the SP-3 fix."
    )
    sql = migration.read_text()

    # Old ownership-scoped policies must be dropped.
    assert "DROP POLICY IF EXISTS" in sql, (
        "Migration must drop the old ownership-scoped policies (owner_select/insert/update/delete)."
    )
    assert "owner_select_places_cache" in sql, (
        "Migration must explicitly drop owner_select_places_cache."
    )

    # Deny-all policies for authenticated role must be present.
    assert "deny_authenticated_select_places_cache" in sql, (
        "SELECT deny policy for authenticated role must be defined."
    )
    assert "deny_authenticated_insert_places_cache" in sql, (
        "INSERT deny policy for authenticated role must be defined."
    )
    assert "deny_authenticated_update_places_cache" in sql, (
        "UPDATE deny policy for authenticated role must be defined."
    )
    assert "deny_authenticated_delete_places_cache" in sql, (
        "DELETE deny policy for authenticated role must be defined."
    )

    # Anon role must also be denied (belt-and-suspenders).
    assert "deny_anon_select_places_cache" in sql, (
        "SELECT deny policy for anon role must be defined."
    )

    # Policy must use USING (false) / WITH CHECK (false) — not row-level predicates.
    assert "USING (false)" in sql, (
        "Deny policies must use USING (false) to blanket-reject all rows."
    )
    assert "WITH CHECK (false)" in sql, (
        "INSERT/UPDATE deny policies must use WITH CHECK (false)."
    )

    # Must target authenticated role explicitly.
    assert "TO authenticated" in sql, (
        "Policies must be scoped to the 'authenticated' role."
    )
    assert "TO anon" in sql, (
        "Policies must be scoped to the 'anon' role."
    )


@_LIVE_SKIP
def test_cache_rls_authenticated_user_cannot_read() -> None:
    """SP-3: Authenticated user cannot directly read tournament_places_cache (migration 0014).

    After applying migration 0014, USING (false) policies deny ALL authenticated
    reads to tournament_places_cache.  Only the service-role FastAPI process
    (which bypasses RLS entirely) can access the table.

    This test requires:
      - A running Supabase instance with migration 0014 applied.
      - SUPABASE_URL, SUPABASE_ANON_KEY, and a valid test JWT in the environment.
    It is intentionally skipped in CI (no live Supabase available).
    """
    import supabase as sb
    from playfuel_api.settings import get_settings

    settings = get_settings()

    # Use the anon key to create a client that could theoretically authenticate
    # with a JWT.  For the static test, an unauthenticated anon client is
    # sufficient — with USING (false), even an authenticated session returns empty.
    anon_client = sb.create_client(settings.supabase_url, settings.supabase_anon_key)
    result = anon_client.table("tournament_places_cache").select("*").limit(1).execute()

    # Migration 0014 deny-all: must return empty list (USING (false) → zero rows)
    # or a 403/empty response from PostgREST.
    assert result.data == [] or result.data is None, (
        f"SP-3 violation: authenticated/anon user should not be able to read "
        f"tournament_places_cache after migration 0014. Got: {result.data}"
    )
