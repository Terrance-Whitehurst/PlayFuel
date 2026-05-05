"""DR_20 regression net — the unit-flip safety regression.

If WEATHER_THRESHOLDS were recalibrated to metric WITHOUT also flipping
Open-Meteo to celsius (or vice-versa), `flag_extreme_heat_risk` would
silently fail to fire on a genuinely dangerous day, silencing the
EmergencyBanner. These tests assert the metric calibration fires
correctly on real-world dangerous-day numbers.

These tests run AFTER the Phase B atomic flip, so they assert metric
behavior directly. The "unit invariance" claim is enforced by the
DR_20 atomic-merge contract (constants + Open-Meteo unit param flip
must ship in the SAME commit).
"""
import pytest

from playfuel_api.rules.weather import classify_weather


def test_extreme_heat_risk_fires_on_32c_humid_day():
    """A 32°C / 90°F + 68% humidity day MUST fire flag_extreme_heat_risk.

    Mexico City summer afternoon is the canonical Phase B target."""
    result = classify_weather(temp_c=32.2, humidity_pct=68.0, wind_kmh=10.0)
    assert result["flag_very_hot"] is True
    assert result["flag_humid"] is True
    assert result["flag_extreme_heat_risk"] is True


def test_extreme_heat_risk_fires_on_29c_humid_day():
    """29.5°C + 72% humidity → hot AND humid → extreme_heat_risk via §E.2 OR branch."""
    result = classify_weather(temp_c=29.5, humidity_pct=72.0, wind_kmh=5.0)
    assert result["flag_hot"] is True
    assert result["flag_humid"] is True
    assert result["flag_very_hot"] is False
    assert result["flag_extreme_heat_risk"] is True


def test_mild_day_fires_no_heat_flags():
    """20°C / 68°F mild day, 50% humidity — no heat flags fire."""
    result = classify_weather(temp_c=20.0, humidity_pct=50.0, wind_kmh=10.0)
    assert result["flag_hot"] is False
    assert result["flag_very_hot"] is False
    assert result["flag_extreme_heat_risk"] is False


def test_below_threshold_does_not_fire_hot():
    """29.0°C is BELOW the 29.4°C `hot` threshold — flag_hot must be False.

    Boundary regression guard for the threshold itself."""
    result = classify_weather(temp_c=29.0, humidity_pct=80.0, wind_kmh=0.0)
    assert result["flag_hot"] is False
    assert result["flag_humid"] is True
    assert result["flag_extreme_heat_risk"] is False
