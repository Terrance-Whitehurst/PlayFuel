"""Places provider abstraction. Mirrors weather/service.py structure.

Phase 5 / Task #8 — food options via venue-adjacent restaurant lookup.

Provider selection (settings.PLACES_PROVIDER):
    "auto"   → GooglePlacesProvider if GOOGLE_PLACES_API_KEY set, else MockPlacesProvider
    "google" → GooglePlacesProvider (key required; falls back to Mock if key absent)
    "mock"   → MockPlacesProvider always (deterministic fixture — used in tests + demo)

The Dallas demo works end-to-end with MockPlacesProvider — no API key required.
GooglePlacesProvider calls Places API (New) and caches results in
tournament_places_cache for 24 h (PLACES_CACHE_TTL_SEC).

Cache strategy:
  - Key: (tournament_id, place_type='food')
  - TTL: 24 h (restaurants don't change daily; 24 h balances freshness vs. quota)
  - Read-through: check cache before HTTP call; return cached payload on hit
  - Write-on-miss: upsert into cache after successful Google Places call
  - Failure modes (OQ-FOOD-EMPTY-1: production Google failures raise, never mock-fallback):
      4xx (incl. 401) → log + raise PlacesUnavailableError (plan sets placesUnavailable=True)
      5xx/timeout + cache stale → return stale data + log WARNING
      5xx/timeout + cache empty → raise PlacesUnavailableError (plan sets placesUnavailable=True)
      401 specifically → log "API key invalid — check rotation" + raise PlacesUnavailableError
  - MockPlacesProvider: NEVER selected on Google failure (prevents silent fake-data bug).
    Mock is ONLY used when PLACES_PROVIDER=mock or GOOGLE_PLACES_API_KEY is unset.

# TODO: rotate the GOOGLE_PLACES_API_KEY after smoke test (key was shared in chat)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, Sequence
from uuid import UUID

import httpx

_logger = logging.getLogger(__name__)

# Cache TTL: 24 hours. Enforced at the Python layer; the DB stores raw fetched_at.
PLACES_CACHE_TTL_SEC: int = 86_400
_CACHE_TABLE = "tournament_places_cache"

# ── MockPlacesProvider fixture offsets ──────────────────────────────────────
# Reference origin: Dallas demo venue (32.78, −96.80). Each template stores a
# lat/lng offset from this origin.  search_nearby applies these offsets to the
# CALLER'S lat/lng, making MockPlacesProvider work for any city, not just Dallas.
_DALLAS_LAT = 32.78   # offset reference — documentation only, NOT a bbox gate
_DALLAS_LNG = -96.80  # offset reference — documentation only, NOT a bbox gate


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RawPlace:
    """Normalised single place record returned by any PlacesProvider.

    ``types`` mirrors the Google Places API ``types[]`` field.
    ``provider`` identifies the data source ("google" | "mock").

    ``lat`` and ``lng`` are geographic coordinates of the place.
    None when the provider does not return geometry (e.g. legacy stub paths).
    MockPlacesProvider supplies best-guess Uptown Dallas offsets (OQ-FOOD-DECK-3).
    GooglePlacesProvider surfaces geometry.location.lat / .lng.
    Added: FOOD_DECK_AND_MAP_V1.md §G.2.

    ``formatted_address`` is the human-readable address string from Google Places.
    ``rating`` is the Google Places rating (0.0–5.0).
    ``price_level`` is the Google Places price level (FREE/INEXPENSIVE/MODERATE/
    EXPENSIVE/VERY_EXPENSIVE or None).
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
    # Extended fields from Google Places (New)
    formatted_address: str | None = None
    rating: float | None = None
    price_level: str | None = None


class PlacesProviderError(Exception):
    """Raised by a PlacesProvider on unrecoverable errors.

    ``find_nearby_food()`` catches this and returns [] — food is non-critical.
    """


class PlacesUnavailableError(Exception):
    """Raised by GooglePlacesProvider when the API key is set but the real
    provider fails (401, 4xx, 5xx, or timeout with no stale cache).

    Distinct from PlacesProviderError (generic provider issues). The plan-gen
    route catches this to set places_unavailable=True on the Plan envelope so
    iOS renders an explicit "unavailable" empty state instead of silently
    showing nothing.

    Never raised by MockPlacesProvider — only fires in production when
    GOOGLE_PLACES_API_KEY is set but the Google API cannot be reached.
    """


# ── Protocol (structural interface) ───────────────────────────────────────────


