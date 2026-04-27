"""WMO weather_code → WeatherCondition mapping (Open-Meteo).

Mapping is lossy by design: our enum is narrower than WMO's full code list.
Source: https://open-meteo.com/en/docs (WMO weather interpretation codes).

Buckets:
    0, 1        → clear
    2, 3        → cloudy
    45, 48      → cloudy  (fog has no enum value; nearest match)
    51–67       → rain    (drizzle + rain)
    71–77       → snow    (snow fall / showers)
    80–82       → rain    (rain showers)
    85–86       → snow    (snow showers)
    95–99       → storm   (thunderstorm; nearest match in our enum)
    unknown     → clear   (safe default; warning logged)
"""
from __future__ import annotations

import logging

from playfuel_api.models.enums import WeatherCondition

_logger = logging.getLogger(__name__)


def wmo_to_condition(weather_code: int) -> WeatherCondition:
    """Map Open-Meteo WMO code to our WeatherCondition enum.

    Buckets aggressively — fog → cloudy, thunderstorm → storm.
    Unknown codes default to `clear` and emit a warning log.
    """
    if weather_code in (0, 1):
        return WeatherCondition.clear
    if weather_code in (2, 3, 45, 48):
        # fog (45, 48) bucketed to cloudy — our enum has no fog value.
        return WeatherCondition.cloudy
    if 51 <= weather_code <= 67 or 80 <= weather_code <= 82:
        return WeatherCondition.rain
    if (71 <= weather_code <= 77) or (85 <= weather_code <= 86):
        return WeatherCondition.snow
    if 95 <= weather_code <= 99:
        # thunderstorm bucketed to storm — closest enum match.
        return WeatherCondition.storm
    _logger.warning(
        "Unknown WMO weather_code=%d; defaulting to clear", weather_code
    )
    return WeatherCondition.clear
