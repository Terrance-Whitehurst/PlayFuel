"""Provider-selection + PlacesUnavailableError propagation tests.

Covers OQ-FOOD-EMPTY-1: verify that when GOOGLE_PLACES_API_KEY is set but the
provider fails, PlacesUnavailableError propagates out of find_nearby_food()
(never swallowed, never falls through to MockPlacesProvider in production).

Test matrix:
    PS-1  Google selected when GOOGLE_PLACES_API_KEY is set + PLACES_PROVIDER=auto
    PS-2  Mock selected when GOOGLE_PLACES_API_KEY is unset + PLACES_PROVIDER=auto
    PS-3  PlacesUnavailableError propagates on simulated 401 (key set, API rejects)
    PS-4  PlacesUnavailableError propagates on simulated 5xx with no stale cache
    PS-5  Genuine empty 200 response → no error, returns [] (rural venue zero results)
    PS-6  find_nearby_food returns (places, False) for valid Google response
    PS-7  Mock provider selected when PLACES_PROVIDER=mock regardless of key
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from playfuel_api.services.places import (
    GooglePlacesProvider,
    MockPlacesProvider,
    PlacesUnavailableError,
    RawPlace,
    find_nearby_food,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_LAT = 40.7128
_LNG = -74.0060  # New York City — deliberately NOT Dallas to verify geo-agnostic behaviour
_RADIUS_M = 4828
_MAX_RESULTS = 6
_FAKE_TID = UUID("b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
_FAKE_KEY = "AIzaSy_test_key_for_provider_selection_tests"

_OK_RESPONSE = {
    "places": [
        {
            "id": "place_nyc_001",
            "displayName": {"text": "Shake Shack"},
            "formattedAddress": "691 8th Ave, New York, NY 10036",
            "types": ["restaurant", "fast_food_restaurant"],
            "location": {"latitude": 40.7142, "longitude": -74.0038},
            "rating": 4.5,
            "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
            "distanceMeters": 620,
        }
    ]
}

_EMPTY_RESPONSE = {"places": []}  # genuine zero results (rural venue)


def _make_http_resp(status: int, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = f"HTTP {status}"
    resp.json.return_value = body or {}
    return resp


def _settings(provider: str = "auto", key: str = _FAKE_KEY) -> MagicMock:
    s = MagicMock()
    s.places_provider = provider
    s.google_places_api_key = key
    s.places_search_radius_m = _RADIUS_M
    s.places_max_results = _MAX_RESULTS
    return s


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_ps1_auto_selects_google_when_key_set() -> None:
    """PS-1: PLACES_PROVIDER=auto + key present → GooglePlacesProvider is used."""
    with (
        patch("playfuel_api.settings.get_settings", return_value=_settings("auto", _FAKE_KEY)),
        patch("playfuel_api.services.places.httpx.post", return_value=_make_http_resp(200, _OK_RESPONSE)),
    ):
        results = find_nearby_food(_LAT, _LNG)

    assert len(results) == 1
    assert results[0].provider == "google"
    assert results[0].name == "Shake Shack"


def test_ps2_auto_selects_mock_when_no_key() -> None:
    """PS-2: PLACES_PROVIDER=auto + no key → MockPlacesProvider is used, no error."""
    with patch("playfuel_api.settings.get_settings", return_value=_settings("auto", "")):
        results = find_nearby_food(_LAT, _LNG)

    assert len(results) >= 1
    # All results come from the mock provider (provider field = "mock")
    assert all(r.provider == "mock" for r in results)


def test_ps3_places_unavailable_error_propagates_on_401() -> None:
    """PS-3: Key is set, API returns 401 → PlacesUnavailableError propagates out.

    Verifies the production contract: when the key is set and broken,
    find_nearby_food() raises PlacesUnavailableError (does NOT fall through to
    MockPlacesProvider, does NOT silently return []).
    """
    with (
        patch("playfuel_api.settings.get_settings", return_value=_settings("auto", _FAKE_KEY)),
        patch("playfuel_api.services.places.httpx.post", return_value=_make_http_resp(401)),
        pytest.raises(PlacesUnavailableError, match="401"),
    ):
        find_nearby_food(_LAT, _LNG)


def test_ps4_places_unavailable_error_propagates_on_5xx_no_cache() -> None:
    """PS-4: Key is set, API returns 5xx, no stale cache → PlacesUnavailableError propagates.

    The _handle_http_error path: no stale cache → raises PlacesUnavailableError.
    No mock fallback in this scenario.
    """
    # No tournament_id → no cache read, no stale fallback path
    with (
        patch("playfuel_api.settings.get_settings", return_value=_settings("auto", _FAKE_KEY)),
        patch("playfuel_api.services.places.httpx.post", return_value=_make_http_resp(503)),
        pytest.raises(PlacesUnavailableError, match="server error"),
    ):
        find_nearby_food(_LAT, _LNG, tournament_id=None)


def test_ps5_genuine_empty_200_no_error() -> None:
    """PS-5: Key set, 200 OK, places=[] (rural venue zero results) → [] returned, no error.

    Distinct from PS-3/PS-4: provider succeeded but found nothing nearby.
    No PlacesUnavailableError should be raised.
    """
    with (
        patch("playfuel_api.settings.get_settings", return_value=_settings("auto", _FAKE_KEY)),
        patch("playfuel_api.services.places.httpx.post", return_value=_make_http_resp(200, _EMPTY_RESPONSE)),
    ):
        results = find_nearby_food(_LAT, _LNG)

    assert results == []


def test_ps6_mock_provider_selected_when_places_provider_mock() -> None:
    """PS-6: PLACES_PROVIDER=mock always selects MockPlacesProvider regardless of key.

    This verifies that the explicit 'mock' setting works for test/dev environments.
    """
    with patch("playfuel_api.settings.get_settings", return_value=_settings("mock", _FAKE_KEY)):
        results = find_nearby_food(_LAT, _LNG)

    # MockPlacesProvider always returns ≥1 fixture; all tagged provider="mock"
    assert len(results) >= 1
    assert all(r.provider == "mock" for r in results)


def test_ps7_mock_distances_are_venue_relative_not_hardcoded() -> None:
    """PS-7: MockPlacesProvider computes place coords relative to caller's (lat, lng).

    The fixture offsets are applied to the caller's coords — not hardcoded to Dallas.
    For a NYC request, lat/lng of returned places should be near NYC, not Dallas.
    """
    mock_provider = MockPlacesProvider()
    results = list(mock_provider.search_nearby(_LAT, _LNG, _RADIUS_M, _MAX_RESULTS))

    assert len(results) >= 1
    for r in results:
        # Each result's lat should be within ~0.1° of the request lat (NYC ~40.7)
        assert r.lat is not None
        assert abs(r.lat - _LAT) < 0.1, (
            f"Expected place lat near {_LAT} (NYC), got {r.lat} — "
            "MockPlacesProvider may still be returning Dallas-hardcoded coords"
        )
        # Each result's lng should be within ~0.1° of the request lng (NYC ~-74.0)
        assert r.lng is not None
        assert abs(r.lng - _LNG) < 0.1, (
            f"Expected place lng near {_LNG} (NYC), got {r.lng} — "
            "MockPlacesProvider may still be returning Dallas-hardcoded coords"
        )