class PlacesProvider(Protocol):
    """Structural interface for Places backends.

    ``search_nearby`` is required. tournament_id is optional (None → skip cache).
    """

    def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int,
        max_results: int,
        tournament_id: UUID | None = None,
    ) -> Sequence[RawPlace]:
        ...


# ── GooglePlacesProvider ──────────────────────────────────────────────────────

_GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.types,"
    "places.location,"
    "places.rating,"
    "places.priceLevel"
    # places.distanceMeters intentionally OMITTED — invalid in Google Places (New)
    # searchNearby API. Including it causes 400 INVALID_ARGUMENT on every call.
    # Distance sort uses haversine(_distance_key in rules/food.py) from
    # places.location lat/lng instead. RawPlace.distance_meters will be None
    # for all GooglePlacesProvider results; _distance_key falls back to
    # haversine when distance_meters is None (FOOD_PLACES_FILTER_V1 §E.3).
    # DR-PLACES-1: do NOT add places.distanceMeters here — verify against the
    # official Places (New) field-mask docs before re-adding any field.
)
# Place types to include (Google Places (New) type list).
# Food-primary only — FOOD_PLACES_FILTER_V1.md §C.
# supermarket/grocery REMOVED — this was the root cause of Publix surfacing (§C).
_INCLUDED_TYPES: list[str] = [
    # ── Core food-primary ────────────────────────────────────────────────────
    "restaurant",
    "cafe",
    "coffee_shop",
    "bakery",
    "fast_food_restaurant",
    "meal_takeaway",
    "meal_delivery",
    # ── Format-specific (cuisine buckets already in _TYPE_MAP) ───────────────
    "sandwich_shop",
    "pizza_restaurant",
    "italian_restaurant",
    "mexican_restaurant",
    "chinese_restaurant",
    "japanese_restaurant",
    "american_restaurant",
    "breakfast_restaurant",
    "brunch_restaurant",
    # ── Hydration/snack ────────────────────────────────────────────
    # juice_bar intentionally OMITTED — not a valid includedType in Google Places (New);
    # returns 400 INVALID_ARGUMENT when included. DR-PLACES-1.
    "ice_cream_shop",
    "diner",
]


def _raw_place_to_dict(p: RawPlace) -> dict:
    """Serialise a RawPlace for JSONB cache storage."""
    return {
        "name": p.name,
        "types": p.types,
        "distance_meters": p.distance_meters,
        "drive_time_minutes": p.drive_time_minutes,
        "place_id": p.place_id,
        "provider": p.provider,
        "lat": p.lat,
        "lng": p.lng,
        "formatted_address": p.formatted_address,
        "rating": p.rating,
        "price_level": p.price_level,
    }


def _dict_to_raw_place(d: dict) -> RawPlace:
    """Deserialise a RawPlace from JSONB cache payload."""
    return RawPlace(
        name=d.get("name", ""),
        types=d.get("types", []),
        distance_meters=d.get("distance_meters"),
        drive_time_minutes=d.get("drive_time_minutes"),
        place_id=d.get("place_id"),
        provider=d.get("provider", "google"),
        lat=d.get("lat"),
        lng=d.get("lng"),
        formatted_address=d.get("formatted_address"),
        rating=d.get("rating"),
        price_level=d.get("price_level"),
    )


