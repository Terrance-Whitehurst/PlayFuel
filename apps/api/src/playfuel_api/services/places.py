"""Places provider abstraction. Mirrors weather/service.py structure.

Phase 5 / Task #8 — food options via venue-adjacent restaurant lookup.

Provider selection (settings.PLACES_PROVIDER):
    "auto"   → GooglePlacesProvider if GOOGLE_PLACES_API_KEY set, else MockPlacesProvider
    "google" → GooglePlacesProvider (key required; raises PlacesProviderError if absent)
    "mock"   → MockPlacesProvider always (deterministic fixture — used in tests + demo)

The Dallas demo works end-to-end with MockPlacesProvider — no API key required.
GooglePlacesProvider is a stub only; raises NotImplementedError (deferred until
a real key is provisioned). This ensures the demo path is always green.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, Sequence

_logger = logging.getLogger(__name__)

# ── Dallas demo bounding box ──────────────────────────────────────────────────
# MockPlacesProvider returns fixtures only within ±0.5° of (32.78, -96.80).
# This matches the seed venue coords (32.776664, -96.796988).
_DALLAS_LAT = 32.78
_DALLAS_LNG = -96.80
_DALLAS_RADIUS_DEG = 0.5


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RawPlace:
    """Normalised single place record returned by any PlacesProvider.

    ``types`` mirrors the Google Places API ``types[]`` field.
    ``provider`` identifies the data source ("google" | "mock").

    ``lat`` and ``lng`` are geographic coordinates of the place.
    None when the provider does not return geometry (e.g. legacy stub paths).
    MockPlacesProvider supplies best-guess Uptown Dallas offsets (OQ-FOOD-DECK-3).
    GooglePlacesProvider should surface geometry.location.lat / .lng.
    Added: FOOD_DECK_AND_MAP_V1.md §G.2.
    """
    name: str
    types: list[str]
    distance_meters: int | None
    drive_time_minutes: int | None
    place_id: str | None
    provider: str
    # Coordinates — optional; must come after all required fields in frozen dataclass
    lat: float | None = None
    lng: float | None = None


class PlacesProviderError(Exception):
    """Raised by a PlacesProvider on unrecoverable errors.

    ``find_nearby_food()`` catches this and returns [] — food is non-critical.
    """


# ── Protocol (structural interface) ───────────────────────────────────────────


class PlacesProvider(Protocol):
    """Structural interface for Places backends.

    Only ``search_nearby`` is required. Both GooglePlacesProvider and
    MockPlacesProvider satisfy this protocol.
    """

    def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int,
        max_results: int,
    ) -> Sequence[RawPlace]:
        ...


# ── GooglePlacesProvider (stub — deferred until API key provisioned) ──────────


class GooglePlacesProvider:
    """Google Places Nearby Search v1 client.

    Gated on GOOGLE_PLACES_API_KEY. For demo purposes this path is not reached
    (MockPlacesProvider is selected by default when no key is set). When a real
    key is provisioned in production, this stub should be replaced with a full
    httpx-based implementation targeting:
        POST https://places.googleapis.com/v1/places:searchNearby
    with an ``X-Goog-FieldMask`` header.

    Raises:
        NotImplementedError — always (implementation deferred, OQ-PLACES-1).
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int,
        max_results: int,
    ) -> Sequence[RawPlace]:
        raise NotImplementedError(
            "GooglePlacesProvider is not yet implemented (OQ-PLACES-1). "
            "Set PLACES_PROVIDER=mock or remove GOOGLE_PLACES_API_KEY to use MockPlacesProvider."
        )


# ── MockPlacesProvider (deterministic Dallas demo fixture) ─────────────────────


