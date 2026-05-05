"""Haversine distance and drive-time estimation for accommodation → venue.

MVP: pure-math estimate. No external API. No network calls. Deterministic.
Google Distance Matrix → post-MVP (see ACCOMMODATIONS_V1.md OQ-ACC-DRIVE).

Formula (§F.2):
    d_km = haversine_km(lat1, lng1, lat2, lng2)
    drive_min = min(120, max(0, round((d_km / AVG_DRIVE_KMH) * 60 / 5) * 5))

Rounding to nearest 5 min: consistent with calm-guidance voice (PRD §4).
Cap at 120 min: anything beyond is user error or needs a different model.
Sentinel: None accommodation → 0 minutes drive → all downstream logic unchanged.
"""
from __future__ import annotations

import math
from typing import Optional

EARTH_RADIUS_KM: float = 6371.0
AVG_DRIVE_KMH: float = 50.0  # urban + suburban blend; conservative; 0% traffic


def haversine_km(
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
) -> float:
    """Return great-circle distance in km between two WGS-84 coordinate pairs."""
    rlat1, rlng1, rlat2, rlng2 = (
        math.radians(lat1),
        math.radians(lng1),
        math.radians(lat2),
        math.radians(lng2),
    )
    d_lat = rlat2 - rlat1
    d_lng = rlng2 - rlng1
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(d_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_drive_minutes(
    accommodation_lat: Optional[float],
    accommodation_lng: Optional[float],
    venue_lat: float,
    venue_lng: float,
) -> int:
    """Estimate drive time (minutes, rounded to nearest 5, capped 0–120).

    Returns 0 when accommodation coords are None — sentinel for 'venue-local'.
    All downstream rules behave byte-for-byte as pre-feature when result is 0.

    Formula:
        drive_min = min(120, max(0, round((haversine_km / AVG_DRIVE_KMH) * 60 / 5) * 5))

    Args:
        accommodation_lat: Latitude of accommodation; None = no accommodation.
        accommodation_lng: Longitude of accommodation; None = no accommodation.
        venue_lat:         Latitude of tournament venue.
        venue_lng:         Longitude of tournament venue.

    Returns:
        Integer minutes, multiple of 5, in range [0, 120].
        0 when accommodation is None or distance rounds to 0.
    """
    if accommodation_lat is None or accommodation_lng is None:
        return 0
    d_km = haversine_km(accommodation_lat, accommodation_lng, venue_lat, venue_lng)
    raw_minutes = (d_km / AVG_DRIVE_KMH) * 60.0
    rounded = round(raw_minutes / 5.0) * 5
    return min(120, max(0, rounded))
