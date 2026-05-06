"""Unit tests for rules/distance.py — ACCOMMODATIONS_V1.md §F + §I.1 T-12.

Tests:
    test_haversine_same_point_is_zero
    test_haversine_dallas_to_fort_worth             — §I.1 T-12
    test_estimate_drive_minutes_none_sentinel        — §I.1 T-07 (None → 0)
    test_estimate_drive_minutes_dallas_fort_worth    — §I.1 T-12
    test_estimate_drive_minutes_rounds_to_zero       — §I.1 T-07 (0.1 km)
    test_estimate_drive_minutes_cap_at_120           — §I.1 T-08
    test_estimate_drive_minutes_5km                  — §I.1 T-02
    test_haversine_symmetry                          — d(A,B) == d(B,A)
    test_haversine_known_london_paris                — sanity cross-check
"""
from __future__ import annotations

import pytest

from playfuel_api.rules.distance import estimate_drive_minutes, haversine_km


# ── haversine_km unit tests ──────────────────────────────────────────────────


def test_haversine_same_point_is_zero():
    """haversine_km(0, 0, 0, 0) == 0."""
    assert haversine_km(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0, abs=1e-9)


def test_haversine_dallas_to_fort_worth():
    """§I.1 T-12 — Dallas (32.78, -96.80) → Fort Worth (32.75, -97.33) ≈ 48.5–50 km.

    Spec says '≈48.5 km' (approximate). Actual haversine yields 49.67 km for these
    exact coords. Tolerance is 2.0 km to account for coord precision in the spec.
    """
    d = haversine_km(32.78, -96.80, 32.75, -97.33)
    assert abs(d - 48.5) < 2.0, f"Expected ≈48.5 km (±2 km tolerance), got {d:.2f} km"


def test_haversine_symmetry():
    """Distance must be symmetric: haversine(A, B) == haversine(B, A)."""
    d1 = haversine_km(32.78, -96.80, 32.75, -97.33)
    d2 = haversine_km(32.75, -97.33, 32.78, -96.80)
    assert d1 == pytest.approx(d2, rel=1e-9)


def test_haversine_known_london_paris():
    """London (51.51, -0.13) to Paris (48.85, 2.35) ≈ 341 km (known reference distance)."""
    d = haversine_km(51.51, -0.13, 48.85, 2.35)
    # Accepted range 335–350 km (straight-line haversine; real driving is longer).
    assert 335.0 < d < 350.0, f"Expected 335–350 km, got {d:.2f} km"


# ── estimate_drive_minutes unit tests ────────────────────────────────────────


def test_estimate_drive_minutes_none_sentinel():
    """None accommodation_lat → 0 minutes (venue-local sentinel)."""
    result = estimate_drive_minutes(None, None, 0.0, 0.0)
    assert result == 0


def test_estimate_drive_minutes_none_lat_only():
    """None accommodation_lat with valid lng → 0 minutes (guard fires on either None)."""
    result = estimate_drive_minutes(None, -97.33, 32.75, -97.33)
    assert result == 0


def test_estimate_drive_minutes_none_lng_only():
    """None accommodation_lng with valid lat → 0 minutes."""
    result = estimate_drive_minutes(32.78, None, 32.75, -97.33)
    assert result == 0


def test_estimate_drive_minutes_dallas_fort_worth():
    """§I.1 T-12 — Dallas to Fort Worth (≈48.5 km) → 60 min.

    raw_min = (48.5 / 50.0) * 60 ≈ 58.2 → rounded to nearest 5 → 60.
    """
    result = estimate_drive_minutes(32.78, -96.80, 32.75, -97.33)
    assert result == 60


def test_estimate_drive_minutes_rounds_to_zero():
    """§I.1 T-07 — 0.1 km apart rounds to 0 min; no departure event should fire.

    raw_min = (0.1 / 50.0) * 60 = 0.12 → round(0.12 / 5) * 5 = 0.
    """
    # Use two points 0.1 km apart (roughly 0.001 degrees lat).
    result = estimate_drive_minutes(32.7800, -96.8000, 32.7809, -96.8000)
    assert result == 0


def test_estimate_drive_minutes_cap_at_120():
    """§I.1 T-08 — 200 km apart caps at 120 min.

    raw_min = (200 / 50.0) * 60 = 240 → capped at 120.
    Note: haversine of 200 km needs ~1.8° lat separation.
    """
    # Approximately 200 km north of Dallas.
    result = estimate_drive_minutes(32.78, -96.80, 34.60, -96.80)
    assert result == 120


def test_estimate_drive_minutes_5km():
    """§I.1 T-02 — 5 km apart → 5 min.

    raw_min = (5.0 / 50.0) * 60 = 6.0 → round(6.0 / 5) * 5 = 5.
    Using points approximately 0.045° apart (≈5 km at ~32° lat).
    """
    # haversine of ~5 km: 0.045° lat ≈ 5 km
    result = estimate_drive_minutes(32.7800, -96.8000, 32.8250, -96.8000)
    assert result == 5


def test_estimate_drive_minutes_result_is_multiple_of_5():
    """All results from estimate_drive_minutes are multiples of 5."""
    for lat_offset in [0.01, 0.05, 0.10, 0.20, 0.50, 1.0]:
        result = estimate_drive_minutes(
            32.78, -96.80,
            32.78 + lat_offset, -96.80,
        )
        assert result % 5 == 0, (
            f"Expected multiple of 5 for lat_offset={lat_offset}, got {result}"
        )


def test_estimate_drive_minutes_result_in_range():
    """All results are in [0, 120]."""
    for lat_offset in [0.001, 0.1, 0.5, 1.5, 2.0, 3.0, 5.0]:
        result = estimate_drive_minutes(
            0.0, 0.0,
            lat_offset, 0.0,
        )
        assert 0 <= result <= 120, (
            f"Expected result in [0, 120] for lat_offset={lat_offset}, got {result}"
        )
