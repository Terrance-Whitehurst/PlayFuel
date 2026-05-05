"""QA-INTL-C3 — International scenario matrix test.

Parameterized matrix covering three Tier 1 markets:

  Row 1 — CDMX (Mexico City, hot+humid):
      venue_country="MX", temp_c=32.0, humidity_pct=70.0, wind_kmh=5.0
      Expected: flag_hot=True, flag_humid=True, flag_extreme_heat_risk=True
      Emergency: "911" in heat_emergency_text (MX is a 911-country since 2017)

  Row 2 — London (UK, mild+windy):
      venue_country="GB", temp_c=18.0, humidity_pct=60.0, wind_kmh=30.0
      Expected: flag_windy=True, flag_extreme_heat_risk=False
      Emergency: "999" in heat_emergency_text (UK national emergency number)

  Row 3 — Dallas (US, hot+humid baseline):
      venue_country="US", temp_c=32.0, humidity_pct=70.0, wind_kmh=5.0
      Expected: identical flags to CDMX (metric pipeline serves US correctly)
      Emergency: "911" in heat_emergency_text

All weather inputs are metric (Phase B pipeline: °C, km/h).
classify_weather() is called directly — fastest isolation of flag assertions,
no Open-Meteo mocking required (pure function, no I/O).

Threshold reference (Phase B WEATHER_THRESHOLDS in rules/constants.py):
    hot=29.4°C, very_hot=32.2°C, humid=65.0%, cold=10.0°C, windy=24.0 km/h

Flag derivation:
    CDMX/Dallas: 32.0 >= 29.4 → flag_hot=True
                 32.0 < 32.2  → flag_very_hot=False
                 70.0 >= 65.0 → flag_humid=True
                 5.0  < 24.0  → flag_windy=False
                 extreme_heat_risk = False OR (True AND True) = True  ← §E.2 hot+humid branch
    London:      18.0 < 29.4  → flag_hot=False
                 60.0 < 65.0  → flag_humid=False
                 30.0 >= 24.0 → flag_windy=True
                 extreme_heat_risk = False

INTERNATIONAL_TEST_PLAN_V1.md: QA-INTL-C3 ✅ closed (see §-N).
Constraints enforced:
  - No food-bucket country-specific assertions (Phase D polish)
  - No live API calls — pure rules-engine test
  - No Open-Meteo mock needed (classify_weather is pure)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from playfuel_api.rules.hard_coded_strings import heat_emergency_text
from playfuel_api.rules.weather import classify_weather


# ── LLM isolation (belt-and-suspenders, mirrors test_scenarios.py pattern) ───

@pytest.fixture(autouse=True, scope="module")
def _force_template_provider():
    """Ensure LLM_PROVIDER=template for the duration of this module.

    build_plan_envelope() does not call LLM directly, but this guard
    prevents accidental Anthropic calls if a future refactor changes that.
    """
    original = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "template"
    yield
    if original is None:
        os.environ.pop("LLM_PROVIDER", None)
    else:
        os.environ["LLM_PROVIDER"] = original


# ── Parametrize rows ──────────────────────────────────────────────────────────
#
# Shape: (venue_country, temp_c, humidity_pct, wind_kmh, expected_flags, expected_emergency_substr)
#
# expected_emergency_substr: substring that MUST appear in heat_emergency_text(venue_country).
#   MX/US (911 countries): HEAT_EMERGENCY_TEXT unchanged → "911" appears in original text.
#   GB (999):              substitution fires    → "999" replaces "911 (or your local...)"

_MATRIX = [
    pytest.param(
        "MX",           # venue_country
        32.0,           # temp_c
        70.0,           # humidity_pct
        5.0,            # wind_kmh
        {               # expected weather flags
            "flag_hot":               True,
            "flag_very_hot":          False,   # 32.0 < 32.2°C threshold
            "flag_humid":             True,
            "flag_cold":              False,
            "flag_windy":             False,
            "flag_extreme_heat_risk": True,    # hot AND humid branch (§E.2)
        },
        "911",          # expected_emergency_substr
        id="cdmx_hot_humid",
    ),
    pytest.param(
        "GB",           # venue_country
        18.0,           # temp_c
        60.0,           # humidity_pct
        30.0,           # wind_kmh
        {               # expected weather flags
            "flag_hot":               False,
            "flag_very_hot":          False,
            "flag_humid":             False,   # 60.0 < 65.0% threshold
            "flag_cold":              False,
            "flag_windy":             True,    # 30.0 >= 24.0 km/h
            "flag_extreme_heat_risk": False,
        },
        "999",          # expected_emergency_substr
        id="london_mild_windy",
    ),
    pytest.param(
        "US",           # venue_country
        32.0,           # temp_c
        70.0,           # humidity_pct
        5.0,            # wind_kmh
        {               # expected weather flags — identical to CDMX row
            "flag_hot":               True,
            "flag_very_hot":          False,
            "flag_humid":             True,
            "flag_cold":              False,
            "flag_windy":             False,
            "flag_extreme_heat_risk": True,    # confirms metric pipeline serves US correctly
        },
        "911",          # expected_emergency_substr
        id="dallas_hot_humid_baseline",
    ),
]

_PARAMETRIZE = pytest.mark.parametrize(
    "venue_country,temp_c,humidity_pct,wind_kmh,expected_flags,expected_emergency_substr",
    _MATRIX,
)


# ── Test class ────────────────────────────────────────────────────────────────

class TestInternationalScenarioMatrix:
    """QA-INTL-C3 — Three-row international scenario matrix.

    Each row is tested across three independent test methods:
      1. Weather flag assertions (classify_weather direct call)
      2. Emergency text assertions (heat_emergency_text direct call)
      3. Plan envelope wire-up (build_plan_envelope respects venue_country)

    Total: 3 test methods × 3 parametrize rows = 9 test cases.
    """

    @_PARAMETRIZE
    def test_weather_flags_per_locale(
        self,
        venue_country: str,
        temp_c: float,
        humidity_pct: float,
        wind_kmh: float,
        expected_flags: dict[str, bool],
        expected_emergency_substr: str,
    ):
        """classify_weather() produces correct flag set for each international locale.

        Phase B metric pipeline: all inputs in °C and km/h.
        No Open-Meteo mock needed — classify_weather() is a pure function.
        """
        result = classify_weather(
            temp_c=temp_c,
            humidity_pct=humidity_pct,
            wind_kmh=wind_kmh,
        )
        for flag_name, expected_value in expected_flags.items():
            assert result[flag_name] is expected_value, (
                f"[{venue_country}] {flag_name}: expected {expected_value}, "
                f"got {result[flag_name]!r}. "
                f"Inputs: temp_c={temp_c}, humidity_pct={humidity_pct}, "
                f"wind_kmh={wind_kmh}"
            )

    @_PARAMETRIZE
    def test_heat_emergency_text_contains_correct_number(
        self,
        venue_country: str,
        temp_c: float,
        humidity_pct: float,
        wind_kmh: float,
        expected_flags: dict[str, bool],
        expected_emergency_substr: str,
    ):
        """heat_emergency_text(venue_country) contains the country-appropriate number.

        QA-INTL-C3 assertion: "911" in MX/US text; "999" in GB text.
        Core safety warning must be preserved regardless of substitution.
        """
        text = heat_emergency_text(venue_country)
        assert text, (
            f"heat_emergency_text({venue_country!r}) returned empty string"
        )
        assert expected_emergency_substr in text, (
            f"[{venue_country}] expected {expected_emergency_substr!r} in "
            f"heat_emergency_text output.\nGot: {text!r}"
        )
        # Core warning preserved after any substitution.
        assert "stop play and seek medical help" in text, (
            f"[{venue_country}] Core warning text missing from "
            f"heat_emergency_text output.\nGot: {text!r}"
        )

    @_PARAMETRIZE
    def test_plan_envelope_heat_text_respects_venue_country(
        self,
        venue_country: str,
        temp_c: float,
        humidity_pct: float,
        wind_kmh: float,
        expected_flags: dict[str, bool],
        expected_emergency_substr: str,
    ):
        """build_plan_envelope() wires venue_country into plan.heat_emergency_text.

        Phase C-infrastructure assertion: venue_country flows from the tournament
        row through build_plan_envelope() and produces the country-specific
        emergency text in the returned Plan.

        Match schedule used across all rows:
          Match 1: 2026-07-04T15:00Z (09:00 Mexico City local, UTC-6 no DST)
          Match 2: 2026-07-04T19:00Z (13:00 local)
          Normal gap: 120 min → quick_pickup, wait_until_end (unchanged across locales)

        London row (no extreme_heat_risk): asserts plan.heat_emergency_text is None.
        CDMX/Dallas rows: asserts plan.heat_emergency_text contains expected number.
        """
        from playfuel_api.models.db import MatchRow
        from playfuel_api.rules.plan import build_plan_envelope
        from playfuel_api.rules.scenarios import generate_match_scenarios

        flags = classify_weather(
            temp_c=temp_c,
            humidity_pct=humidity_pct,
            wind_kmh=wind_kmh,
        )

        _ts = datetime(2026, 7, 4, 0, 0, tzinfo=timezone.utc)
        tid = uuid4()
        m1 = MatchRow(
            id=uuid4(),
            tournament_id=tid,
            # UTC-6, no DST (Mexico abolished DST 2023 — QA-INTL-2 fix)
            scheduled_start=datetime(2026, 7, 4, 15, 0, tzinfo=timezone.utc),
            created_at=_ts,
            updated_at=_ts,
        )
        m2 = MatchRow(
            id=uuid4(),
            tournament_id=tid,
            scheduled_start=datetime(2026, 7, 4, 19, 0, tzinfo=timezone.utc),
            created_at=_ts,
            updated_at=_ts,
        )
        scenarios = generate_match_scenarios(m1, m2)
        plan = build_plan_envelope(
            tournament_id=tid,
            scenarios=scenarios,
            weather_flags=flags,
            venue_country=venue_country,
        )

        if flags["flag_extreme_heat_risk"]:
            assert plan.heat_emergency_text is not None, (
                f"[{venue_country}] Expected heat_emergency_text in plan "
                f"when flag_extreme_heat_risk=True, got None"
            )
            assert expected_emergency_substr in plan.heat_emergency_text, (
                f"[{venue_country}] Expected {expected_emergency_substr!r} in "
                f"plan.heat_emergency_text.\nGot: {plan.heat_emergency_text!r}"
            )
        else:
            # London row — no heat risk, plan must not attach emergency text.
            assert plan.heat_emergency_text is None, (
                f"[{venue_country}] Expected heat_emergency_text=None "
                f"when flag_extreme_heat_risk=False, "
                f"got: {plan.heat_emergency_text!r}"
            )
