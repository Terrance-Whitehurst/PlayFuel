"""Test generate_match_scenarios() with doubles match types.

Covers DOUBLES_SPEC_V1.md §B.1 duration table:
    - doubles + best_of_3  → 60/90/135 min
    - doubles + pro_set_8  → 45/70/100 min
    - singles (default)    → 75/120/180 min (regression guard)
    - invalid combination  → ValueError

Also verifies that gap arithmetic and bucket logic work correctly with
the new durations (since bucket boundaries are unchanged from §B.2/§B.3
of RULES_CONSTANTS_V1 — same as singles per DOUBLES_SPEC_V1.md §C).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import FoodBucket, GapStatus, PickupBucket, ScenarioKind
from playfuel_api.rules.scenarios import generate_match_scenarios


# ── Helpers ───────────────────────────────────────────────────────────────────

_BASE = datetime(2026, 6, 14, 9, 0, tzinfo=timezone.utc)  # 9:00 AM anchor


def _match(start: datetime) -> MatchRow:
    tid = uuid4()
    return MatchRow(
        id=uuid4(),
        tournament_id=tid,
        scheduled_start=start,
        created_at=start,
        updated_at=start,
    )


def _match_pair(gap_after_normal_min: int, match_type_: str, doubles_fmt: str | None) -> tuple[MatchRow, MatchRow]:
    """Build a pair where the *normal* scenario for the given type produces exactly gap_after_normal_min."""
    from playfuel_api.rules.constants import SCENARIO_DURATIONS_MIN
    key = (match_type_, doubles_fmt)
    normal_dur = SCENARIO_DURATIONS_MIN[key]["normal"]
    next_start = _BASE + timedelta(minutes=normal_dur + gap_after_normal_min)
    m1 = _match(_BASE)
    m2 = _match(next_start)
    return m1, m2


# ── Singles regression ────────────────────────────────────────────────────────


def test_singles_durations_default():
    """Default (no kwargs) → 75/120/180 min. Regression guard."""
    m1, m2 = _match_pair(150, "singles", None)
    scenarios = generate_match_scenarios(m1, m2)
    durations = {s.scenario.value: s.duration_min for s in scenarios}
    assert durations == {"short": 75, "normal": 120, "long": 180}


def test_singles_explicit():
    """Explicit match_type='singles', doubles_format=None → same as default."""
    m1, m2 = _match_pair(150, "singles", None)
    scenarios = generate_match_scenarios(m1, m2, match_type="singles", doubles_format=None)
    durations = {s.scenario.value: s.duration_min for s in scenarios}
    assert durations == {"short": 75, "normal": 120, "long": 180}


# ── Doubles — best_of_3 ───────────────────────────────────────────────────────


def test_doubles_best_of_3_durations():
    """doubles + best_of_3 → 60/90/135 min."""
    m1, m2 = _match_pair(150, "doubles", "best_of_3")
    scenarios = generate_match_scenarios(m1, m2, match_type="doubles", doubles_format="best_of_3")
    durations = {s.scenario.value: s.duration_min for s in scenarios}
    assert durations == {"short": 60, "normal": 90, "long": 135}


def test_doubles_best_of_3_returns_three_scenarios():
    """generate_match_scenarios always returns exactly 3 ScenarioPlan objects."""
    m1, m2 = _match_pair(150, "doubles", "best_of_3")
    scenarios = generate_match_scenarios(m1, m2, match_type="doubles", doubles_format="best_of_3")
    assert len(scenarios) == 3
    kinds = {s.scenario for s in scenarios}
    assert kinds == {ScenarioKind.short, ScenarioKind.normal, ScenarioKind.long}


# ── Doubles — pro_set_8 ───────────────────────────────────────────────────────


def test_doubles_pro_set_8_durations():
    """doubles + pro_set_8 → 45/70/100 min."""
    m1, m2 = _match_pair(150, "doubles", "pro_set_8")
    scenarios = generate_match_scenarios(m1, m2, match_type="doubles", doubles_format="pro_set_8")
    durations = {s.scenario.value: s.duration_min for s in scenarios}
    assert durations == {"short": 45, "normal": 70, "long": 100}


def test_doubles_pro_set_8_returns_three_scenarios():
    m1, m2 = _match_pair(150, "doubles", "pro_set_8")
    scenarios = generate_match_scenarios(m1, m2, match_type="doubles", doubles_format="pro_set_8")
    assert len(scenarios) == 3


# ── Gap arithmetic with doubles durations ────────────────────────────────────


def test_doubles_pro_set_8_gap_arithmetic():
    """Gap arithmetic is correct for pro_set_8 normal duration (70 min).

    DOUBLES_SPEC_V1.md §B.4: with second match at 1 PM (240 min after 9 AM),
    gap for normal scenario = 240 - 70 = 170 min → food=light_meal, pickup=wait_until_end.
    """
    m1 = _match(_BASE)  # 9:00 AM
    m2 = _match(_BASE + timedelta(hours=4))  # 1:00 PM
    scenarios = generate_match_scenarios(m1, m2, match_type="doubles", doubles_format="pro_set_8")
    normal = next(s for s in scenarios if s.scenario == ScenarioKind.normal)
    assert normal.duration_min == 70
    assert normal.gap_minutes == 170  # 240 - 70
    assert normal.gap_status == GapStatus.ok
    assert normal.food_strategy is not None
    assert normal.food_strategy.bucket == FoodBucket.light_meal   # gap >= 150
    assert normal.pickup_strategy.bucket == PickupBucket.wait_until_end  # gap >= 120


def test_doubles_best_of_3_long_scenario_gap():
    """Long scenario (135 min) with zero gap produces tight gap_status.

    m2 starts exactly when the long scenario ends (gap_minutes == 0).
    0 < TIGHT_GAP_THRESHOLD_MIN (30) → gap_status == tight.
    """
    m1 = _match(_BASE)                                         # 9:00 AM
    m2 = _match(_BASE + timedelta(minutes=135))               # 11:15 AM exactly at long end
    scenarios = generate_match_scenarios(m1, m2, match_type="doubles", doubles_format="best_of_3")
    long_s = next(s for s in scenarios if s.scenario == ScenarioKind.long)
    assert long_s.duration_min == 135
    assert long_s.gap_minutes == 0  # m2 starts exactly when long scenario ends
    assert long_s.gap_status == GapStatus.tight  # 0 < TIGHT_GAP_THRESHOLD_MIN=30


# ── Invalid combination → ValueError ─────────────────────────────────────────


def test_invalid_match_type_raises():
    """Unknown match_type raises ValueError."""
    m1 = _match(_BASE)
    with pytest.raises(ValueError, match="Unknown"):
        generate_match_scenarios(m1, None, match_type="team", doubles_format=None)


def test_invalid_doubles_format_raises():
    """doubles + unknown format raises ValueError."""
    m1 = _match(_BASE)
    with pytest.raises(ValueError, match="Unknown"):
        generate_match_scenarios(m1, None, match_type="doubles", doubles_format="bogus")


def test_doubles_none_format_raises():
    """doubles + doubles_format=None raises ValueError (no default for doubles)."""
    m1 = _match(_BASE)
    with pytest.raises(ValueError):
        generate_match_scenarios(m1, None, match_type="doubles", doubles_format=None)


# ── No-next-match with doubles ────────────────────────────────────────────────


def test_doubles_no_next_match():
    """no_next_match branch still works for doubles."""
    m1 = _match(_BASE)
    scenarios = generate_match_scenarios(m1, None, match_type="doubles", doubles_format="best_of_3")
    assert len(scenarios) == 3
    for s in scenarios:
        assert s.gap_status == GapStatus.no_next_match
        assert s.food_strategy is None
