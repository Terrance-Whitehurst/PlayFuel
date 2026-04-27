"""Weather flag classification tests — RULES_CONSTANTS_V1.md §E.1 / §E.2.

6 parametrized cases covering primary flags and the derived extreme_heat_risk flag.

§E.2 derived flag rule:
    extreme_heat_risk = very_hot OR (hot AND humid)

Cases:
    1. 65°F / 40% hum   — no weather flags set (all below thresholds)
    2. 88°F / 72% hum   — hot + humid → extreme_heat_risk=True (Scenario 2 canonical)
    3. 92°F / 30% hum   — very_hot alone → extreme_heat_risk=True; humid=False
    4. 88°F / 40% hum   — hot only (humid=False → extreme_heat_risk=False)
    5. 50°F / 50% hum   — cold (temp_f <= 50); hot/very_hot/extreme_heat_risk all False
    6. 70°F / rain=55%  — rain_risk only (precip >= 40%)
"""
import pytest

from playfuel_api.rules.weather import classify_weather


@pytest.mark.parametrize(
    "temp_f, humidity_pct, wind_mph, precip_pct, expected",
    [
        # Case 1 — cool, no flags (Scenario 1 weather)
        (
            65.0, 40.0, 5.0, 10.0,
            {
                "flag_hot": False,
                "flag_very_hot": False,
                "flag_humid": False,
                "flag_cold": False,
                "flag_windy": False,
                "flag_rain_risk": False,
                "flag_extreme_heat_risk": False,
            },
        ),
        # Case 2 — hot + humid → extreme_heat_risk (Scenario 2 canonical)
        # 88°F ≥ 85 → hot; 72% ≥ 65 → humid; extreme = hot AND humid = True.
        # 88°F < 90 → very_hot=False (confirmed in SCENARIO_ACCEPTANCE Scenario 2 Must Not Include).
        (
            88.0, 72.0, 8.0, 0.0,
            {
                "flag_hot": True,
                "flag_very_hot": False,
                "flag_humid": True,
                "flag_cold": False,
                "flag_windy": False,
                "flag_rain_risk": False,
                "flag_extreme_heat_risk": True,  # hot AND humid
            },
        ),
        # Case 3 — very_hot alone triggers extreme_heat_risk (§E.2 OR branch)
        # 92°F ≥ 90 → very_hot=True; sets both hot AND very_hot per §E.1 note.
        (
            92.0, 30.0, 0.0, 0.0,
            {
                "flag_hot": True,   # 92 >= 85
                "flag_very_hot": True,  # 92 >= 90
                "flag_humid": False,
                "flag_cold": False,
                "flag_windy": False,
                "flag_rain_risk": False,
                "flag_extreme_heat_risk": True,  # very_hot alone is sufficient
            },
        ),
        # Case 4 — hot only; humid=False → extreme_heat_risk=False
        (
            88.0, 40.0, 0.0, 0.0,
            {
                "flag_hot": True,
                "flag_very_hot": False,
                "flag_humid": False,
                "flag_cold": False,
                "flag_windy": False,
                "flag_rain_risk": False,
                "flag_extreme_heat_risk": False,  # hot but NOT humid → no extreme
            },
        ),
        # Case 5 — cold boundary (temp_f exactly 50 → cold=True per §E.1 <=)
        (
            50.0, 50.0, 0.0, 0.0,
            {
                "flag_hot": False,
                "flag_very_hot": False,
                "flag_humid": False,
                "flag_cold": True,   # 50 <= 50 → cold
                "flag_windy": False,
                "flag_rain_risk": False,
                "flag_extreme_heat_risk": False,
            },
        ),
        # Case 6 — rain_risk (precipitation_probability=55 >= 40, Scenario 5 weather)
        (
            70.0, 50.0, 5.0, 55.0,
            {
                "flag_hot": False,
                "flag_very_hot": False,
                "flag_humid": False,
                "flag_cold": False,
                "flag_windy": False,
                "flag_rain_risk": True,  # 55 >= 40
                "flag_extreme_heat_risk": False,
            },
        ),
    ],
    ids=[
        "cool_no_flags",
        "hot_and_humid_extreme_heat",
        "very_hot_alone_extreme_heat",
        "hot_only_not_extreme",
        "cold_boundary_50f",
        "rain_risk_55pct",
    ],
)
def test_classify_weather(
    temp_f, humidity_pct, wind_mph, precip_pct, expected
):
    """classify_weather() returns the correct flag dict for each weather case."""
    result = classify_weather(
        temp_f=temp_f,
        humidity_pct=humidity_pct,
        wind_mph=wind_mph,
        precipitation_probability=precip_pct,
    )
    assert result == expected
