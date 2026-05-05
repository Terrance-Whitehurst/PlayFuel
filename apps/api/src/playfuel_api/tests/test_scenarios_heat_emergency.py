"""Test the heat_emergency_text plumbing in build_plan_envelope (§E.2 / §H.2).

Covers the gap in Task #5 QA report — no test asserted heat_emergency_text is
set when flag_extreme_heat_risk=True, or absent when False.

extreme_heat_risk formula (verified from rules/weather.py):
    flag_extreme_heat_risk = flag_very_hot OR (flag_hot AND flag_humid)
    flag_hot      : temp_c >= 29.4°C  (was 85°F)
    flag_very_hot : temp_c >= 32.2°C  (was 90°F)
    flag_humid    : humidity_pct >= 65

Phase B: all test values converted from °F to °C.

Cases:
    (31.1, 72) → hot AND humid    → extreme_heat_risk=True  → text set  [was 88°F]
    (18.3, 40) → neither          → extreme_heat_risk=False → text None  [was 65°F]
    (31.1, 40) → hot, NOT humid   → extreme_heat_risk=False → text None  [was 88°F boundary]
    (33.3, 30) → very_hot         → extreme_heat_risk=True  → text set  [was 92°F]

Rule: never re-type HEAT_EMERGENCY_TEXT — always import the constant.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from playfuel_api.models.db import MatchRow
from playfuel_api.rules.hard_coded_strings import HEAT_EMERGENCY_TEXT
from playfuel_api.rules.plan import build_plan_envelope
from playfuel_api.rules.scenarios import generate_match_scenarios
from playfuel_api.rules.weather import classify_weather

# ── Helper ────────────────────────────────────────────────────────────────────

_TS = datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)


def _make_scenarios():
    """Minimal match pair with a comfortable gap (normal scenario gap=120 → ok status)."""
    m1 = MatchRow(
        id=uuid4(),
        tournament_id=uuid4(),
        scheduled_start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        created_at=_TS,
        updated_at=_TS,
    )
    m2 = MatchRow(
        id=uuid4(),
        tournament_id=m1.tournament_id,
        scheduled_start=datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc),  # 9AM+4h → gap=120 for normal
        created_at=_TS,
        updated_at=_TS,
    )
    return generate_match_scenarios(m1, m2)


# ── Parametrize table ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("temp_c,humidity_pct,expect_extreme", [
    (31.1, 72.0, True),   # hot AND humid → extreme  [was 88°F]
    (18.3, 40.0, False),  # Cool day: neither flag → not extreme  [was 65°F]
    (31.1, 40.0, False),  # Hot-but-not-humid boundary: hot alone ≠ extreme  [was 88°F]
    (33.3, 30.0, True),   # Very hot alone is sufficient for extreme  [was 92°F]
])
def test_extreme_heat_risk_flag(temp_c, humidity_pct, expect_extreme):
    """classify_weather correctly sets flag_extreme_heat_risk for boundary cases."""
    flags = classify_weather(temp_c, humidity_pct)
    assert flags["flag_extreme_heat_risk"] == expect_extreme, (
        f"temp_c={temp_c}, humidity={humidity_pct}: "
        f"expected flag_extreme_heat_risk={expect_extreme}, "
        f"got {flags['flag_extreme_heat_risk']}"
    )


# ── Heat-emergency-text plumbing tests ────────────────────────────────────────

def test_dallas_heat_plan_has_emergency_text():
    """(31.1°C, 72%) → flag_extreme_heat_risk=True → plan.heat_emergency_text == HEAT_EMERGENCY_TEXT.

    Phase B: 31.1°C was 88°F. hot=True (31.1>=29.4), humid=True (72>=65), extreme=True.
    """
    scenarios = _make_scenarios()
    flags = classify_weather(31.1, 72.0)
    assert flags["flag_extreme_heat_risk"] is True  # precondition

    plan = build_plan_envelope(uuid4(), scenarios, weather_flags=flags)

    assert plan.heat_emergency_text is not None, (
        "Expected heat_emergency_text to be set for extreme heat conditions"
    )
    assert plan.heat_emergency_text == HEAT_EMERGENCY_TEXT, (
        "heat_emergency_text must equal HEAT_EMERGENCY_TEXT constant verbatim (v1.1 wording)"
    )


def test_cool_day_plan_has_no_emergency_text():
    """(18.3°C, 40%) → flag_extreme_heat_risk=False → plan.heat_emergency_text is None.

    Phase B: 18.3°C was 65°F. Below hot threshold (29.4°C) → no heat flags.
    """
    scenarios = _make_scenarios()
    flags = classify_weather(18.3, 40.0)
    assert flags["flag_extreme_heat_risk"] is False  # precondition

    plan = build_plan_envelope(uuid4(), scenarios, weather_flags=flags)

    assert plan.heat_emergency_text is None, (
        "Cool-day plan must NOT include heat_emergency_text"
    )


def test_hot_but_not_humid_plan_has_no_emergency_text():
    """(31.1°C, 40%) → hot only, not extreme → plan.heat_emergency_text is None.

    Phase B: 31.1°C (was 88°F) is hot (>=29.4°C) but 40% humidity < 65% threshold.
    very_hot requires >=32.2°C. So extreme_heat_risk = False.
    """
    scenarios = _make_scenarios()
    flags = classify_weather(31.1, 40.0)
    assert flags["flag_hot"] is True           # hot threshold met (31.1 >= 29.4)
    assert flags["flag_humid"] is False        # humid threshold NOT met (40 < 65)
    assert flags["flag_very_hot"] is False     # very_hot threshold NOT met (31.1 < 32.2)
    assert flags["flag_extreme_heat_risk"] is False  # final assertion

    plan = build_plan_envelope(uuid4(), scenarios, weather_flags=flags)

    assert plan.heat_emergency_text is None, (
        "Hot-but-not-humid plan must NOT trigger heat_emergency_text"
    )


def test_very_hot_plan_has_emergency_text():
    """(33.3°C, 30%) → very_hot alone is sufficient → plan.heat_emergency_text == HEAT_EMERGENCY_TEXT.

    Phase B: 33.3°C was 92°F. very_hot=True (33.3>=32.2) → extreme_heat_risk=True.
    """
    scenarios = _make_scenarios()
    flags = classify_weather(33.3, 30.0)
    assert flags["flag_very_hot"] is True        # precondition (33.3 >= 32.2)
    assert flags["flag_extreme_heat_risk"] is True

    plan = build_plan_envelope(uuid4(), scenarios, weather_flags=flags)

    assert plan.heat_emergency_text == HEAT_EMERGENCY_TEXT


def test_no_weather_flags_plan_has_no_emergency_text():
    """When weather_flags=None, plan.heat_emergency_text must be None."""
    scenarios = _make_scenarios()
    plan = build_plan_envelope(uuid4(), scenarios, weather_flags=None)
    assert plan.heat_emergency_text is None
