"""Tests for MockPlacesProvider — deterministic Dallas demo fixture.

Verifies that the demo seed coordinates return ≥3 places with the expected
names, and that out-of-bbox coordinates return an empty list.
Phase 5 / Task #8.
"""
import pytest
from playfuel_api.services.places import MockPlacesProvider, RawPlace


DALLAS_LAT = 32.78
DALLAS_LNG = -96.80
SEARCH_RADIUS = 4828
MAX_RESULTS = 6


@pytest.fixture()
def provider() -> MockPlacesProvider:
    return MockPlacesProvider()


# ── Happy-path: Dallas seed coords ────────────────────────────────────────────


def test_mock_provider_returns_at_least_three_places(provider):
    """Dallas bbox returns ≥3 deterministic places."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    assert len(results) >= 3


def test_mock_provider_includes_chipotle(provider):
    """Dallas fixture must include a place with 'Chipotle' in the name."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    names = [r.name for r in results]
    assert any("Chipotle" in n for n in names), f"No Chipotle in {names}"


def test_mock_provider_includes_jimmy_johns(provider):
    """Dallas fixture must include a place with 'Jimmy' in the name."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    names = [r.name for r in results]
    assert any("Jimmy" in n for n in names), f"No Jimmy John's in {names}"


def test_mock_provider_includes_central_market(provider):
    """Dallas fixture must include a place with 'Central' in the name."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    names = [r.name for r in results]
    assert any("Central" in n for n in names), f"No Central Market in {names}"


def test_mock_provider_returns_raw_place_instances(provider):
    """All returned objects are RawPlace dataclass instances."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    for r in results:
        assert isinstance(r, RawPlace)


def test_mock_provider_all_have_provider_mock(provider):
    """All fixture places have provider='mock'."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    for r in results:
        assert r.provider == "mock"


def test_mock_provider_respects_max_results_cap(provider):
    """Results capped at max_results."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, 2)
    assert len(results) <= 2


def test_mock_provider_seed_coords_within_radius(provider):
    """Actual seed venue coords (32.776664, -96.796988) return places."""
    results = provider.search_nearby(32.776664, -96.796988, SEARCH_RADIUS, MAX_RESULTS)
    assert len(results) >= 3


def test_mock_provider_within_plus_half_degree(provider):
    """Coords at the bbox boundary (+0.49°) still return places."""
    results = provider.search_nearby(DALLAS_LAT + 0.49, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    assert len(results) >= 3


# ── Geo-agnostic: any coords return geo-offset fixtures ───────────────────────


def test_mock_provider_outside_dallas_returns_geo_offset_fixtures(provider):
    """Coords outside Dallas bbox still return geo-offset fixtures — no bbox gate.

    Pre-fix, MockPlacesProvider had a Dallas bbox gate; any non-Dallas input
    returned []. This assertion would have FAILED pre-fix (got [], expected >= 3).
    """
    austin_lat, austin_lng = 30.2672, -97.7431
    results = list(provider.search_nearby(austin_lat, austin_lng, SEARCH_RADIUS, MAX_RESULTS))
    assert len(results) >= 3, f"Expected ≥3 mock results for Austin coords; got {len(results)}"
    for r in results:
        assert abs(r.lat - austin_lat) <= 0.05, (
            f"{r.name}.lat={r.lat} not within 0.05° of Austin lat={austin_lat}"
        )
        assert abs(r.lng - austin_lng) <= 0.05, (
            f"{r.name}.lng={r.lng} not within 0.05° of Austin lng={austin_lng}"
        )


def test_mock_provider_null_island_still_returns_fixtures(provider):
    """Null island (0.0, 0.0) returns geo-offset fixtures — no bbox gate."""
    results = list(provider.search_nearby(0.0, 0.0, SEARCH_RADIUS, MAX_RESULTS))
    assert len(results) >= 3, f"Expected ≥3 mock results for null island; got {len(results)}"


def test_mock_provider_new_york_returns_geo_offset_fixtures(provider):
    """New York coords return fixtures offset from NYC, not anchored to Dallas."""
    nyc_lat, nyc_lng = 40.7128, -74.0060
    results = list(provider.search_nearby(nyc_lat, nyc_lng, SEARCH_RADIUS, MAX_RESULTS))
    assert len(results) >= 3, f"Expected ≥3 mock results for NYC coords; got {len(results)}"
    for r in results:
        assert abs(r.lat - nyc_lat) <= 0.05, (
            f"{r.name}.lat={r.lat} not within 0.05° of NYC lat={nyc_lat}"
        )
        assert abs(r.lng - nyc_lng) <= 0.05, (
            f"{r.name}.lng={r.lng} not within 0.05° of NYC lng={nyc_lng}"
        )


# ── RawPlace field completeness ────────────────────────────────────────────────


def test_chipotle_has_expected_fields(provider):
    """Chipotle fixture has expected drive_time, distance, and types."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    chipotle = next(r for r in results if "Chipotle" in r.name)
    assert chipotle.drive_time_minutes is not None
    assert chipotle.distance_meters is not None
    assert len(chipotle.types) > 0
    assert chipotle.place_id is not None


def test_jimmy_johns_drive_time_is_under_8_min(provider):
    """Jimmy John's should be within quick_pickup (≤8 min) budget."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    jimmy = next(r for r in results if "Jimmy" in r.name)
    assert jimmy.drive_time_minutes is not None and jimmy.drive_time_minutes <= 8


def test_central_market_drive_time_is_over_5_min(provider):
    """Central Market should be outside portable (>5 min) budget."""
    results = provider.search_nearby(DALLAS_LAT, DALLAS_LNG, SEARCH_RADIUS, MAX_RESULTS)
    central = next(r for r in results if "Central" in r.name)
    assert central.drive_time_minutes is not None and central.drive_time_minutes > 5