# fmt: off
# Coordinates are best-guess Uptown Dallas offsets centred on
# venue (32.776664, -96.796988).  Real Place API geometry will
# replace these when GooglePlacesProvider is implemented (OQ-FOOD-DECK-3).
_DALLAS_FIXTURE: list[RawPlace] = [
    RawPlace(
        name="Chipotle Mexican Grill",
        types=["restaurant", "meal_takeaway", "food", "establishment"],
        distance_meters=1200,
        drive_time_minutes=4,
        place_id="mock_chipotle_dallas_001",
        provider="mock",
        lat=32.7825,
        lng=-96.7975,
    ),
    RawPlace(
        name="Jimmy John's",
        types=["restaurant", "sandwich_shop", "food", "establishment"],
        distance_meters=800,
        drive_time_minutes=3,
        place_id="mock_jimmyjohns_dallas_001",
        provider="mock",
        lat=32.7820,
        lng=-96.8025,
    ),
    RawPlace(
        name="Central Market",
        types=["supermarket", "grocery_store", "food", "establishment"],
        distance_meters=3500,
        drive_time_minutes=9,
        place_id="mock_centralmarket_dallas_001",
        provider="mock",
        lat=32.7755,
        lng=-96.7920,
    ),
    RawPlace(
        name="Starbucks",
        types=["cafe", "bakery", "food", "establishment"],
        distance_meters=600,
        drive_time_minutes=2,
        place_id="mock_starbucks_dallas_001",
        provider="mock",
        lat=32.7805,
        lng=-96.7990,
    ),
]
# fmt: on


class MockPlacesProvider:
    """Deterministic Dallas demo fixture.

    Returns ≥ 3 places near (32.78, −96.80) ± 0.5° so the Dallas seed always
    renders foodOptions with the mock provider. Returns [] outside that bbox.

    Fixture roster (stable across test runs):
        Chipotle Mexican Grill  — fast_casual_bowl, ~1200 m, 4 min
        Jimmy John's            — sandwich_shop,    ~800 m,  3 min
        Central Market          — grocery_prepared, ~3500 m, 9 min
        Starbucks               — breakfast_cafe,   ~600 m,  2 min
    """

    def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int,  # noqa: ARG002  (radius not used for bbox mock)
        max_results: int,
    ) -> Sequence[RawPlace]:
        if abs(lat - _DALLAS_LAT) > _DALLAS_RADIUS_DEG:
            return []
        if abs(lng - _DALLAS_LNG) > _DALLAS_RADIUS_DEG:
            return []
        return _DALLAS_FIXTURE[:max_results]


# ── Factory ───────────────────────────────────────────────────────────────────


def find_nearby_food(lat: float, lng: float) -> list[RawPlace]:
    """Return places near (lat, lng) using the configured provider.

    Provider selection order:
        1. Read settings.PLACES_PROVIDER + settings.GOOGLE_PLACES_API_KEY.
        2. "mock"   → always MockPlacesProvider.
        3. "google" → GooglePlacesProvider (raises NotImplementedError now).
        4. "auto"   → Google if GOOGLE_PLACES_API_KEY non-empty, else Mock.

    Returns:
        list[RawPlace] — may be empty on error or no results in bbox.
        Never raises (food is a non-critical augmentation — errors are logged
        and swallowed so the plan endpoint always returns 200).
    """
    from playfuel_api.settings import get_settings

    settings = get_settings()
    provider_name = settings.places_provider.lower()
    api_key = settings.google_places_api_key

    provider: PlacesProvider

    if provider_name == "mock":
        provider = MockPlacesProvider()
    elif provider_name == "google":
        if not api_key:
            _logger.warning(
                "PLACES_PROVIDER=google but GOOGLE_PLACES_API_KEY is not set; "
                "falling back to MockPlacesProvider"
            )
            provider = MockPlacesProvider()
        else:
            provider = GooglePlacesProvider(api_key)
    else:  # "auto" or unrecognised
        if api_key:
            provider = GooglePlacesProvider(api_key)
        else:
            provider = MockPlacesProvider()

    try:
        results = provider.search_nearby(
            lat,
            lng,
            settings.places_search_radius_m,
            settings.places_max_results,
        )
        return list(results)
    except (PlacesProviderError, NotImplementedError) as exc:
        _logger.warning("Places provider error: %s — returning empty food list", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        _logger.error("Unexpected Places error: %s — returning empty food list", exc)
        return []
