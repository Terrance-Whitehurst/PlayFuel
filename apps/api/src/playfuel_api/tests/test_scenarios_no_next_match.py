"""Test the no_next_match branch (§G.5) of generate_match_scenarios.

Covers the gap in Task #5 QA report — no test exercised the next_match=None
code path. Every generated ScenarioPlan should carry gap_status=no_next_match
and have food/pickup/rewarm all clamped to None per §G.5.

Named tests:
    test_no_next_match_all_scenarios_have_no_next_match_status
    test_no_next_match_clamps_food_and_pickup_to_none
    test_no_next_match_drives_low_schedule_confidence
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from playfuel_api.models.enums import GapStatus, ScheduleConfidence, ScenarioKind
from playfuel_api.models.db import MatchRow
from playfuel_api.rules.scenarios import generate_match_scenarios
from playfuel_api.rules.plan import derive_schedule_confidence

# ── Fixtures ──────────────────────────────────────────────────────────────────

_TS = datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)

_PICKUP_TEXT_NO_NEXT = (
    "No next match provided. Parent can wait until match ends."
)


def _match() -> MatchRow:
    return MatchRow(
        id=uuid4(),
        tournament_id=uuid4(),
        scheduled_start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        created_at=_TS,
        updated_at=_TS,
    )


# ── Shared result ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def no_next_match_scenarios():
    return generate_match_scenarios(_match(), next_match=None)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_no_next_match_all_scenarios_have_no_next_match_status(no_next_match_scenarios):
    """All 3 ScenarioPlans must carry gap_status == GapStatus.no_next_match (§G.5)."""
    assert len(no_next_match_scenarios) == 3
    for sp in no_next_match_scenarios:
        assert sp.gap_status == GapStatus.no_next_match, (
            f"Expected no_next_match, got {sp.gap_status} for scenario {sp.scenario}"
        )


def test_no_next_match_scenario_kinds_are_short_normal_long(no_next_match_scenarios):
    """Returned list must still be [short, normal, long] in ScenarioKind order."""
    assert [sp.scenario for sp in no_next_match_scenarios] == [
        ScenarioKind.short,
        ScenarioKind.normal,
        ScenarioKind.long,
    ]


def test_no_next_match_clamps_food_and_pickup_to_none(no_next_match_scenarios):
    """§G.5: food_strategy, pickup_strategy.bucket, and rewarm_up must all be None."""
    for sp in no_next_match_scenarios:
        # food_strategy itself is None — no food bucket assigned
        assert sp.food_strategy is None, (
            f"Expected food_strategy=None for scenario {sp.scenario}"
        )
        # pickup_strategy exists but its bucket is None
        assert sp.pickup_strategy is not None
        assert sp.pickup_strategy.bucket is None, (
            f"Expected pickup_strategy.bucket=None for scenario {sp.scenario}"
        )
        # verbatim pickup text per §G.5
        assert sp.pickup_strategy.text == _PICKUP_TEXT_NO_NEXT, (
            f"pickup_strategy.text mismatch for scenario {sp.scenario}"
        )
        # rewarm_up is suppressed — no warm-up timing when no next match
        assert sp.rewarm_up is None, (
            f"Expected rewarm_up=None for scenario {sp.scenario}"
        )


def test_no_next_match_gap_minutes_is_none(no_next_match_scenarios):
    """§G.5: gap_minutes must be None (no arithmetic possible without next_match)."""
    for sp in no_next_match_scenarios:
        assert sp.gap_minutes is None, (
            f"Expected gap_minutes=None for scenario {sp.scenario}"
        )


def test_no_next_match_no_overrun_warning(no_next_match_scenarios):
    """§G.5: no overrun_warning and empty warnings list — no_next_match is not an error."""
    for sp in no_next_match_scenarios:
        assert sp.overrun_warning is None
        assert sp.warnings == []


def test_no_next_match_drives_low_schedule_confidence(no_next_match_scenarios):
    """no_next_match in gap_status set → derive_schedule_confidence returns low.

    Rule: low if any gap_status in {overrun, no_next_match}.
    """
    confidence = derive_schedule_confidence(no_next_match_scenarios)
    assert confidence == ScheduleConfidence.low, (
        f"Expected low schedule confidence, got {confidence}"
    )
