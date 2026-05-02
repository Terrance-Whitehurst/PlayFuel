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

Full-pipeline classes (TestScenario*_FullPipeline):
    Each calls classify_weather() + generate_match_scenarios() + build_plan_envelope()
    — the same three-step pipeline the route uses minus the LLM step.
    LLM is never reached here (build_plan_envelope is rules-engine only; llm_summary stays
    None). The module-scoped `_force_template_provider` autouse fixture also sets
    LLM_PROVIDER=template in os.environ so no LLM provider auto-selects if it somehow fires.

Ref: .pi/multi-team/expertise/SCENARIO_ACCEPTANCE.md
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import FoodBucket, GapStatus, PickupBucket, ScenarioKind, ScheduleConfidence
from playfuel_api.rules.hard_coded_strings import HEAT_EMERGENCY_TEXT
from playfuel_api.rules.plan import build_plan_envelope, derive_schedule_confidence
from playfuel_api.rules.scenarios import generate_match_scenarios
from playfuel_api.rules.weather import classify_weather

# ── LLM isolation fixture ────────────────────────────────────────────────────
# Force LLM_PROVIDER=template in os.environ for the entire test module.
# build_plan_envelope() never calls the LLM directly, so this is belt-and-suspenders,
# but it satisfies the eval-harness AC: no Anthropic calls during pytest -k scenario.


@pytest.fixture(autouse=True, scope="module")
def _force_template_provider():
    """Set LLM_PROVIDER=template for the duration of this module's tests.

    Ensures Anthropic provider never auto-selects if a future refactor causes the
    rules layer to reach the LLM factory. Unset after the module completes.
    """
    original = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "template"
    yield
    if original is None:
        os.environ.pop("LLM_PROVIDER", None)
    else:
        os.environ["LLM_PROVIDER"] = original


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


# ── Scenario 5 — Rain delay (OQ-F) ──────────────────────────────────────────
# The weather flag (`flag_rain_risk`) IS implemented (Phase 4 classify_weather).
# The plan-body rain-delay guidance (RAIN_DELAY_RISK warning, flexible pickup prose)
# is NOT yet implemented — schedule_confidence is driven by gap_status, not weather flags.
# So the full Scenario 5 contract remains xfail.


def test_scenario_5_rain_risk_flag_is_classified():
    """SCENARIO_ACCEPTANCE.md Scenario 5: flag_rain_risk IS implemented in classify_weather.

    precipitation_probability=55% ≥ 40% threshold → flag_rain_risk=True.
    This specific invariant is verifiable even though the full rain-delay guidance
    in the plan body is not yet implemented (see xfail test below).

    Ref: SCENARIO_ACCEPTANCE.md §Scenario 5 — Must Include (first bullet).
    """
    flags = classify_weather(
        temp_f=70.0,
        humidity_pct=60.0,
        wind_mph=5.0,
        precipitation_probability=55.0,
    )
    assert flags["flag_rain_risk"] is True, (
        "precipitation_probability=55% must set flag_rain_risk=True (threshold >= 40%)"
    )
    # Sanity: 70°F → not hot, not cold, not extreme
    assert flags["flag_hot"] is False
    assert flags["flag_extreme_heat_risk"] is False


@pytest.mark.xfail(
    reason=(
        "OQ-F: rain-delay guidance in plan body not implemented. "
        "classify_weather sets flag_rain_risk=True (tested separately), but "
        "build_plan_envelope does not yet emit RAIN_DELAY_RISK warnings or "
        "set schedule_confidence=low from rain risk alone (requires gap overrun/no_next_match)."
    )
)
def test_scenario_5_rain_delay_engine_path():
    """Contract for rain-delay scenario plan body — not implemented in v1.0.0.

    SCENARIO_ACCEPTANCE.md Scenario 5 — Must Include (full contract):
        - schedule_confidence='low' when rain_delay_risk is active.
        - RAIN_DELAY_RISK warning in plan.warnings.
        - Flexible pickup prose: 'keep food flexible and have extra snacks available.'

    Ref: SCENARIO_ACCEPTANCE.md §Scenario 5 — Must Include.
    """
    raise NotImplementedError(
        "Rain delay guidance in plan body (OQ-F) not yet implemented. "
        "schedule_confidence=low requires overrun/no_next_match gap_status, not flag_rain_risk."
    )


# ── Scenario 1 — Full Pipeline ────────────────────────────────────────────────


