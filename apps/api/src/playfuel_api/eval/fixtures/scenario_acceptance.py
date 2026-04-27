"""Canonical SCENARIO_ACCEPTANCE.md cases encoded as (input, expected) fixture records.

Each fixture is a dict with:
    name       str   — human-readable label used in eval output
    match      MatchRow
    next_match MatchRow | None
    weather    dict  — kwargs for classify_weather(); None to skip classification
    xfail      bool  — True means [XFAIL] is emitted and the case doesn't fail the run
    expected   dict  — field-path → expected value assertions the runner checks

Scenario 5 is explicitly marked xfail=True (OQ-F deferred to Phase 4).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import (
    FoodBucket,
    GapStatus,
    PickupBucket,
    ScheduleConfidence,
)

# ── Shared base datetime ──────────────────────────────────────────────────────

_TS = datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)


def _m(hour: int, minute: int = 0, tid=None) -> MatchRow:
    return MatchRow(
        id=uuid4(),
        tournament_id=tid or uuid4(),
        scheduled_start=datetime(2026, 4, 26, hour, minute, tzinfo=timezone.utc),
        created_at=_TS,
        updated_at=_TS,
    )


# ── Scenario 1 — Cool 9 AM / 1 PM ────────────────────────────────────────────
#
# match 9:00, next 13:00, weather 65°F / 40% humidity
# Short (75min, end ~10:15, gap=165) → light_meal, wait_until_end
# Normal (120min, end ~11:00, gap=120) → quick_pickup, wait_until_end  [OQ-13 resolution]
# Long (180min, end ~12:00, gap=60) → portable, pickup_during_match

def _scenario_1():
    m1 = _m(9, 0)
    m2 = _m(13, 0, tid=m1.tournament_id)
    return {
        "name": "Scenario 1 — Cool 9/1 baseline",
        "match": m1,
        "next_match": m2,
        "weather": {"temp_f": 65.0, "humidity_pct": 40.0, "wind_mph": 5.0, "precipitation_probability": 10.0},
        "xfail": False,
        "expected": {
            # short (index 0): gap=165 → light_meal, wait_until_end
            "scenarios[0].gap_minutes": 165,
            "scenarios[0].gap_status": GapStatus.ok,
            "scenarios[0].food_strategy.bucket": FoodBucket.light_meal,
            "scenarios[0].pickup_strategy.bucket": PickupBucket.wait_until_end,
            # normal (index 1): gap=120 → quick_pickup (OQ-13), wait_until_end
            "scenarios[1].gap_minutes": 120,
            "scenarios[1].gap_status": GapStatus.ok,
            "scenarios[1].food_strategy.bucket": FoodBucket.quick_pickup,
            "scenarios[1].pickup_strategy.bucket": PickupBucket.wait_until_end,
            # long (index 2): gap=60 → portable, pickup_during_match
            "scenarios[2].gap_minutes": 60,
            "scenarios[2].gap_status": GapStatus.ok,
            "scenarios[2].food_strategy.bucket": FoodBucket.portable,
            "scenarios[2].pickup_strategy.bucket": PickupBucket.pickup_during_match,
            # plan level — no heat risk
            "plan.heat_emergency_text": None,
            "plan.schedule_confidence": ScheduleConfidence.high,
            "weather.flag_extreme_heat_risk": False,
        },
    }


# ── Scenario 2 — Hot/Humid Dallas 9 AM / 12 PM ───────────────────────────────
#
# match 9:00, next 12:00, weather 88°F / 72% humidity
# Short (75min, gap=105) → quick_pickup, pickup_during_match
# Normal (120min, gap=60) → portable, pickup_during_match
# Long (180min, gap=0) → tight, bag_only, bring_portable

def _scenario_2():
    m1 = _m(9, 0)
    m2 = _m(12, 0, tid=m1.tournament_id)
    return {
        "name": "Scenario 2 — Hot/humid Dallas demo",
        "match": m1,
        "next_match": m2,
        "weather": {"temp_f": 88.0, "humidity_pct": 72.0, "wind_mph": 8.0, "precipitation_probability": 0.0},
        "xfail": False,
        "expected": {
            # short: gap=105
            "scenarios[0].gap_minutes": 105,
            "scenarios[0].gap_status": GapStatus.ok,
            "scenarios[0].food_strategy.bucket": FoodBucket.quick_pickup,
            "scenarios[0].pickup_strategy.bucket": PickupBucket.pickup_during_match,
            # normal: gap=60
            "scenarios[1].gap_minutes": 60,
            "scenarios[1].gap_status": GapStatus.ok,
            "scenarios[1].food_strategy.bucket": FoodBucket.portable,
            "scenarios[1].pickup_strategy.bucket": PickupBucket.pickup_during_match,
            # long: gap=0 → tight (NOT overrun)
            "scenarios[2].gap_minutes": 0,
            "scenarios[2].gap_status": GapStatus.tight,
            "scenarios[2].food_strategy.bucket": FoodBucket.bag_only,
            "scenarios[2].pickup_strategy.bucket": PickupBucket.bring_portable,
            # plan level — extreme heat
            "plan.heat_emergency_text_is_set": True,
            "plan.schedule_confidence": ScheduleConfidence.medium,
            "weather.flag_hot": True,
            "weather.flag_humid": True,
            "weather.flag_extreme_heat_risk": True,
        },
    }


# ── Scenario 3 — Long gap 10 AM / 4 PM ───────────────────────────────────────
#
# match 10:00, next 16:00
# All gaps >= 150 → light_meal, wait_until_end

def _scenario_3():
    m1 = _m(10, 0)
    m2 = _m(16, 0, tid=m1.tournament_id)
    return {
        "name": "Scenario 3 — Long gap",
        "match": m1,
        "next_match": m2,
        "weather": {"temp_f": 72.0, "humidity_pct": 50.0, "wind_mph": 5.0, "precipitation_probability": 0.0},
        "xfail": False,
        "expected": {
            "scenarios[0].gap_minutes": 285,
            "scenarios[0].food_strategy.bucket": FoodBucket.light_meal,
            "scenarios[0].pickup_strategy.bucket": PickupBucket.wait_until_end,
            "scenarios[1].gap_minutes": 240,
            "scenarios[1].food_strategy.bucket": FoodBucket.light_meal,
            "scenarios[1].pickup_strategy.bucket": PickupBucket.wait_until_end,
            "scenarios[2].gap_minutes": 180,
            "scenarios[2].food_strategy.bucket": FoodBucket.light_meal,
            "scenarios[2].pickup_strategy.bucket": PickupBucket.wait_until_end,
            "plan.schedule_confidence": ScheduleConfidence.high,
            "plan.heat_emergency_text": None,
        },
    }


# ── Scenario 4 — Back-to-back 9 AM / 11 AM ───────────────────────────────────
#
# match 9:00, next 11:00
# Short (75min, gap=45) → portable, bring_portable
# Normal (120min, gap=0) → tight, bag_only, bring_portable
# Long (180min, gap=-60) → overrun

def _scenario_4():
    m1 = _m(9, 0)
    m2 = _m(11, 0, tid=m1.tournament_id)
    return {
        "name": "Scenario 4 — Back-to-back",
        "match": m1,
        "next_match": m2,
        "weather": {"temp_f": 72.0, "humidity_pct": 50.0, "wind_mph": 5.0, "precipitation_probability": 0.0},
        "xfail": False,
        "expected": {
            # short: gap=45 → portable (45 ∈ [45,90)), bring_portable (45 < 60)
            "scenarios[0].gap_minutes": 45,
            "scenarios[0].gap_status": GapStatus.ok,
            "scenarios[0].food_strategy.bucket": FoodBucket.portable,
            "scenarios[0].pickup_strategy.bucket": PickupBucket.bring_portable,
            # normal: gap=0 → tight (NOT overrun — Invariant 4)
            "scenarios[1].gap_minutes": 0,
            "scenarios[1].gap_status": GapStatus.tight,
            # long: gap=-60 → overrun
            "scenarios[2].gap_minutes": -60,
            "scenarios[2].gap_status": GapStatus.overrun,
            "scenarios[2].food_strategy.bucket": FoodBucket.bag_only,
            "scenarios[2].pickup_strategy.bucket": PickupBucket.bring_portable,
            "plan.schedule_confidence": ScheduleConfidence.low,
        },
    }


# ── Scenario 5 — Rain delay (OQ-F deferred to Phase 4) ───────────────────────
#
# xfail=True — this case documents the contract only; engine does not implement it.
# The runner emits [XFAIL] and does not count it as a failure.

def _scenario_5():
    m1 = _m(9, 0)
    m2 = _m(13, 0, tid=m1.tournament_id)
    return {
        "name": "Scenario 5 — Rain delay (OQ-F deferred to Phase 4)",
        "match": m1,
        "next_match": m2,
        "weather": {"temp_f": 70.0, "humidity_pct": 60.0, "wind_mph": 5.0, "precipitation_probability": 55.0},
        "xfail": True,  # OQ-F — rain-delay handling deferred to Phase 4
        "expected": {
            # When implemented: rain_risk flag + schedule_confidence=low + rain delay guidance
            "weather.flag_rain_risk": True,
            "plan.schedule_confidence": ScheduleConfidence.low,
        },
    }


# ── Public fixture list ───────────────────────────────────────────────────────

FIXTURES: list[dict] = [
    _scenario_1(),
    _scenario_2(),
    _scenario_3(),
    _scenario_4(),
    _scenario_5(),
]
