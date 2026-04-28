"""Test build_timeline() partnerCoordination event — DOUBLES_SPEC_V1.md §C.1.

build_timeline() emits a partnerCoordination event at T−60m before the
first doubles match ONLY when at least one match in the group has
format == 'doubles'.

Covers:
    1. Singles matches → NO partnerCoordination event
    2. Doubles match → exactly ONE partnerCoordination event
    3. partnerCoordination time == match.scheduled_start − 60 min
    4. partnerCoordination kind == TimelineEventKind.partnerCoordination
    5. Events are sorted chronologically (partnerCoordination precedes match)
    6. Two doubles matches → partnerCoordination fires only once (first match only)
    7. Event title and detail are non-empty strings
    8. match + matchEnd events still emit for doubles (no regression)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import TimelineEventKind
from playfuel_api.rules.plan import build_timeline
from playfuel_api.rules.scenarios import generate_match_scenarios

_BASE = datetime(2026, 6, 14, 9, 0, tzinfo=timezone.utc)  # 9:00 AM anchor


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_match(
    start: datetime,
    format_: str = "singles",
    doubles_format: str | None = None,
    display_order: int = 1,
) -> MatchRow:
    tid = uuid4()
    return MatchRow(
        id=uuid4(),
        tournament_id=tid,
        scheduled_start=start,
        format=format_,
        doubles_format=doubles_format,
        display_order=display_order,
        created_at=start,
        updated_at=start,
    )


def _singles_scenarios(m1: MatchRow, m2: MatchRow | None = None):
    return generate_match_scenarios(m1, m2, match_type="singles", doubles_format=None)


def _doubles_scenarios(m1: MatchRow, m2: MatchRow | None = None, fmt: str = "best_of_3"):
    return generate_match_scenarios(m1, m2, match_type="doubles", doubles_format=fmt)


# ── Test 1: singles → no partnerCoordination ──────────────────────────────────


def test_singles_no_partner_coordination_event():
    """Singles timeline must NOT contain a partnerCoordination event."""
    m1 = _make_match(_BASE, format_="singles")
    scenarios = _singles_scenarios(m1)
    timeline = build_timeline([m1], scenarios)

    kinds = [e.kind for e in timeline]
    assert TimelineEventKind.partnerCoordination not in kinds, (
        f"Expected no partnerCoordination for singles; got {[k.value for k in kinds]}"
    )


# ── Test 2: doubles → exactly one partnerCoordination ─────────────────────────


def test_doubles_has_exactly_one_partner_coordination_event():
    """Doubles timeline must contain exactly ONE partnerCoordination event."""
    m1 = _make_match(_BASE, format_="doubles", doubles_format="best_of_3")
    scenarios = _doubles_scenarios(m1)
    timeline = build_timeline([m1], scenarios)

    pc_events = [e for e in timeline if e.kind == TimelineEventKind.partnerCoordination]
    assert len(pc_events) == 1, (
        f"Expected exactly 1 partnerCoordination event; got {len(pc_events)}"
    )


# ── Test 3: partnerCoordination fires at T−60m ────────────────────────────────


def test_partner_coordination_time_is_t_minus_60():
    """partnerCoordination event time == scheduled_start − 60 min."""
    m1 = _make_match(_BASE, format_="doubles", doubles_format="best_of_3")
    scenarios = _doubles_scenarios(m1)
    timeline = build_timeline([m1], scenarios)

    pc = next(e for e in timeline if e.kind == TimelineEventKind.partnerCoordination)
    expected_time = (_BASE - timedelta(minutes=60)).isoformat()
    assert pc.time == expected_time, (
        f"partnerCoordination time mismatch. Expected {expected_time!r}, got {pc.time!r}"
    )


# ── Test 4: event kind is partnerCoordination enum ───────────────────────────


def test_partner_coordination_event_kind():
    """Event kind must be TimelineEventKind.partnerCoordination (not a string)."""
    m1 = _make_match(_BASE, format_="doubles", doubles_format="pro_set_8")
    scenarios = _doubles_scenarios(m1, fmt="pro_set_8")
    timeline = build_timeline([m1], scenarios)

    pc = next(e for e in timeline if e.kind == TimelineEventKind.partnerCoordination)
    assert pc.kind is TimelineEventKind.partnerCoordination


# ── Test 5: chronological ordering ───────────────────────────────────────────


def test_partner_coordination_precedes_match_event():
    """partnerCoordination (T−60m) must sort before the match start event."""
    m1 = _make_match(_BASE, format_="doubles", doubles_format="best_of_3")
    scenarios = _doubles_scenarios(m1)
    timeline = build_timeline([m1], scenarios)

    times = [e.time for e in timeline]
    pc_idx = next(i for i, e in enumerate(timeline) if e.kind == TimelineEventKind.partnerCoordination)
    match_idx = next(i for i, e in enumerate(timeline) if e.kind == TimelineEventKind.match)

    assert pc_idx < match_idx, (
        f"partnerCoordination (idx {pc_idx}) must come before match (idx {match_idx}). "
        f"Times: {times}"
    )


# ── Test 6: two doubles matches → only one partnerCoordination ───────────────


def test_two_doubles_matches_one_partner_coordination():
    """With two doubles matches, partnerCoordination fires ONLY for the first match."""
    m1 = _make_match(_BASE, format_="doubles", doubles_format="best_of_3", display_order=1)
    m2 = _make_match(
        _BASE + timedelta(hours=4),
        format_="doubles",
        doubles_format="best_of_3",
        display_order=2,
    )
    scenarios = _doubles_scenarios(m1, m2)
    timeline = build_timeline([m1, m2], scenarios)

    pc_events = [e for e in timeline if e.kind == TimelineEventKind.partnerCoordination]
    assert len(pc_events) == 1, (
        f"Expected exactly 1 partnerCoordination; got {len(pc_events)}"
    )
    # The one event should be T−60m before the FIRST match
    expected_time = (_BASE - timedelta(minutes=60)).isoformat()
    assert pc_events[0].time == expected_time


# ── Test 7: non-empty title and detail ───────────────────────────────────────


def test_partner_coordination_event_has_non_empty_title_and_detail():
    """partnerCoordination event must have a non-empty title and detail string."""
    m1 = _make_match(_BASE, format_="doubles", doubles_format="best_of_3")
    scenarios = _doubles_scenarios(m1)
    timeline = build_timeline([m1], scenarios)

    pc = next(e for e in timeline if e.kind == TimelineEventKind.partnerCoordination)
    assert pc.title, "partnerCoordination title must not be empty"
    assert pc.detail, "partnerCoordination detail must not be empty"


# ── Test 8: match + matchEnd events still emitted for doubles ────────────────


def test_doubles_timeline_still_has_match_and_match_end_events():
    """Doubles timeline must still include match and matchEnd events (no regression)."""
    m1 = _make_match(_BASE, format_="doubles", doubles_format="best_of_3")
    m2 = _make_match(
        _BASE + timedelta(hours=4),
        format_="doubles",
        doubles_format="best_of_3",
        display_order=2,
    )
    scenarios = _doubles_scenarios(m1, m2)
    timeline = build_timeline([m1, m2], scenarios)

    kinds = {e.kind for e in timeline}
    assert TimelineEventKind.match in kinds, "match event must still be emitted for doubles"
    assert TimelineEventKind.matchEnd in kinds, "matchEnd event must still be emitted for doubles"
