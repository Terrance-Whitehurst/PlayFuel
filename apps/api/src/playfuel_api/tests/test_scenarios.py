"""Scenario acceptance tests — SCENARIO_ACCEPTANCE.md + RULES_CONSTANTS_V1.md §B / §G.

5 cases per SCENARIO_ACCEPTANCE.md:
    1. Cool weather · 9 AM / 1 PM — §B.4 canonical demo scenario
    2. Hot & Humid · 9 AM / 12 PM — extreme_heat_risk weather, including gap=0 tight
    3. Long gap · 10 AM / 4 PM   — all three scenarios land in light_meal
    4. Back-to-back · 9 AM / 11 AM — short=portable, normal=tight (gap=0), long=overrun
    5. Rain delay (OQ-F) — xfail; contract documented but not implemented in v1.0.0

Key invariants:
    - gap_status='tight' when gap=0 (NOT overrun) — see Invariant 4 in brief.
    - gap_status='overrun' ONLY when gap < 0.
    - Overrun clamps: food=bag_only, pickup=bring_portable, rewarm_up=None.
    - gap=120 → food=quick_pickup (OQ-13 resolution; not light_meal).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import FoodBucket, GapStatus, PickupBucket, ScenarioKind
from playfuel_api.rules.scenarios import generate_match_scenarios

# ── Helpers ───────────────────────────────────────────────────────────────────

_TS = datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc)  # base date for created_at/updated_at


def _match(hour: int, minute: int = 0, tid=None) -> MatchRow:
    return MatchRow(
        id=uuid4(),
        tournament_id=tid or uuid4(),
        scheduled_start=datetime(2026, 4, 26, hour, minute, tzinfo=timezone.utc),
        created_at=_TS,
        updated_at=_TS,
    )


# ── Scenario 1 — Cool weather · 9 AM / 1 PM ──────────────────────────────────

class TestScenario1_CoolWeather_9am1pm:
    """SCENARIO_ACCEPTANCE.md Scenario 1: canonical demo (§B.4 worked example)."""

    def setup_method(self):
        m1 = _match(9, 0)
        m2 = _match(13, 0, tid=m1.tournament_id)
        self.scenarios = generate_match_scenarios(m1, m2)
        self.short, self.normal, self.long_ = self.scenarios

    def test_three_scenarios_generated(self):
        assert len(self.scenarios) == 3
        assert [s.scenario for s in self.scenarios] == [
            ScenarioKind.short, ScenarioKind.normal, ScenarioKind.long
        ]

    def test_short_gap_165_light_meal_wait(self):
        """Short: duration=75 → end=10:15AM → gap=165 → light_meal, wait_until_end."""
        assert self.short.gap_minutes == 165
        assert self.short.gap_status == GapStatus.ok
        assert self.short.food_strategy.bucket == FoodBucket.light_meal
        assert self.short.pickup_strategy.bucket == PickupBucket.wait_until_end
        assert self.short.rewarm_up is not None  # gap=165 >= 60

    def test_normal_gap_120_quick_pickup_wait(self):
        """Normal: duration=120 → end=11:00AM → gap=120 → quick_pickup (OQ-13), wait_until_end."""
        assert self.normal.gap_minutes == 120
        assert self.normal.gap_status == GapStatus.ok
        # OQ-13 resolution: gap=120 ∈ [90, 150) → quick_pickup (not light_meal)
        assert self.normal.food_strategy.bucket == FoodBucket.quick_pickup
        assert self.normal.pickup_strategy.bucket == PickupBucket.wait_until_end
        assert self.normal.rewarm_up is not None  # gap=120 >= 60

    def test_long_gap_60_portable_pickup_during(self):
        """Long: duration=180 → end=12:00PM → gap=60 → portable, pickup_during_match."""
        assert self.long_.gap_minutes == 60
        assert self.long_.gap_status == GapStatus.ok
        assert self.long_.food_strategy.bucket == FoodBucket.portable
        assert self.long_.pickup_strategy.bucket == PickupBucket.pickup_during_match
        assert self.long_.rewarm_up is not None  # gap=60 >= 60

    def test_no_overrun_warnings(self):
        for s in self.scenarios:
            assert s.overrun_warning is None
            assert s.warnings == []


# ── Scenario 2 — Hot & Humid · 9 AM / 12 PM ──────────────────────────────────

class TestScenario2_HotHumid_9am12pm:
    """SCENARIO_ACCEPTANCE.md Scenario 2: hot+humid, including gap=0 tight."""

    def setup_method(self):
        m1 = _match(9, 0)
        m2 = _match(12, 0, tid=m1.tournament_id)
        self.scenarios = generate_match_scenarios(m1, m2)
        self.short, self.normal, self.long_ = self.scenarios

    def test_short_gap_105_quick_pickup_during(self):
        """Short: duration=75 → end=10:15AM → gap=105 → quick_pickup, pickup_during_match."""
        assert self.short.gap_minutes == 105
        assert self.short.gap_status == GapStatus.ok
        assert self.short.food_strategy.bucket == FoodBucket.quick_pickup
        assert self.short.pickup_strategy.bucket == PickupBucket.pickup_during_match

    def test_normal_gap_60_portable_pickup_during(self):
        """Normal: duration=120 → end=11:00AM → gap=60 → portable, pickup_during_match."""
        assert self.normal.gap_minutes == 60
        assert self.normal.gap_status == GapStatus.ok
        assert self.normal.food_strategy.bucket == FoodBucket.portable
        assert self.normal.pickup_strategy.bucket == PickupBucket.pickup_during_match

    def test_long_gap_0_is_tight_not_overrun(self):
        """Long: duration=180 → end=12:00PM → gap=0 → gap_status=tight (NOT overrun).

        Invariant 4: gap=0 is tight (0 <= 0 < 30). overrun is ONLY gap < 0.
        """
        assert self.long_.gap_minutes == 0
        assert self.long_.gap_status == GapStatus.tight   # NOT overrun
        assert self.long_.overrun_warning is None          # tight ≠ overrun
        assert self.long_.food_strategy.bucket == FoodBucket.bag_only   # 0 < 45
        assert self.long_.pickup_strategy.bucket == PickupBucket.bring_portable  # 0 < 60


# ── Scenario 3 — Long gap · 10 AM / 4 PM ─────────────────────────────────────

class TestScenario3_LongGap_10am4pm:
    """SCENARIO_ACCEPTANCE.md Scenario 3: all gaps >= 150 → light_meal + wait_until_end."""

    def setup_method(self):
        m1 = _match(10, 0)
        m2 = _match(16, 0, tid=m1.tournament_id)
        self.scenarios = generate_match_scenarios(m1, m2)

    def test_all_gaps_are_large(self):
        # short: 360-75=285, normal: 360-120=240, long: 360-180=180
        expected_gaps = [285, 240, 180]
        for s, expected_gap in zip(self.scenarios, expected_gaps):
            assert s.gap_minutes == expected_gap

    def test_all_scenarios_light_meal(self):
        """All gaps ≥ 150 → light_meal bucket."""
        for s in self.scenarios:
            assert s.food_strategy.bucket == FoodBucket.light_meal, (
                f"Expected light_meal for gap={s.gap_minutes}, got {s.food_strategy.bucket}"
            )

    def test_all_scenarios_wait_until_end(self):
        """All gaps ≥ 120 → wait_until_end bucket."""
        for s in self.scenarios:
            assert s.pickup_strategy.bucket == PickupBucket.wait_until_end

    def test_all_scenarios_have_rewarm_up(self):
        """All gaps ≥ 60 → rewarm_up is not None."""
        for s in self.scenarios:
            assert s.rewarm_up is not None


# ── Scenario 4 — Back-to-back · 9 AM / 11 AM ─────────────────────────────────

class TestScenario4_BackToBack_9am11am:
    """SCENARIO_ACCEPTANCE.md Scenario 4: short=portable, normal=tight/gap=0, long=overrun."""

    def setup_method(self):
        m1 = _match(9, 0)
        m2 = _match(11, 0, tid=m1.tournament_id)
        self.scenarios = generate_match_scenarios(m1, m2)
        self.short, self.normal, self.long_ = self.scenarios

    def test_short_gap_45_portable(self):
        """Short: duration=75 → end=10:15AM → gap=45 → portable (boundary: 45 ∈ [45,90))."""
        assert self.short.gap_minutes == 45
        assert self.short.gap_status == GapStatus.ok  # 45 >= 30
        assert self.short.food_strategy.bucket == FoodBucket.portable
        assert self.short.pickup_strategy.bucket == PickupBucket.bring_portable  # 45 < 60
        assert self.short.overrun_warning is None

    def test_normal_gap_0_is_tight(self):
        """Normal: duration=120 → end=11:00AM → gap=0 → tight (NOT overrun).

        Invariant 4: gap=0 → tight. overrun is ONLY gap < 0.
        """
        assert self.normal.gap_minutes == 0
        assert self.normal.gap_status == GapStatus.tight
        assert self.normal.overrun_warning is None
        assert self.normal.food_strategy.bucket == FoodBucket.bag_only
        assert self.normal.rewarm_up is None  # gap=0 < 60

    def test_long_gap_negative_is_overrun(self):
        """Long: duration=180 → end=12:00PM → gap=-60 → overrun (gap < 0)."""
        assert self.long_.gap_minutes == -60
        assert self.long_.gap_status == GapStatus.overrun
        assert self.long_.overrun_warning is not None
        assert self.long_.overrun_warning.code == "MATCH_OVERRUN"
        assert self.long_.overrun_warning.minutes_over == 60
        assert self.long_.food_strategy.bucket == FoodBucket.bag_only  # overrun clamp
        assert self.long_.pickup_strategy.bucket == PickupBucket.bring_portable  # overrun clamp
        assert self.long_.rewarm_up is None  # overrun clamp
        assert "MATCH_OVERRUN" in self.long_.warnings


# ── Scenario 5 — Rain delay (OQ-F, deferred to Phase 4) ─────────────────────

@pytest.mark.xfail(reason="OQ-F deferred to Phase 4")
def test_scenario_5_rain_delay_engine_path():
    """Contract for rain-delay scenario — not implemented in v1.0.0.

    When precipitation_probability >= 40% and next match schedule is uncertain,
    the engine should:
        - Return schedule_confidence='low' in the Plan envelope.
        - Include rain-delay guidance in warnings (e.g. 'RAIN_DELAY_RISK').
        - Treat parent pickup advice as uncertain / flexible.

    Implementation deferred to Phase 4 per OQ-F.
    This test documents the expected behaviour contract only.
    """
    raise NotImplementedError("Rain delay handling (OQ-F) deferred to Phase 4")