class TestScenario1_FullPipeline:
    """SCENARIO_ACCEPTANCE.md Scenario 1: full plan pipeline — cool weather 9 AM / 1 PM.

    Calls classify_weather() + generate_match_scenarios() + build_plan_envelope().
    LLM is NOT called (rules-engine path only; _force_template_provider fixture also guards).
    Ref: SCENARIO_ACCEPTANCE.md §Scenario 1 — Must Include / Must Not Include.
    """

    def setup_method(self):
        m1 = _match(9, 0)
        m2 = _match(13, 0, tid=m1.tournament_id)
        scenarios = generate_match_scenarios(m1, m2)
        self.weather = classify_weather(
            temp_f=65.0, humidity_pct=40.0, wind_mph=5.0, precipitation_probability=10.0
        )
        self.plan = build_plan_envelope(m1.tournament_id, scenarios, weather_flags=self.weather)

    def test_cool_weather_flags_not_set(self):
        """§Scenario 1 Must Not Include: no hot, humid, or extreme_heat_risk flags.

        65°F is below hot threshold (85°F); 40% humidity below humid threshold (65%).
        """
        assert self.weather["flag_hot"] is False
        assert self.weather["flag_humid"] is False
        assert self.weather["flag_extreme_heat_risk"] is False
        assert self.weather["flag_rain_risk"] is False  # 10% < 40%

    def test_plan_has_no_heat_emergency_text(self):
        """§Scenario 1 Must Not Include: heat_emergency_text is None (no extreme heat)."""
        assert self.plan.heat_emergency_text is None

    def test_plan_schedule_confidence_is_high(self):
        """§Scenario 1 Must Include: schedule_confidence == high.

        All gaps are ok status (165, 120, 60) — no overrun, no tight, no no_next_match.
        """
        assert self.plan.schedule_confidence == ScheduleConfidence.high

    def test_plan_has_no_overrun_warnings(self):
        """§Scenario 1 Must Not Include: no MATCH_OVERRUN warning in plan."""
        assert "MATCH_OVERRUN" not in self.plan.warnings

    def test_llm_summary_is_none(self):
        """Eval harness: LLM is never called from the rules engine path.

        build_plan_envelope() does not invoke the LLM provider. llm_summary
        must be None to confirm no Anthropic calls occurred.
        """
        assert self.plan.llm_summary is None


# ── Scenario 2 — Full Pipeline ────────────────────────────────────────────────


class TestScenario2_FullPipeline:
    """SCENARIO_ACCEPTANCE.md Scenario 2: full plan pipeline — hot/humid Dallas 88°F.

    Calls classify_weather() + generate_match_scenarios() + build_plan_envelope().
    LLM is NOT called (rules-engine path only).
    Ref: SCENARIO_ACCEPTANCE.md §Scenario 2 — Must Include / Must Not Include.
    """

    def setup_method(self):
        m1 = _match(9, 0)
        m2 = _match(12, 0, tid=m1.tournament_id)
        scenarios = generate_match_scenarios(m1, m2)
        self.weather = classify_weather(
            temp_f=88.0, humidity_pct=72.0, wind_mph=8.0, precipitation_probability=0.0
        )
        self.plan = build_plan_envelope(m1.tournament_id, scenarios, weather_flags=self.weather)

    def test_hot_and_humid_flags_set(self):
        """§Scenario 2 Must Include: flag_hot and flag_humid both True at 88°F / 72%.

        88°F ≥ 85°F hot threshold; 72% ≥ 65% humid threshold.
        extreme_heat_risk = flag_hot AND flag_humid → True.
        """
        assert self.weather["flag_hot"] is True
        assert self.weather["flag_humid"] is True
        assert self.weather["flag_extreme_heat_risk"] is True

    def test_not_very_hot(self):
        """§Scenario 2 Must Not Include: very_hot flag NOT set (88°F < 90°F threshold)."""
        assert self.weather["flag_very_hot"] is False

    def test_plan_has_heat_emergency_text(self):
        """§Scenario 2 Must Include: heat_emergency_text is set when extreme_heat_risk=True.

        HEAT_EMERGENCY_TEXT verbatim constant — no paraphrase, no truncation.
        """
        assert self.plan.heat_emergency_text is not None
        assert self.plan.heat_emergency_text == HEAT_EMERGENCY_TEXT

    def test_plan_schedule_confidence_is_medium(self):
        """§Scenario 2: schedule_confidence == medium.

        Long scenario gap=0 → gap_status=tight (NOT overrun). No overrun exists,
        so confidence = medium (not low). derive_schedule_confidence: tight → medium.
        """
        assert self.plan.schedule_confidence == ScheduleConfidence.medium

    def test_llm_summary_is_none(self):
        """Eval harness: LLM is never called from the rules engine path."""
        assert self.plan.llm_summary is None


