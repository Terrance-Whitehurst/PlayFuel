"""ACCOMMODATIONS_V1.md §I — plan integration tests for accommodation feature.

Tests (§I.1 acceptance scenarios):
    T-01  GATING: null accommodation → plan output byte-for-byte identical (regression gate)
    T-03  Hotel accommodation ~25 km → departure event emitted, title "Leave the hotel"
    T-04  Home accommodation ~50 km → departure event at T-120 min, no heat addendum
    T-05  ~50 km + extreme_heat_risk → departure detail appends heat addendum
    T-06  Hot (not extreme) flag → no heat addendum
    T-07  0.1 km → rounds to 0 min → no departure event
    T-08  200 km → capped at 120 min → departure event present with long-drive warning
    T-09  accommodation_kind='hotel' → title = "Leave the hotel"
    T-10  accommodation_kind='home' → title = "Leave home"
    T-11  accommodation_kind=None → title defaults to "Leave home"
    T-OQ  Departure event time is the right number of minutes before match start.

All tests call build_timeline() directly (unit-level; no HTTP/DB).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import TimelineEventKind
from playfuel_api.rules.constants import ARRIVE_SNACK_MIN
from playfuel_api.rules.plan import build_timeline
from playfuel_api.rules.scenarios import generate_match_scenarios

# ── Shared fixtures ───────────────────────────────────────────────────────────

_VENUE_LAT = 32.75
_VENUE_LNG = -97.33  # Fort Worth venue

_MATCH_START = datetime(2026, 8, 15, 14, 0, 0, tzinfo=timezone.utc)  # 9 AM CDT = 14:00 UTC

_BASE_MATCH_ID = uuid.UUID("c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
_BASE_TOURNAMENT_ID = uuid.UUID("b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def _make_match(match_start: datetime = _MATCH_START) -> MatchRow:
    """Minimal MatchRow for plan tests."""
    return MatchRow(
        id=_BASE_MATCH_ID,
        tournament_id=_BASE_TOURNAMENT_ID,
        scheduled_start=match_start,
        format="singles",
        is_done=False,
        created_at=match_start,
        updated_at=match_start,
    )


def _scenarios(match: MatchRow):
    """Generate scenarios (no next match) for a given MatchRow."""
    return generate_match_scenarios(match, None)


def _find_departure(timeline) -> object | None:
    """Return the first departure event in a timeline, or None."""
    return next(
        (e for e in timeline if e.kind == TimelineEventKind.departure),
        None,
    )


# ── T-01: Null accommodation regression gate ──────────────────────────────────


def test_t01_null_accommodation_plan_unchanged():
    """T-01 GATING: null accommodation → no departure event; plan shape unchanged.

    This is the regression-safety gate. Any accommodation-derived change to the
    timeline when accommodation_lat is None means the sentinel (0 return) is broken.

    Comparison approach: call build_timeline() with no accommodation args first
    (baseline = pre-feature call signature), then call with explicit None args,
    then assert departure kind is absent in both.
    """
    match = _make_match()
    scenarios = _scenarios(match)

    # Baseline: pre-feature call signature (no new keyword args).
    baseline = build_timeline([match], scenarios)

    # With explicit None args: must produce identical output (byte-for-byte).
    with_nones = build_timeline(
        [match],
        scenarios,
        accommodation_lat=None,
        accommodation_lng=None,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind=None,
        weather_flags=None,
    )

    # Neither should have a departure event.
    assert _find_departure(baseline) is None, (
        "departure event present in baseline (no accommodation) — regression!"
    )
    assert _find_departure(with_nones) is None, (
        "departure event present when accommodation=None — regression!"
    )

    # Shape must match: same kinds in same order.
    baseline_kinds = [str(e.kind) for e in baseline]
    nones_kinds = [str(e.kind) for e in with_nones]
    assert baseline_kinds == nones_kinds, (
        f"Timeline kinds differ between baseline and None-accommodation: "
        f"{baseline_kinds} vs {nones_kinds}"
    )

    # Serialize both to sorted JSON (excluding fresh UUIDs) and compare field shapes.
    def _normalise(tl):
        return [
            json.dumps({k: v for k, v in e.model_dump().items() if k != "id"}, sort_keys=True)
            for e in tl
        ]

    assert _normalise(baseline) == _normalise(with_nones), (
        "plan envelope JSON differs between baseline and None-accommodation — regression!"
    )


# ── T-07: Rounds to 0 → no departure ─────────────────────────────────────────


def test_t07_drive_rounds_to_zero_no_departure():
    """T-07: accommodation 0.1 km from venue → estimate rounds to 0 → no departure event."""
    match = _make_match()
    scenarios = _scenarios(match)
    # 0.1 km offset (≈0.001° lat)
    timeline = build_timeline(
        [match], scenarios,
        accommodation_lat=_VENUE_LAT + 0.001,
        accommodation_lng=_VENUE_LNG,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind="home",
    )
    assert _find_departure(timeline) is None, (
        "departure event emitted for 0.1 km drive (rounds to 0) — should be absent"
    )


# ── T-08: 200 km cap + long-drive warning ────────────────────────────────────


def test_t08_long_drive_capped_at_120():
    """T-08: 200 km → capped at 120 min; departure event present + long-drive warning."""
    match = _make_match()
    scenarios = _scenarios(match)
    # ~200 km north of venue: ~1.8° lat offset.
    timeline = build_timeline(
        [match], scenarios,
        accommodation_lat=_VENUE_LAT + 1.8,
        accommodation_lng=_VENUE_LNG,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind="home",
    )
    departure = _find_departure(timeline)
    assert departure is not None, "Expected departure event for 120-min drive"
    assert "120-minute drive" in departure.detail, (
        f"Expected '120-minute drive' in detail (capped), got: {departure.detail!r}"
    )
    # Long-drive warning should be present (≥90 min threshold)
    assert "route planned the night before" in departure.detail, (
        f"Expected long-drive warning in detail, got: {departure.detail!r}"
    )


# ── T-09/T-10/T-11: Kind → title mapping ─────────────────────────────────────


@pytest.mark.parametrize("kind,expected_title", [
    ("hotel", "Leave the hotel"),
    ("home",  "Leave home"),
    (None,    "Leave home"),   # T-11: None defaults to home copy
])
def test_accommodation_kind_title(kind, expected_title):
    """T-09/T-10/T-11: accommodation_kind drives departure event title."""
    match = _make_match()
    scenarios = _scenarios(match)
    # Use a 25 km offset (≈0.225° lat ≈ 25 km → 30 min)
    timeline = build_timeline(
        [match], scenarios,
        accommodation_lat=_VENUE_LAT + 0.225,
        accommodation_lng=_VENUE_LNG,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind=kind,
    )
    departure = _find_departure(timeline)
    assert departure is not None, f"Expected departure event for kind={kind!r}"
    assert departure.title == expected_title, (
        f"For kind={kind!r}: expected title {expected_title!r}, got {departure.title!r}"
    )


# ── T-03: Hotel 25 km → departure time and detail ────────────────────────────


def test_t03_hotel_25km_departure_event():
    """T-03: hotel accommodation ~25 km → departure event, correct title and detail."""
    match = _make_match()
    scenarios = _scenarios(match)
    # ~25 km offset → raw_min ≈ 30 → estimate = 30 min
    timeline = build_timeline(
        [match], scenarios,
        accommodation_lat=_VENUE_LAT + 0.225,
        accommodation_lng=_VENUE_LNG,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind="hotel",
    )
    departure = _find_departure(timeline)
    assert departure is not None, "Expected departure event for 25 km hotel drive"
    assert departure.title == "Leave the hotel", (
        f"Expected 'Leave the hotel', got {departure.title!r}"
    )
    assert "minute drive" in departure.detail, departure.detail
    # No heat addendum (no weather_flags passed)
    assert "pre-cool" not in departure.detail, departure.detail


def test_t03_departure_time_is_correct():
    """T-03: departure time = match_start - ARRIVE_SNACK_MIN - drive_minutes."""
    match = _make_match()
    scenarios = _scenarios(match)
    # 25 km → 30 min drive
    timeline = build_timeline(
        [match], scenarios,
        accommodation_lat=_VENUE_LAT + 0.225,
        accommodation_lng=_VENUE_LNG,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind="hotel",
    )
    departure = _find_departure(timeline)
    assert departure is not None

    # Parse departure time from ISO string
    departure_dt = datetime.fromisoformat(departure.time.replace("Z", "+00:00"))
    # match_start - ARRIVE_SNACK_MIN(60) - drive(30) = match_start - 90 min
    from datetime import timedelta
    expected_dt = _MATCH_START - timedelta(minutes=ARRIVE_SNACK_MIN + 30)
    delta_seconds = abs((departure_dt - expected_dt).total_seconds())
    assert delta_seconds < 60, (
        f"Departure time off by {delta_seconds}s: expected {expected_dt.isoformat()}, "
        f"got {departure_dt.isoformat()}"
    )


# ── T-04: Home 50 km, no heat ────────────────────────────────────────────────


def test_t04_home_50km_no_heat():
    """T-04: home accommodation ~50 km → departure event; no heat addendum (no weather)."""
    match = _make_match()
    scenarios = _scenarios(match)
    # ~50 km → raw_min ≈ 60 → estimate = 60 min
    timeline = build_timeline(
        [match], scenarios,
        accommodation_lat=_VENUE_LAT + 0.45,
        accommodation_lng=_VENUE_LNG,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind="home",
    )
    departure = _find_departure(timeline)
    assert departure is not None, "Expected departure event for 50 km home drive"
    assert departure.title == "Leave home"
    assert "pre-cool" not in departure.detail, (
        f"Heat addendum should not appear without extreme heat flag: {departure.detail!r}"
    )


# ── T-05: Extreme heat addendum ───────────────────────────────────────────────


def test_t05_extreme_heat_addendum():
    """T-05: drive ≥ 45 min + flag_extreme_heat_risk=True → heat addendum in detail."""
    match = _make_match()
    scenarios = _scenarios(match)
    # ~50 km → 60 min (≥ 45 threshold)
    timeline = build_timeline(
        [match], scenarios,
        accommodation_lat=_VENUE_LAT + 0.45,
        accommodation_lng=_VENUE_LNG,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind="home",
        weather_flags={
            "flag_hot": True,
            "flag_very_hot": True,
            "flag_extreme_heat_risk": True,
            "flag_humid": True,
            "flag_cold": False,
            "flag_windy": False,
            "flag_rain_risk": False,
        },
    )
    departure = _find_departure(timeline)
    assert departure is not None, "Expected departure event for 50 km drive"
    assert "pre-cool the car" in departure.detail, (
        f"Expected heat addendum in detail, got: {departure.detail!r}"
    )
    assert "sip water" in departure.detail


# ── T-06: Hot (not extreme) → no heat addendum ───────────────────────────────


def test_t06_hot_not_extreme_no_heat_addendum():
    """T-06: flag_hot=True, flag_extreme_heat_risk=False → no heat addendum."""
    match = _make_match()
    scenarios = _scenarios(match)
    # ~50 km → 60 min
    timeline = build_timeline(
        [match], scenarios,
        accommodation_lat=_VENUE_LAT + 0.45,
        accommodation_lng=_VENUE_LNG,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind="home",
        weather_flags={
            "flag_hot": True,
            "flag_very_hot": False,
            "flag_extreme_heat_risk": False,  # key threshold
            "flag_humid": False,
            "flag_cold": False,
            "flag_windy": False,
            "flag_rain_risk": False,
        },
    )
    departure = _find_departure(timeline)
    assert departure is not None, "Expected departure event for 50 km drive"
    assert "pre-cool" not in departure.detail, (
        f"Heat addendum should not appear for hot-but-not-extreme weather: {departure.detail!r}"
    )


# ── T-timeline-ordering: departure before match ───────────────────────────────


def test_departure_event_appears_before_match_event():
    """Departure event is always chronologically before the match event."""
    match = _make_match()
    scenarios = _scenarios(match)
    timeline = build_timeline(
        [match], scenarios,
        accommodation_lat=_VENUE_LAT + 0.225,
        accommodation_lng=_VENUE_LNG,
        venue_lat=_VENUE_LAT,
        venue_lng=_VENUE_LNG,
        accommodation_kind="home",
    )
    kinds = [e.kind for e in timeline]
    assert TimelineEventKind.departure in kinds
    dep_idx = kinds.index(TimelineEventKind.departure)
    match_idx = kinds.index(TimelineEventKind.match)
    assert dep_idx < match_idx, (
        f"departure index ({dep_idx}) should be before match index ({match_idx})"
    )


# ── Departure kind in enum ────────────────────────────────────────────────────


def test_departure_kind_in_timeline_event_kind_enum():
    """TimelineEventKind.departure must exist and have value 'departure'."""
    assert TimelineEventKind.departure == "departure"


def test_arrive_snack_min_is_60():
    """ARRIVE_SNACK_MIN must be 60 (RULES_CONSTANTS_V1.md §D.1)."""
    assert ARRIVE_SNACK_MIN == 60
