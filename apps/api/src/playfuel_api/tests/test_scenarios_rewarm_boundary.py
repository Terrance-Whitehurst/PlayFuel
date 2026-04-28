"""Test the rewarm_up gap boundary at gap=59 vs gap=60 (§D.2 / REWARM_UP_MIN_GAP).

Covers the gap in Task #5 QA report — the rewarm_up boundary was never isolated
as a named boundary test.

Rule (verified from rules/constants.py + rules/scenarios.py):
    REWARM_UP_MIN_GAP = 60
    if gap_minutes >= REWARM_UP_MIN_GAP:
        rewarm_up = RewarmUp(start_offset_min=-30, duration_min=20)
    else:
        rewarm_up = None

Uses the *normal* scenario (duration=120 min) so gap arithmetic is clean:
    next_start = match_start + timedelta(minutes=120 + gap_min)

    gap=59: next_start = match_start + 179min → gap=59 → rewarm_up is None
    gap=60: next_start = match_start + 180min → gap=60 → rewarm_up is set

Named tests:
    test_rewarm_at_gap_59_is_null
    test_rewarm_at_gap_60_is_set
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import ScenarioKind
from playfuel_api.rules.constants import (
    REWARM_UP_DURATION_MIN,
    REWARM_UP_MIN_GAP,
    REWARM_UP_OFFSET_MIN,
    SCENARIO_DURATIONS_MIN,
)
from playfuel_api.rules.scenarios import generate_match_scenarios

# ── Constants ─────────────────────────────────────────────────────────────────

_NORMAL_DURATION = SCENARIO_DURATIONS_MIN[("singles", None)]["normal"]  # 120 min — singles defaults
_TS = datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)
_MATCH_START = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


def _match_pair_with_gap(gap_min: int) -> tuple[MatchRow, MatchRow]:
    """Build a match pair where the normal scenario (120min) produces exactly gap_min."""
    tid = uuid4()
    m1 = MatchRow(
        id=uuid4(),
        tournament_id=tid,
        scheduled_start=_MATCH_START,
        created_at=_TS,
        updated_at=_TS,
    )
    m2 = MatchRow(
        id=uuid4(),
        tournament_id=tid,
        scheduled_start=_MATCH_START + timedelta(minutes=_NORMAL_DURATION + gap_min),
        created_at=_TS,
        updated_at=_TS,
    )
    return m1, m2


def _get_normal(scenarios) -> object:
    """Extract the normal ScenarioPlan from the returned list."""
    return next(s for s in scenarios if s.scenario == ScenarioKind.normal)


# ── Boundary tests ────────────────────────────────────────────────────────────

def test_rewarm_at_gap_59_is_null():
    """gap=59 is one below REWARM_UP_MIN_GAP (60) → rewarm_up must be None (§D.2).

    Half-open boundary: rewarm_up applies to [60, ∞). Gap=59 is NOT included.
    """
    m1, m2 = _match_pair_with_gap(59)
    scenarios = generate_match_scenarios(m1, m2)
    normal = _get_normal(scenarios)

    assert normal.gap_minutes == 59, (
        f"Expected gap=59, got {normal.gap_minutes}"
    )
    assert normal.rewarm_up is None, (
        f"gap=59 is below REWARM_UP_MIN_GAP ({REWARM_UP_MIN_GAP}); "
        f"rewarm_up must be None, got {normal.rewarm_up}"
    )


def test_rewarm_at_gap_60_is_set():
    """gap=60 equals REWARM_UP_MIN_GAP exactly → rewarm_up must be set (§D.2).

    Half-open boundary: [60, ∞) → rewarm_up is non-null with canonical offsets.
    """
    m1, m2 = _match_pair_with_gap(60)
    scenarios = generate_match_scenarios(m1, m2)
    normal = _get_normal(scenarios)

    assert normal.gap_minutes == 60, (
        f"Expected gap=60, got {normal.gap_minutes}"
    )
    assert normal.rewarm_up is not None, (
        f"gap=60 meets REWARM_UP_MIN_GAP ({REWARM_UP_MIN_GAP}); "
        f"rewarm_up must be set, got None"
    )
    assert normal.rewarm_up.start_offset_min == REWARM_UP_OFFSET_MIN, (
        f"Expected start_offset_min={REWARM_UP_OFFSET_MIN}, "
        f"got {normal.rewarm_up.start_offset_min}"
    )
    assert normal.rewarm_up.duration_min == REWARM_UP_DURATION_MIN, (
        f"Expected duration_min={REWARM_UP_DURATION_MIN}, "
        f"got {normal.rewarm_up.duration_min}"
    )


def test_rewarm_at_gap_61_is_set():
    """gap=61 (one above boundary) → rewarm_up must also be set — regression guard."""
    m1, m2 = _match_pair_with_gap(61)
    scenarios = generate_match_scenarios(m1, m2)
    normal = _get_normal(scenarios)

    assert normal.gap_minutes == 61
    assert normal.rewarm_up is not None


def test_rewarm_constants_are_unchanged():
    """Sanity check: constants haven't drifted from spec values (§D.2).

    If these fail, a constant was changed without a RULES_CONSTANTS_VERSION bump.
    """
    assert REWARM_UP_MIN_GAP == 60, (
        f"REWARM_UP_MIN_GAP should be 60, got {REWARM_UP_MIN_GAP}"
    )
    assert REWARM_UP_OFFSET_MIN == -30, (
        f"REWARM_UP_OFFSET_MIN should be -30, got {REWARM_UP_OFFSET_MIN}"
    )
    assert REWARM_UP_DURATION_MIN == 20, (
        f"REWARM_UP_DURATION_MIN should be 20, got {REWARM_UP_DURATION_MIN}"
    )