# ── Scenario 3 — Full Pipeline ────────────────────────────────────────────────


class TestScenario3_FullPipeline:
    """SCENARIO_ACCEPTANCE.md Scenario 3: full plan pipeline — long gap 10 AM / 4 PM.

    Calls classify_weather() + generate_match_scenarios() + build_plan_envelope().
    LLM is NOT called (rules-engine path only).
    Ref: SCENARIO_ACCEPTANCE.md §Scenario 3 — Must Include / Must Not Include.
    """

    def setup_method(self):
        m1 = _match(10, 0)
        m2 = _match(16, 0, tid=m1.tournament_id)
        self.scenarios = generate_match_scenarios(m1, m2)
        self.weather = classify_weather(
            temp_f=72.0, humidity_pct=50.0, wind_mph=5.0, precipitation_probability=0.0
        )
        self.plan = build_plan_envelope(m1.tournament_id, self.scenarios, weather_flags=self.weather)

    def test_plan_schedule_confidence_is_high(self):
        """§Scenario 3: schedule_confidence == high.

        All gaps ≥ 180 → gap_status=ok for all scenarios. No tight or overrun.
        """
        assert self.plan.schedule_confidence == ScheduleConfidence.high

    def test_neutral_weather_no_heat_flags(self):
        """§Scenario 3 Must Not Include: neutral weather → no heat or rain flags.

        72°F is below hot threshold (85°F); 50% humidity below humid (65%);
        0% precipitation below rain_risk (40%).
        """
        assert self.weather["flag_hot"] is False
        assert self.weather["flag_rain_risk"] is False
        assert self.weather["flag_extreme_heat_risk"] is False

    def test_plan_no_heat_emergency_text(self):
        """§Scenario 3 Must Not Include: neutral weather → heat_emergency_text is None."""
        assert self.plan.heat_emergency_text is None

    def test_plan_no_overrun_warnings(self):
        """§Scenario 3 Must Not Include: no urgent warnings (all gaps ≥ 150 min)."""
        assert self.plan.warnings == []
        assert "MATCH_OVERRUN" not in self.plan.warnings

    def test_all_scenarios_have_rewarm_up(self):
        """§Scenario 3 Must Include: re-warm-up timing specified (all gaps ≥ 60 min).

        Long scenario gap=180 (≥ REWARM_UP_MIN_GAP=60) → rewarm_up set for all three.
        """
        for s in self.scenarios:
            assert s.rewarm_up is not None, (
                f"Expected rewarm_up set for scenario {s.scenario} (gap={s.gap_minutes})"
            )


# ── Scenario 4 — Full Pipeline ────────────────────────────────────────────────


class TestScenario4_FullPipeline:
    """SCENARIO_ACCEPTANCE.md Scenario 4: full plan pipeline — back-to-back 9 AM / 11 AM.

    Calls classify_weather() + generate_match_scenarios() + build_plan_envelope().
    LLM is NOT called (rules-engine path only).
    Ref: SCENARIO_ACCEPTANCE.md §Scenario 4 — Must Include / Must Not Include.
    """

    def setup_method(self):
        m1 = _match(9, 0)
        m2 = _match(11, 0, tid=m1.tournament_id)
        scenarios = generate_match_scenarios(m1, m2)
        self.weather = classify_weather(
            temp_f=72.0, humidity_pct=50.0, wind_mph=5.0, precipitation_probability=0.0
        )
        self.plan = build_plan_envelope(m1.tournament_id, scenarios, weather_flags=self.weather)

    def test_plan_schedule_confidence_is_low(self):
        """§Scenario 4: schedule_confidence == low.

        Long scenario gap=-60 → gap_status=overrun. derive_schedule_confidence:
        overrun in status set → low.
        """
        assert self.plan.schedule_confidence == ScheduleConfidence.low

    def test_overrun_warning_in_plan_warnings(self):
        """§Scenario 4 Must Include: MATCH_OVERRUN warning bubbles to plan-level warnings.

        build_plan_envelope de-duplicates and aggregates scenario.warnings.
        The long scenario's overrun_warning should surface here.
        """
        assert "MATCH_OVERRUN" in self.plan.warnings

    def test_no_heat_emergency_text(self):
        """§Scenario 4: neutral weather → no heat_emergency_text."""
        assert self.plan.heat_emergency_text is None

    def test_llm_summary_is_none(self):
        """Eval harness: LLM is never called from the rules engine path."""
        assert self.plan.llm_summary is None