class GooglePlacesProvider:
    """Google Places Nearby Search (New) client with cache read-through.

    Calls POST https://places.googleapis.com/v1/places:searchNearby.
    Uses X-Goog-FieldMask for minimal response size (New API requirement).

    Cache read-through:
        If tournament_id is provided, check tournament_places_cache for a
        (tournament_id, 'food') row fetched within PLACES_CACHE_TTL_SEC (24 h).
        On cache hit: return cached payload (no HTTP call).
        On cache miss: call Google, upsert result, return fresh data.

    Error handling (OQ-FOOD-EMPTY-1: no silent mock fallback):
        4xx (incl. 401): log + raise PlacesUnavailableError (plan sets placesUnavailable=True)
        401 specifically: log "API key invalid — check rotation" + raise PlacesUnavailableError
        5xx / timeout + cache has stale row: return stale + log warning
        5xx / timeout + cache empty: raise PlacesUnavailableError (plan sets placesUnavailable=True)

    API key: settings.google_places_api_key
    # TODO: rotate GOOGLE_PLACES_API_KEY after smoke test (key was shared in chat)
    """

    def __init__(self, api_key: str, db_client=None) -> None:
        self._api_key = api_key
        self._db_client = db_client  # Supabase client; None in unit tests

    def _read_cache(self, tournament_id: UUID, place_type: str) -> list[RawPlace] | None:
        """Return cached places if within TTL, else None.

        Returns:
            list[RawPlace] on fresh cache hit.
            None on cache miss or stale entry.
            "stale" list[RawPlace] is surfaced only during HTTP failures (see
            _read_stale_cache).
        """
        if self._db_client is None:
            return None
        try:
            result = (
                self._db_client.table(_CACHE_TABLE)
                .select("payload, fetched_at")
                .eq("tournament_id", str(tournament_id))
                .eq("place_type", place_type)
                .limit(1)
                .execute()
            )
            if not result.data:
                return None
            row = result.data[0]
            fetched_at_str = row["fetched_at"]
            # Parse ISO 8601 with timezone
            if fetched_at_str.endswith("Z"):
                fetched_at_str = fetched_at_str[:-1] + "+00:00"
            fetched_at = datetime.fromisoformat(fetched_at_str)
            age = (datetime.now(tz=timezone.utc) - fetched_at).total_seconds()
            if age <= PLACES_CACHE_TTL_SEC:
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                return [_dict_to_raw_place(p) for p in payload]
            # Stale but present — we'll use it on HTTP errors
            return None
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Places cache read error: %s", exc)
            return None

    def _read_stale_cache(self, tournament_id: UUID, place_type: str) -> list[RawPlace] | None:
        """Return any cached row regardless of TTL (for HTTP failure fallback)."""
        if self._db_client is None:
            return None
        try:
            result = (
                self._db_client.table(_CACHE_TABLE)
                .select("payload")
                .eq("tournament_id", str(tournament_id))
                .eq("place_type", place_type)
                .limit(1)
                .execute()
            )
            if not result.data:
                return None
            payload = result.data[0]["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            return [_dict_to_raw_place(p) for p in payload]
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Places stale cache read error: %s", exc)
            return None

    def _write_cache(
        self, tournament_id: UUID, place_type: str, places: list[RawPlace]
    ) -> None:
        """Upsert places into cache. Errors are logged and swallowed."""
        if self._db_client is None:
            return
        try:
            payload = [_raw_place_to_dict(p) for p in places]
            self._db_client.table(_CACHE_TABLE).upsert(
                {
                    "tournament_id": str(tournament_id),
                    "place_type": place_type,
                    "payload": payload,
                    "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
                },
                on_conflict="tournament_id,place_type",
            ).execute()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Places cache write error (non-critical): %s", exc)

    def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int,
        max_results: int,
        tournament_id: UUID | None = None,
    ) -> list[RawPlace]:
        """Search for nearby food places, with cache read-through.

        Args:
            lat, lng: Venue coordinates.
            radius_m: Search radius in metres.
            max_results: Maximum number of places to return.
            tournament_id: If provided, read/write tournament_places_cache.

        Returns:
            list[RawPlace] — may be empty.

        Raises:
            PlacesProviderError — only on HTTP 5xx/timeout when cache is also empty.
        """
        place_type = "food"

        # Cache read-through (skip if no tournament_id)
        if tournament_id is not None:
            cached = self._read_cache(tournament_id, place_type)
            if cached is not None:
                _logger.debug(
                    "Places cache HIT for tournament %s (type=%s, count=%d)",
                    tournament_id, place_type, len(cached),
                )
                return cached

        # Call Google Places (New) API
        body = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius_m),
                }
            },
            "maxResultCount": min(max_results, 20),
            "includedTypes": _INCLUDED_TYPES,
        }
        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
            "Content-Type": "application/json",
        }

        try:
            resp = httpx.post(
                _GOOGLE_PLACES_URL, json=body, headers=headers, timeout=8.0
            )
        except httpx.TimeoutException as exc:
            _logger.warning("Google Places request timed out: %s", exc)
            return self._handle_http_error(tournament_id, place_type, lat, lng, radius_m, max_results, is_timeout=True)
        except httpx.RequestError as exc:
            _logger.warning("Google Places request failed (transport): %s", exc)
            return self._handle_http_error(tournament_id, place_type, lat, lng, radius_m, max_results, is_timeout=True)

        # HTTP error handling
        if resp.status_code == 401:
            _logger.warning(
                "Google Places API returned 401 — API key invalid or expired. "
                "Rotate: flyctl secrets set GOOGLE_PLACES_API_KEY=<new-key> --app playfuel-api"
            )
            raise PlacesUnavailableError(
                "Google Places 401 — API key invalid or expired. "
                "See Fly logs for rotation instructions."
            )

        if resp.status_code >= 400 and resp.status_code < 500:
            _logger.warning(
                "Google Places API returned %d (client error): %s",
                resp.status_code,
                resp.text[:200],
            )
            raise PlacesUnavailableError(
                f"Google Places {resp.status_code} client error"
            )

        if resp.status_code >= 500:
            _logger.warning(
                "Google Places API returned %d (server error): %s",
                resp.status_code,
                resp.text[:200],
            )
            return self._handle_http_error(tournament_id, place_type, lat, lng, radius_m, max_results, is_timeout=False)

        # Parse successful response
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Google Places response JSON parse error: %s", exc)
            return []

        raw_places_data = data.get("places", [])
        results: list[RawPlace] = []
        for p in raw_places_data:
            loc = p.get("location", {})
            name_obj = p.get("displayName", {})
            name = name_obj.get("text", "") if isinstance(name_obj, dict) else str(name_obj)
            results.append(
                RawPlace(
                    name=name,
                    types=p.get("types", []),
                    distance_meters=p.get("distanceMeters"),
                    drive_time_minutes=None,  # Places (New) does not return drive time
                    place_id=p.get("id"),
                    provider="google",
                    lat=loc.get("latitude"),
                    lng=loc.get("longitude"),
                    formatted_address=p.get("formattedAddress"),
                    rating=p.get("rating"),
                    price_level=p.get("priceLevel"),
                )
            )

        # Cache write-on-miss
        if tournament_id is not None and results:
            self._write_cache(tournament_id, place_type, results)

        return results

    def _handle_http_error(
        self,
        tournament_id: UUID | None,
        place_type: str,
        lat: float,
        lng: float,
        radius_m: int,
        max_results: int,
        *,
        is_timeout: bool,
    ) -> list[RawPlace]:
        """On HTTP 5xx or timeout: return stale cache if available.

        When no stale cache is available, raises PlacesUnavailableError so the
        plan-gen route can set places_unavailable=True on the Plan envelope.
        Does NOT fall back to MockPlacesProvider — that would mask production
        API failures with fake restaurant data.
        """
        if tournament_id is not None:
            stale = self._read_stale_cache(tournament_id, place_type)
            if stale is not None:
                _logger.warning(
                    "Google Places HTTP error — returning stale cache for tournament %s",
                    tournament_id,
                )
                return stale
        reason = "timeout" if is_timeout else "server error"
        _logger.warning(
            "Google Places %s — no stale cache for venue (%.4f, %.4f); "
            "raising PlacesUnavailableError so plan sets placesUnavailable=true",
            reason, lat, lng,
        )
        raise PlacesUnavailableError(
            f"Google Places {reason} — no stale cache available"
        )


