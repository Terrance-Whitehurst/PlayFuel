"""Weather flag classification tests — RULES_CONSTANTS_V1.md §E.1 / §E.2.

Phase B update: classify_weather() signature renamed to temp_c / wind_kmh.
All °F values converted to °C; all mph values converted to km/h.
Threshold table updated to metric in WEATHER_THRESHOLDS (constants.py).

6 parametrized cases covering primary flags and the derived extreme_heat_risk flag.

§E.2 derived flag rule:
    extreme_heat_risk = very_hot OR (hot AND humid)

Cases:
    1. 18.3°C / 40% hum   — no weather flags set (all below thresholds) [was 65°F]
    2. 31.1°C / 72% hum   — hot + humid → extreme_heat_risk=True (Scenario 2 canonical) [was 88°F]
    3. 33.3°C / 30% hum   — very_hot alone → extreme_heat_risk=True; humid=False [was 92°F]
    4. 31.1°C / 40% hum   — hot only (humid=False → extreme_heat_risk=False) [was 88°F]
    5. 10.0°C / 50% hum   — cold (temp_c <= 10.0); hot/very_hot/extreme_heat_risk all False [was 50°F]
    6. 21.1°C / rain=55%  — rain_risk only (precip >= 40%) [was 70°F]
"""
import pytest

from playfuel_api.rules.weather import classify_weather


@pytest.mark.parametrize(
    "temp_c, humidity_pct, wind_kmh, precip_pct, expected",
    [
        # Case 1 — cool, no flags (Scenario 1 weather) [was 65°F / 5 mph]
        (
            18.3, 40.0, 8.0, 10.0,
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
        # 31.1°C >= 29.4 → hot; 72% >= 65 → humid; extreme = hot AND humid = True.
        # 31.1°C < 32.2 → very_hot=False (confirmed in SCENARIO_ACCEPTANCE Scenario 2 Must Not Include).
        # [was 88°F / 8 mph]
        (
            31.1, 72.0, 12.9, 0.0,
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
        # 33.3°C >= 32.2 → very_hot=True; sets both hot AND very_hot per §E.1 note.
        # [was 92°F / 0 mph]
        (
            33.3, 30.0, 0.0, 0.0,
            {
                "flag_hot": True,   # 33.3 >= 29.4
                "flag_very_hot": True,  # 33.3 >= 32.2
                "flag_humid": False,
                "flag_cold": False,
                "flag_windy": False,
                "flag_rain_risk": False,
                "flag_extreme_heat_risk": True,  # very_hot alone is sufficient
            },
        ),
        # Case 4 — hot only; humid=False → extreme_heat_risk=False [was 88°F / 0 mph]
        (
            31.1, 40.0, 0.0, 0.0,
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
        # Case 5 — cold boundary (temp_c exactly 10.0 → cold=True per §E.1 <=)
        # [was 50°F / 0 mph]
        (
            10.0, 50.0, 0.0, 0.0,
            {
                "flag_hot": False,
                "flag_very_hot": False,
                "flag_humid": False,
                "flag_cold": True,   # 10.0 <= 10.0 → cold
                "flag_windy": False,
                "flag_rain_risk": False,
                "flag_extreme_heat_risk": False,
            },
        ),
        # Case 6 — rain_risk (precipitation_probability=55 >= 40, Scenario 5 weather)
        # [was 70°F / 5 mph]
        (
            21.1, 50.0, 8.0, 55.0,
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
        "cold_boundary_10c",
        "rain_risk_55pct",
    ],
)
def test_classify_weather(
    temp_c, humidity_pct, wind_kmh, precip_pct, expected
):
    """classify_weather() returns the correct flag dict for each weather case."""
    result = classify_weather(
        temp_c=temp_c,
        humidity_pct=humidity_pct,
        wind_kmh=wind_kmh,
        precipitation_probability=precip_pct,
    )
    assert result == expected
