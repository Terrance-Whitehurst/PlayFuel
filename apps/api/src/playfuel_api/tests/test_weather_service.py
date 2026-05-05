"""Weather provider integration tests — Open-Meteo + cache.

Requires pytest-asyncio (see pyproject.toml [project.optional-dependencies].dev).
All Supabase and httpx calls are mocked; no network access in CI.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from playfuel_api.models.enums import WeatherCondition
from playfuel_api.weather.codes import wmo_to_condition
from playfuel_api.weather.service import WeatherService


# ─── codes.py — WMO mapping ──────────────────────────────────────────────────


@pytest.mark.parametrize("code,expected", [
    (0, WeatherCondition.clear),
    (1, WeatherCondition.clear),
    (2, WeatherCondition.cloudy),
    (3, WeatherCondition.cloudy),
    (45, WeatherCondition.cloudy),   # fog → cloudy (lossy; documented in codes.py)
    (48, WeatherCondition.cloudy),   # fog → cloudy
    (51, WeatherCondition.rain),
    (65, WeatherCondition.rain),
    (80, WeatherCondition.rain),
    (82, WeatherCondition.rain),
    (71, WeatherCondition.snow),
    (86, WeatherCondition.snow),
    (95, WeatherCondition.storm),    # thunderstorm → storm (lossy)
    (99, WeatherCondition.storm),
    (-1, WeatherCondition.clear),    # unknown → clear default
    (12345, WeatherCondition.clear), # unknown → clear default
])
def test_wmo_to_condition(code, expected):
    assert wmo_to_condition(code) == expected


# ─── service.py — HTTP fetch ─────────────────────────────────────────────────


def _make_open_meteo_payload(
    temp_f: float = 88.0,
    humidity: int = 72,
    code: int = 0,
    wind_mph: float = 8.5,
    precip: int = 10,
) -> dict:
    return {
        "current": {
            "time": "2026-04-27T12:00",
            "temperature_2m": temp_f,
            "relative_humidity_2m": humidity,
            "weather_code": code,
            "wind_speed_10m": wind_mph,
            "precipitation_probability": precip,
        }
    }


@pytest.mark.asyncio
async def test_fetch_current_returns_payload():
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value=_make_open_meteo_payload())
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    svc = WeatherService(
        base_url="https://api.open-meteo.com",
        http_client=mock_client,
    )
    payload = await svc.fetch_current(32.78, -96.80)

    assert payload["current"]["temperature_2m"] == 88.0
    mock_client.get.assert_awaited_once()

    # Verify the URL and params include required fields.
    call_args = mock_client.get.call_args
    assert "/v1/forecast" in call_args.args[0]
    params = call_args.kwargs.get("params", {})
    assert params["temperature_unit"] == "celsius"
    assert "temperature_2m" in params["current"]


@pytest.mark.asyncio
async def test_fetch_current_raises_on_http_error():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "500 Server Error",
            request=MagicMock(),
            response=MagicMock(),
        )
    )
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    svc = WeatherService(
        base_url="https://api.open-meteo.com",
        http_client=mock_client,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await svc.fetch_current(32.78, -96.80)


# ─── cache.py — read-through cache ───────────────────────────────────────────


def _make_snapshot_dict(age_seconds: int, tournament_id: str | None = None) -> dict:
    """Build a minimal dict that WeatherSnapshotRow can deserialise."""
    now = datetime.now(tz=timezone.utc)
    fetched_at = now - timedelta(seconds=age_seconds)
    return {
        "id": str(uuid4()),
        "tournament_id": tournament_id or str(uuid4()),
        "temp_f": 88.0,
        "humidity_pct": 72.0,
        "wind_mph": 8.5,
        "precipitation_probability": 10.0,
        "condition": "clear",
        "flag_hot": True,
        "flag_very_hot": False,
        "flag_humid": True,
        "flag_cold": False,
        "flag_windy": False,
        "flag_rain_risk": False,
        "flag_extreme_heat_risk": True,
        "fetched_at": fetched_at.isoformat(),
        "provider": "open-meteo",
        "created_at": fetched_at.isoformat(),
        "updated_at": fetched_at.isoformat(),
    }


def _mock_supabase_client(
    select_data: list | None = None,
    insert_data: dict | None = None,
) -> MagicMock:
    """Build a mock Supabase client.

    select_data: rows returned by .select(...).execute()
    insert_data: row returned by .insert(...).execute() (single dict, or None)
    """
    # select chain
    select_exec = MagicMock()
    select_exec.execute.return_value = MagicMock(data=select_data or [])

    select_chain = MagicMock()
    select_chain.select.return_value.eq.return_value.order.return_value.limit.return_value = select_exec

    # insert chain
    insert_exec = MagicMock()
    insert_exec.execute.return_value = MagicMock(
        data=[insert_data] if insert_data else []
    )
    select_chain.insert.return_value = insert_exec

    client = MagicMock()
    client.table.return_value = select_chain
    return client


@pytest.mark.asyncio
async def test_cache_hit_skips_fetch():
    """Fresh snapshot (1 min old, TTL 30 min) → no HTTP call."""
    from playfuel_api.weather.cache import get_or_fetch_weather

    fresh = _make_snapshot_dict(age_seconds=60)
    client = _mock_supabase_client(select_data=[fresh])

    svc = MagicMock()
    svc.fetch_current = AsyncMock()

    result = await get_or_fetch_weather(
        client, uuid4(), lat=32.78, lng=-96.80,
        weather_service=svc, ttl_seconds=1800,
    )

    assert result is not None
    assert result.temp_f == 88.0
    svc.fetch_current.assert_not_awaited()  # cache hit — no fetch


@pytest.mark.asyncio
async def test_cache_miss_fetches_and_persists():
    """No cached snapshot → HTTP call made → snapshot inserted and returned."""
    from playfuel_api.weather.cache import get_or_fetch_weather

    new_row = _make_snapshot_dict(age_seconds=0)
    client = _mock_supabase_client(select_data=[], insert_data=new_row)

    svc = MagicMock()
    svc.fetch_current = AsyncMock(return_value=_make_open_meteo_payload())

    result = await get_or_fetch_weather(
        client, uuid4(), lat=32.78, lng=-96.80,
        weather_service=svc, ttl_seconds=1800,
    )

    assert result is not None
    svc.fetch_current.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_coords_returns_none():
    """lat=None / lng=None → return None without touching provider."""
    from playfuel_api.weather.cache import get_or_fetch_weather

    client = MagicMock()
    svc = MagicMock()
    svc.fetch_current = AsyncMock()

    result = await get_or_fetch_weather(
        client, uuid4(), lat=None, lng=None,
        weather_service=svc, ttl_seconds=1800,
    )

    assert result is None
    svc.fetch_current.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_error_with_stale_returns_stale():
    """Stale snapshot (2 h old) + provider error → return stale snapshot."""
    from playfuel_api.weather.cache import get_or_fetch_weather

    stale = _make_snapshot_dict(age_seconds=7200)  # 2 hours old
    client = _mock_supabase_client(select_data=[stale])

    svc = MagicMock()
    svc.fetch_current = AsyncMock(side_effect=httpx.HTTPError("network down"))

    result = await get_or_fetch_weather(
        client, uuid4(), lat=32.78, lng=-96.80,
        weather_service=svc, ttl_seconds=1800,
    )

    assert result is not None  # stale fallback returned


@pytest.mark.asyncio
async def test_provider_error_no_stale_returns_none():
    """No cached snapshot + provider error → return None."""
    from playfuel_api.weather.cache import get_or_fetch_weather

    client = _mock_supabase_client(select_data=[])

    svc = MagicMock()
    svc.fetch_current = AsyncMock(side_effect=httpx.HTTPError("network down"))

    result = await get_or_fetch_weather(
        client, uuid4(), lat=32.78, lng=-96.80,
        weather_service=svc, ttl_seconds=1800,
    )

    assert result is None