# ── MockPlacesProvider (deterministic Dallas demo fixture) ─────────────────────


# fmt: off
# Fixture templates: each entry stores offsets from the caller's (lat, lng).
# Offsets are computed relative to Dallas demo center (_DALLAS_LAT/_DALLAS_LNG)
# so that distances and drive-times remain realistic.  Applying offsets to ANY
# input coords makes the mock work for Austin, NYC, or any other city.
#
# Offset math (origin = 32.78, -96.80):
#   Chipotle   32.7825 → +0.0025  / -96.7975 → +0.0025
#   Jimmy John's 32.7820 → +0.0020  / -96.8025 → -0.0025
#   Central Market 32.7755 → -0.0045  / -96.7920 → +0.0080
#   Starbucks  32.7805 → +0.0005  / -96.7990 → +0.0010
#   Domino's   (new)   → +0.0030  /           → -0.0015
_FIXTURE_TEMPLATES: list[dict] = [
    {
        "name": "Chipotle Mexican Grill",
        "types": ["restaurant", "meal_takeaway", "food", "establishment"],
        "distance_meters": 1200,
        "drive_time_minutes": 4,
        "place_id": "mock_chipotle_001",
        "lat_offset": 0.0025,
        "lng_offset": 0.0025,
    },
    {
        "name": "Jimmy John's",
        "types": ["restaurant", "sandwich_shop", "food", "establishment"],
        "distance_meters": 800,
        "drive_time_minutes": 3,
        "place_id": "mock_jimmyjohns_001",
        "lat_offset": 0.0020,
        "lng_offset": -0.0025,
    },
    {
        "name": "Central Market",
        "types": ["supermarket", "grocery_store", "food", "establishment"],
        "distance_meters": 3500,
        "drive_time_minutes": 9,
        "place_id": "mock_centralmarket_001",
        "lat_offset": -0.0045,
        "lng_offset": 0.0080,
    },
    {
        "name": "Starbucks",
        "types": ["cafe", "bakery", "food", "establishment"],
        "distance_meters": 600,
        "drive_time_minutes": 2,
        "place_id": "mock_starbucks_001",
        "lat_offset": 0.0005,
        "lng_offset": 0.0010,
    },
    {
        "name": "Domino's Pizza",
        "types": ["restaurant", "pizza_restaurant", "food", "establishment"],
        "distance_meters": 450,
        "drive_time_minutes": 2,
        "place_id": "mock_dominos_001",
        "lat_offset": 0.0030,
        "lng_offset": -0.0015,
    },
]
# fmt: on


