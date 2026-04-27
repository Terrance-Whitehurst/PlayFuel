"""Weather flag classification — RULES_CONSTANTS_V1.md §E.

Source of truth: rules/constants.py WEATHER_THRESHOLDS dict.
All logic is pure (no I/O, no LLM). The derived flag extreme_heat_risk
is computed per §E.2: very_hot OR (hot AND humid).

OQ-H (NEW — Engineering3): weather_condition enum may need 'partly_cloudy',
'fog', 'haze' in a future phase. This module is not affected; it classifies
numeric weather data into boolean flags, not WeatherCondition enum values.
"""
from playfuel_api.rules.constants import WEATHER_THRESHOLDS


def classify_weather(
    temp_f: float,
    humidity_pct: float,
    wind_mph: float = 0.0,
    precipitation_probability: float = 0.0,
) -> dict[str, bool]:
    """Classify weather inputs into binary flags per §E.1 + §E.2.

    All intervals are threshold-inclusive (>=) for hot, very_hot, humid,
    windy, rain_risk; and threshold-inclusive (<=) for cold.

    Args:
        temp_f:                   Observed temperature in °F.
        humidity_pct:             Observed relative humidity (0–100).
        wind_mph:                 Wind speed in mph. Defaults to 0.0.
        precipitation_probability: Precipitation probability (0–100). Defaults to 0.0.

    Returns:
        dict with keys:
          flag_hot, flag_very_hot, flag_humid, flag_cold,
          flag_windy, flag_rain_risk, flag_extreme_heat_risk (derived §E.2)
    """
    t = WEATHER_THRESHOLDS

    flag_hot: bool = temp_f >= t["hot"]            # §E.1 — temp_f >= 85
    flag_very_hot: bool = temp_f >= t["very_hot"]  # §E.1 — temp_f >= 90
    flag_humid: bool = humidity_pct >= t["humid"]   # §E.1 — humidity_pct >= 65
    flag_cold: bool = temp_f <= t["cold"]           # §E.1 — temp_f <= 50
    flag_windy: bool = wind_mph >= t["windy"]       # §E.1 — wind_mph >= 15
    flag_rain_risk: bool = precipitation_probability >= t["rain_risk"]  # §E.1 >= 40

    # §E.2: extreme_heat_risk is a derived flag — not a raw sensor threshold.
    # very_hot (>=90°F) alone is sufficient; hot+humid is also dangerous.
    flag_extreme_heat_risk: bool = flag_very_hot or (flag_hot and flag_humid)

    return {
        "flag_hot": flag_hot,
        "flag_very_hot": flag_very_hot,
        "flag_humid": flag_humid,
        "flag_cold": flag_cold,
        "flag_windy": flag_windy,
        "flag_rain_risk": flag_rain_risk,
        "flag_extreme_heat_risk": flag_extreme_heat_risk,
    }
