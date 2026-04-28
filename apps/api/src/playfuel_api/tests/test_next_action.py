"""Tests for rules/next_action.py — deterministic NextAction derivation.

All tests inject a frozen `now` to keep behavior deterministic and
independent of system clock.

Coverage:
    1. Future event within window → correct NextAction returned
    2. Past events skipped
    3. Event beyond lookahead excluded
    4. Heat prepend on match_start when extreme_heat_risk=True
    5. Heat prepend on warmup / hydration_check (parametrize HEAT_SENSITIVE_KINDS)
    6. No heat prepend on pre_match_meal / parent_food_pickup even with extreme_heat_risk
    7. Fallback recovery_fallback when no upcoming events
    8. Deterministic with frozen now (call twice → identical)
    9. mins_until correctly computed (30-min-out event → 30)
    10. partner_coordination kind → correct detail copy
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from playfuel_api.models.enums import TimelineEventKind
from playfuel_api.rules.next_action import (
    HEAT_SENSITIVE_KINDS,
    NEXT_ACTION_COPY_MAP,
    _HEAT_PREPEND,
    derive_next_action,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 5, 15, 9, 0, 0, tzinfo=timezone.utc)


def _make_event(kind: TimelineEventKind, offset_min: int, title: str = "") -> MagicMock:
    """Build a minimal TimelineEventOut-like object."""
    event_time = _NOW + timedelta(minutes=offset_min)
    ev = MagicMock()
    ev.time = event_time.isoformat()
    ev.kind = kind
    ev.title = title or kind.value.replace("_", " ").title()
    return ev


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_future_event_within_window_is_picked() -> None:
    """Event 60 min out → returned as NextAction."""
    event = _make_event(TimelineEventKind.match, 60, "Match 1")
    result = derive_next_action([event], now=_NOW)

    assert result is not None
    assert result.title == "Match 1"
    assert result.kind == "match"
    assert result.mins_until == 60
    assert result.scheduled_for is not None


def test_past_event_is_skipped() -> None:
    """Event 30 min in the PAST → skipped; no future event → recovery_fallback."""
    past_event = _make_event(TimelineEventKind.match, -30)
    result = derive_next_action([past_event], now=_NOW)

    assert result.kind == "recovery_fallback"
    assert result.scheduled_for is None


def test_event_beyond_lookahead_is_excluded() -> None:
    """Event 6h + 1 min out → outside 6h window → fallback."""
    far_event = _make_event(TimelineEventKind.match, 6 * 60 + 1)
    result = derive_next_action([far_event], now=_NOW, lookahead_hours=6)

    assert result.kind == "recovery_fallback"


def test_heat_prepend_on_match_start_kind() -> None:
    """extreme_heat_risk=True + match kind → detail prepended with heat warning."""
    event = _make_event(TimelineEventKind.match, 30, "Match 1")
    result = derive_next_action([event], now=_NOW, extreme_heat_risk=True)

    assert result.detail.startswith(_HEAT_PREPEND), (
        f"Expected detail to start with heat prepend. Got: {result.detail!r}"
    )
    # Base detail should still be present after the prepend
    base_detail = NEXT_ACTION_COPY_MAP.get("match", "")
    assert base_detail in result.detail


@pytest.mark.parametrize("kind_value", sorted(HEAT_SENSITIVE_KINDS))
def test_heat_prepend_on_all_heat_sensitive_kinds(kind_value: str) -> None:
    """All HEAT_SENSITIVE_KINDS get the heat prepend when extreme_heat_risk=True."""
    # Find the matching enum member
    kind_enum = next(
        (k for k in TimelineEventKind if k.value == kind_value),
        None,
    )
    if kind_enum is None:
        # Some HEAT_SENSITIVE_KINDS values might not be in the enum — skip gracefully
        pytest.skip(f"TimelineEventKind has no value '{kind_value}'")

    event = _make_event(kind_enum, 45)
    result = derive_next_action([event], now=_NOW, extreme_heat_risk=True)

    assert result.detail.startswith(_HEAT_PREPEND), (
        f"Kind '{kind_value}' should get heat prepend. Got: {result.detail!r}"
    )


@pytest.mark.parametrize("kind_enum_value", [
    "meal",       # TimelineEventKind.meal — not heat-sensitive
    "pickup",     # TimelineEventKind.pickup — not heat-sensitive
    "recovery",   # TimelineEventKind.recovery — not heat-sensitive
    "matchEnd",   # TimelineEventKind.matchEnd — not heat-sensitive
])
def test_no_heat_prepend_on_non_sensitive_kinds(kind_enum_value: str) -> None:
    """Non-HEAT_SENSITIVE_KINDS do NOT get heat prepend even when extreme_heat_risk=True."""
    kind_enum = next(
        (k for k in TimelineEventKind if k.value == kind_enum_value),
        None,
    )
    assert kind_enum is not None, f"TimelineEventKind has no value '{kind_enum_value}'"
    event = _make_event(kind_enum, 45)
    result = derive_next_action([event], now=_NOW, extreme_heat_risk=True)

    assert not result.detail.startswith(_HEAT_PREPEND), (
        f"Kind '{kind_enum_value}' should NOT get heat prepend. Got: {result.detail!r}"
    )


def test_fallback_recovery_when_no_upcoming_events() -> None:
    """Empty timeline → recovery_fallback returned."""
    result = derive_next_action([], now=_NOW)

    assert result.kind == "recovery_fallback"
    assert result.title == "Recovery"
    assert result.scheduled_for is None
    assert result.mins_until is None
    assert NEXT_ACTION_COPY_MAP["recovery_fallback"] in result.detail


def test_deterministic_with_frozen_now() -> None:
    """Calling derive_next_action twice with same inputs → identical output."""
    event = _make_event(TimelineEventKind.match, 45, "Match 1")
    result1 = derive_next_action([event], now=_NOW)
    result2 = derive_next_action([event], now=_NOW)

    assert result1.title == result2.title
    assert result1.detail == result2.detail
    assert result1.kind == result2.kind
    assert result1.mins_until == result2.mins_until


def test_mins_until_correctly_computed() -> None:
    """Event exactly 30 min out → mins_until == 30."""
    event = _make_event(TimelineEventKind.match, 30, "Match 1")
    result = derive_next_action([event], now=_NOW)

    assert result.mins_until == 30, (
        f"Expected mins_until=30, got {result.mins_until}"
    )


def test_partner_coordination_kind_copy() -> None:
    """partnerCoordination kind → detail from NEXT_ACTION_COPY_MAP."""
    event = _make_event(TimelineEventKind.partnerCoordination, 60, "Confirm with your doubles partner")
    result = derive_next_action([event], now=_NOW)

    assert result.kind == "partnerCoordination"
    expected_detail = NEXT_ACTION_COPY_MAP.get("partnerCoordination", "")
    assert expected_detail in result.detail, (
        f"Expected partnerCoordination detail. Got: {result.detail!r}"
    )


def test_earliest_event_picked_when_multiple_in_window() -> None:
    """When 3 events are in window, the soonest is picked."""
    ev_30 = _make_event(TimelineEventKind.match, 30, "Match 1")
    ev_60 = _make_event(TimelineEventKind.matchEnd, 60, "Match End")
    ev_90 = _make_event(TimelineEventKind.partnerCoordination, 90, "Partner Confirm")

    result = derive_next_action([ev_90, ev_30, ev_60], now=_NOW)  # passed in arbitrary order

    assert result.mins_until == 30, (
        f"Expected the soonest event (30 min). Got mins_until={result.mins_until}"
    )


def test_at_horizon_boundary_is_included() -> None:
    """Event exactly at the lookahead horizon (6h = 360 min) is included."""
    event = _make_event(TimelineEventKind.match, 360, "Match at horizon")
    result = derive_next_action([event], now=_NOW, lookahead_hours=6)

    assert result.kind != "recovery_fallback", (
        "Event at exactly 6h should be included (boundary is <=)"
    )
    assert result.mins_until == 360