class MockPlacesProvider:
    """Geo-agnostic deterministic fixture provider.

    Returns 4–5 RawPlace objects for ANY (lat, lng) input by applying fixed
    offsets from the caller's coordinates.  No bbox gate — works for Dallas,
    Austin, New York, or any other city.

    Use-when: PLACES_PROVIDER=mock (explicit), or as fallback when
    GooglePlacesProvider receives a 4xx / 5xx / timeout response.

    Fixture roster (stable across test runs):
        Chipotle Mexican Grill  — fast_casual_bowl, ~1200 m, 4 min
        Jimmy John's            — sandwich_shop,    ~800 m,  3 min
        Central Market          — grocery_prepared, ~3500 m, 9 min
        Starbucks               — breakfast_cafe,   ~600 m,  2 min
        Domino's Pizza          — pizza,            ~450 m,  2 min
    """

    def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: int,  # noqa: ARG002  (mock ignores radius — offset-based)
        max_results: int,
        tournament_id: UUID | None = None,  # noqa: ARG002  (no cache for mock)
    ) -> Sequence[RawPlace]:
        """Return up to max_results fixture places centred on (lat, lng)."""
        return [
            RawPlace(
                name=t["name"],
                types=t["types"],
                distance_meters=t["distance_meters"],
                drive_time_minutes=t["drive_time_minutes"],
                place_id=t["place_id"],
                provider="mock",
                lat=lat + t["lat_offset"],
                lng=lng + t["lng_offset"],
            )
            for t in _FIXTURE_TEMPLATES[:max_results]
        ]


# ── Factory ───────────────────────────────────────────────────────────────────


def find_nearby_food(
    lat: float,
    lng: float,
    tournament_id: UUID | None = None,
    db_client=None,
) -> list[RawPlace]:
    """Return places near (lat, lng) using the configured provider.

    Provider selection order:
        1. Read settings.PLACES_PROVIDER + settings.GOOGLE_PLACES_API_KEY.
        2. "mock"   → always MockPlacesProvider.
        3. "google" → GooglePlacesProvider (key required; falls back to Mock if missing).
        4. "auto"   → Google if GOOGLE_PLACES_API_KEY non-empty, else Mock.

    Args:
        lat, lng: Venue coordinates.
        tournament_id: If provided (and Google provider selected), enables
            cache read-through in tournament_places_cache (24h TTL).
        db_client: Supabase client instance for cache operations. If None,
            cache is skipped (e.g. unit tests without Supabase).

    Returns:
        list[RawPlace] — may be empty on error or no results in bbox.
        Never raises (food is a non-critical augmentation — errors are logged
        and swallowed so the plan endpoint always returns 200).
    """
    from playfuel_api.settings import get_settings

    settings = get_settings()
    provider_name = settings.places_provider.lower()
    # TODO: rotate GOOGLE_PLACES_API_KEY after smoke test (key was shared in chat)
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
            provider = GooglePlacesProvider(api_key, db_client=db_client)
    else:  # "auto" or unrecognised
        if api_key:
            provider = GooglePlacesProvider(api_key, db_client=db_client)
        else:
            provider = MockPlacesProvider()

    try:
        results = provider.search_nearby(
            lat,
            lng,
            settings.places_search_radius_m,
            settings.places_max_results,
            tournament_id=tournament_id,
        )
        return list(results)
    except PlacesUnavailableError:
        raise  # Propagate to _fetch_places_async() in routes/plans.py so the
               # plan envelope sets placesUnavailable=True for iOS empty-state.
               # Only raised by GooglePlacesProvider when GOOGLE_PLACES_API_KEY
               # is set — never from MockPlacesProvider (dev/test path).
    except (PlacesProviderError, NotImplementedError) as exc:
        _logger.warning("Places provider error: %s — returning empty food list", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        _logger.error("Unexpected Places error: %s — returning empty food list", exc)
        return []
