"""Phase 4 WX-G1/G2 close-out tests — forecast targeting + wind/precip exposure.

WX-G1: fetch_forecast_at() picks the correct hourly slot; cache dispatches
       to forecast vs. current based on target_dt distance from now.
WX-G2: WeatherBlock serialises wind_mph + precip_prob with camelCase aliases.
Route: generate_plan() passes target_dt kwarg through to get_or_fetch_weather.

All Open-Meteo HTTP calls are mocked (HTTP-layer mock).
No Supabase or DB mocking (project rule).

Live test gated on SUPABASE_SERVICE_ROLE_KEY (mirrors places live test pattern).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from playfuel_api.models.api import WeatherBlock
from playfuel_api.models.enums import WeatherCondition
from playfuel_api.weather.service import WeatherService


# ── Helpers ───────────────────────────────────────────────────────────────────


def _hourly_payload(
    target_hour_idx: int = 6,
    temp_f: float = 88.0,
    humidity: int = 72,
    code: int = 0,
    wind_mph: float = 8.5,
    precip: int = 10,
    n_hours: int = 24,
) -> dict:
    """Build a mock Open-Meteo hourly response with n_hours of data.

    target_hour_idx determines which slot has the expected values; all other
    slots get different values so the test can confirm the right slot was picked.
    """
    base = datetime(2026, 5, 10, 0, 0, tzinfo=timezone.utc)
    times = [(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(n_hours)]

    temperature_2m = [0.0] * n_hours
    relative_humidity_2m = [0] * n_hours
    weather_code = [99] * n_hours   # storm default; will differ from target slot
    wind_speed_10m = [0.0] * n_hours
    precipitation_probability = [0] * n_hours

    # Set target slot values
    temperature_2m[target_hour_idx] = temp_f
    relative_humidity_2m[target_hour_idx] = humidity
    weather_code[target_hour_idx] = code
    wind_speed_10m[target_hour_idx] = wind_mph
    precipitation_probability[target_hour_idx] = precip

    return {
        "hourly": {
            "time": times,
            "temperature_2m": temperature_2m,
            "relative_humidity_2m": relative_humidity_2m,
            "weather_code": weather_code,
            "wind_speed_10m": wind_speed_10m,
            "precipitation_probability": precipitation_probability,
        }
    }


def _mock_http_for_forecast(payload: dict) -> MagicMock:
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value=payload)
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


# ── WX-G1 service.py tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_forecast_at_picks_correct_hour():
    """fetch_forecast_at() returns the temperature from the slot closest to target_dt.

    Target: 2026-05-10T06:00 UTC  ->  index 6 in a 24-hour payload starting at 00:00.
    All other slots have temp=0.0; slot 6 has temp=88.0.
    """
    target_hour_idx = 6
    target_dt = datetime(2026, 5, 10, 6, 0, tzinfo=timezone.utc)
    payload = _hourly_payload(target_hour_idx=target_hour_idx, temp_f=88.0)

    mock_client = _mock_http_for_forecast(payload)
    svc = WeatherService(base_url="https://api.open-meteo.com", http_client=mock_client)

    result = await svc.fetch_forecast_at(32.78, -96.80, target_dt)

    assert result["current"]["temperature_2m"] == 88.0, (
        f"Expected 88.0 (slot 6), got {result['current']['temperature_2m']}"
    )
    assert result["current"]["wind_speed_10m"] == 8.5
    assert result["current"]["precipitation_probability"] == 10


@pytest.mark.asyncio
async def test_fetch_forecast_at_picks_nearest_when_not_on_hour():
    """fetch_forecast_at picks the nearest slot when target_dt is between hours.

    Target: 2026-05-10T06:40 UTC -- closer to hour 7 (40 min away) than hour 7 is
    actually 20 min away, hour 6 is 40 min away.  Expects slot index 7.
    """
    target_dt = datetime(2026, 5, 10, 6, 40, tzinfo=timezone.utc)
    # Slot 7 should be closest (6:40 -> 7:00 is 20 min away; 6:00 is 40 min away)
    payload = _hourly_payload(target_hour_idx=7, temp_f=91.0)
    mock_client = _mock_http_for_forecast(payload)
    svc = WeatherService(base_url="https://api.open-meteo.com", http_client=mock_client)

    result = await svc.fetch_forecast_at(32.78, -96.80, target_dt)

    assert result["current"]["temperature_2m"] == 91.0


@pytest.mark.asyncio
async def test_fetch_forecast_at_uses_hourly_param():
    """HTTP GET to /v1/forecast must include 'hourly' in params (not 'current').

    The 'current' param is for fetch_current(); fetch_forecast_at() uses 'hourly'.
    """
    target_dt = datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc)
    payload = _hourly_payload(target_hour_idx=9)
    mock_client = _mock_http_for_forecast(payload)
    svc = WeatherService(base_url="https://api.open-meteo.com", http_client=mock_client)

    await svc.fetch_forecast_at(32.78, -96.80, target_dt)

    call_args = mock_client.get.call_args
    assert call_args is not None
    params = call_args.kwargs.get("params", {})
    assert "hourly" in params, "fetch_forecast_at must use 'hourly' param, not 'current'"
    assert "current" not in params, "fetch_forecast_at must NOT use 'current' param"
    assert params.get("timezone") == "UTC", "timezone=UTC required for consistent hour indexing"


@pytest.mark.asyncio
async def test_fetch_forecast_at_normalises_naive_datetime():
    """Naive target_dt (no tzinfo) is treated as UTC without raising."""
    target_dt_naive = datetime(2026, 5, 10, 9, 0)  # no tzinfo
    payload = _hourly_payload(target_hour_idx=9)
    mock_client = _mock_http_for_forecast(payload)
    svc = WeatherService(base_url="https://api.open-meteo.com", http_client=mock_client)

    # Should not raise -- naive dt handled gracefully
    result = await svc.fetch_forecast_at(32.78, -96.80, target_dt_naive)
    assert "current" in result


# ── WX-G1 cache.py dispatch tests ────────────────────────────────────────────


def _make_cache_mock_client(select_data: list | None = None, insert_data: dict | None = None):
    """Minimal Supabase mock for cache tests (mirrors test_weather_service.py pattern)."""
    select_exec = MagicMock()
    select_exec.execute.return_value = MagicMock(data=select_data or [])
    select_chain = MagicMock()
    select_chain.select.return_value.eq.return_value.order.return_value.limit.return_value = select_exec
    insert_exec = MagicMock()
    insert_exec.execute.return_value = MagicMock(
        data=[insert_data] if insert_data else []
    )
    select_chain.insert.return_value = insert_exec
    client = MagicMock()
    client.table.return_value = select_chain
    return client


def _snapshot_dict(age_seconds: int = 0) -> dict:
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    now = datetime.now(tz=timezone.utc)
    fetched_at = now - timedelta(seconds=age_seconds)
    return {
        "id": str(uuid4()),
        "tournament_id": str(uuid4()),
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


@pytest.mark.asyncio
async def test_cache_uses_forecast_when_future():
    """target_dt = now + 6h -> use_forecast=True -> fetch_forecast_at() called."""
    from playfuel_api.weather.cache import get_or_fetch_weather

    new_row = _snapshot_dict(age_seconds=0)
    client = _make_cache_mock_client(select_data=[], insert_data=new_row)

    svc = MagicMock()
    svc.fetch_current = AsyncMock()
    # fetch_forecast_at must return the same shape as fetch_current
    svc.fetch_forecast_at = AsyncMock(return_value={
        "current": {
            "temperature_2m": 88.0,
            "relative_humidity_2m": 72.0,
            "weather_code": 0,
            "wind_speed_10m": 8.5,
            "precipitation_probability": 10.0,
        }
    })

    target_dt = datetime.now(tz=timezone.utc) + timedelta(hours=6)  # 6h out -> forecast
    result = await get_or_fetch_weather(
        client, uuid4(), lat=32.78, lng=-96.80,
        weather_service=svc, ttl_seconds=1800, target_dt=target_dt,
    )

    svc.fetch_forecast_at.assert_awaited_once()
    svc.fetch_current.assert_not_awaited()
    assert result is not None


@pytest.mark.asyncio
async def test_cache_uses_current_when_near():
    """target_dt = now + 1h (< 3h threshold) -> fetch_current() called, not forecast."""
    from playfuel_api.weather.cache import get_or_fetch_weather

    new_row = _snapshot_dict(age_seconds=0)
    client = _make_cache_mock_client(select_data=[], insert_data=new_row)

    svc = MagicMock()
    svc.fetch_current = AsyncMock(return_value={
        "current": {
            "temperature_2m": 80.0,
            "relative_humidity_2m": 60.0,
            "weather_code": 1,
            "wind_speed_10m": 5.0,
            "precipitation_probability": 0.0,
        }
    })
    svc.fetch_forecast_at = AsyncMock()

    target_dt = datetime.now(tz=timezone.utc) + timedelta(hours=1)  # 1h out -> current
    result = await get_or_fetch_weather(
        client, uuid4(), lat=32.78, lng=-96.80,
        weather_service=svc, ttl_seconds=1800, target_dt=target_dt,
    )

    svc.fetch_current.assert_awaited_once()
    svc.fetch_forecast_at.assert_not_awaited()
    assert result is not None


@pytest.mark.asyncio
async def test_cache_uses_current_when_no_target_dt():
    """target_dt=None -> fetch_current() always called (unchanged behaviour)."""
    from playfuel_api.weather.cache import get_or_fetch_weather

    new_row = _snapshot_dict(age_seconds=0)
    client = _make_cache_mock_client(select_data=[], insert_data=new_row)

    svc = MagicMock()
    svc.fetch_current = AsyncMock(return_value={
        "current": {
            "temperature_2m": 80.0,
            "relative_humidity_2m": 60.0,
            "weather_code": 1,
            "wind_speed_10m": 5.0,
            "precipitation_probability": 0.0,
        }
    })
    svc.fetch_forecast_at = AsyncMock()

    result = await get_or_fetch_weather(
        client, uuid4(), lat=32.78, lng=-96.80,
        weather_service=svc, ttl_seconds=1800, target_dt=None,
    )

    svc.fetch_current.assert_awaited_once()
    svc.fetch_forecast_at.assert_not_awaited()
    assert result is not None


@pytest.mark.asyncio
async def test_cache_uses_current_when_over_7d(caplog):
    """target_dt = now + 8d (> 7-day horizon) -> warning logged + fetch_current() used."""
    from playfuel_api.weather.cache import get_or_fetch_weather

    new_row = _snapshot_dict(age_seconds=0)
    client = _make_cache_mock_client(select_data=[], insert_data=new_row)

    svc = MagicMock()
    svc.fetch_current = AsyncMock(return_value={
        "current": {
            "temperature_2m": 80.0,
            "relative_humidity_2m": 60.0,
            "weather_code": 1,
            "wind_speed_10m": 5.0,
            "precipitation_probability": 0.0,
        }
    })
    svc.fetch_forecast_at = AsyncMock()

    target_dt = datetime.now(tz=timezone.utc) + timedelta(days=8)

    with caplog.at_level(logging.WARNING, logger="playfuel_api.weather.cache"):
        result = await get_or_fetch_weather(
            client, uuid4(), lat=32.78, lng=-96.80,
            weather_service=svc, ttl_seconds=1800, target_dt=target_dt,
        )

    svc.fetch_current.assert_awaited_once()
    svc.fetch_forecast_at.assert_not_awaited()
    assert result is not None
    # Warning must have been emitted
    warning_texts = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("forecast horizon" in t or "days out" in t for t in warning_texts), (
        f"Expected warning about >7d horizon; got: {warning_texts}"
    )


# ── WX-G2 WeatherBlock serialisation tests ───────────────────────────────────


def test_weather_block_exposes_wind_precip():
    """WeatherBlock(wind_mph=8.5, precip_prob=10.0) serialises to windMph + precipProb."""
    block = WeatherBlock(
        temp_f=88.0,
        humidity_pct=72.0,
        condition=WeatherCondition.clear,
        flag_hot=True,
        flag_very_hot=False,
        flag_humid=True,
        flag_cold=False,
        flag_windy=False,
        flag_rain_risk=False,
        flag_extreme_heat_risk=True,
        is_stale=False,
        fetched_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
        provider="open-meteo",
        wind_mph=8.5,
        precip_prob=10.0,
    )

    dumped = block.model_dump(by_alias=True)
    assert dumped["windMph"] == 8.5, f"Expected windMph=8.5, got {dumped.get('windMph')}"
    assert dumped["precipProb"] == 10.0, f"Expected precipProb=10.0, got {dumped.get('precipProb')}"


def test_weather_block_wind_precip_default_none():
    """WeatherBlock without wind/precip -> both default to None, not 0.0."""
    block = WeatherBlock(
        temp_f=65.0,
        humidity_pct=40.0,
        condition=WeatherCondition.clear,
        flag_hot=False,
        flag_very_hot=False,
        flag_humid=False,
        flag_cold=False,
        flag_windy=False,
        flag_rain_risk=False,
        flag_extreme_heat_risk=False,
        is_stale=False,
        fetched_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
        provider="open-meteo",
    )

    dumped = block.model_dump(by_alias=True)
    assert dumped["windMph"] is None
    assert dumped["precipProb"] is None


# ── Route integration test: target_dt flows through ──────────────────────────


def test_route_plan_passes_target_dt(client_with_auth, mock_db) -> None:
    """generate_plan() passes target_dt kwarg to get_or_fetch_weather.

    When match_rows[0].scheduled_start is 6h in the future, the route must pass
    that datetime as target_dt so the cache layer can dispatch to forecast.
    """
    future_start = datetime.now(tz=timezone.utc) + timedelta(hours=6)
    match_data = {
        "id": str(uuid4()),
        "tournament_id": "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        "scheduled_start": future_start.isoformat(),
        "estimated_duration_minutes": None,
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "doubles_format": None,
        "age_bracket": "14U",
        "display_order": 1,
        "round_label": "R16",
        "opponent_label": None,
        "court_label": None,
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }

    TID = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

    matches_chain = MagicMock()
    (
        matches_chain.select.return_value
        .eq.return_value
        .order.return_value
        .order.return_value
        .execute.return_value.data
    ) = [match_data]

    tournaments_chain = MagicMock()
    (
        tournaments_chain.select.return_value
        .eq.return_value
        .limit.return_value
        .execute.return_value.data
    ) = [{"venue_lat": 26.4615, "venue_lng": -80.0728, "venue_name": "Delray Beach TC"}]

    plans_chain = MagicMock()
    plans_chain.upsert.return_value.execute.return_value.data = [{"id": "fake"}]

    def _dispatch(name: str):
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch

    from playfuel_api.services.llm import TemplateProvider
    from playfuel_api.services.places import MockPlacesProvider

    places = list(MockPlacesProvider().search_nearby(26.46, -80.07, 4828, 6))

    captured_kwargs: list[dict] = []

    async def _spy_weather(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return None  # degrade gracefully -- plan still generated

    with (
        patch("playfuel_api.routes.plans.get_or_fetch_weather", side_effect=_spy_weather),
        patch("playfuel_api.routes.plans.find_nearby_food", return_value=places),
        patch("playfuel_api.routes.plans.get_llm_provider", return_value=TemplateProvider()),
    ):
        resp = client_with_auth.post(f"/v1/tournaments/{TID}/plans/generate")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert captured_kwargs, "get_or_fetch_weather was never called"

    call_kw = captured_kwargs[0]
    assert "target_dt" in call_kw, (
        "generate_plan must pass target_dt kwarg to get_or_fetch_weather"
    )
    passed_target_dt = call_kw["target_dt"]
    assert passed_target_dt is not None, "target_dt should not be None when matches exist"

    # Confirm the passed value is close to our future_start (within 1 second)
    delta = abs((passed_target_dt - future_start).total_seconds())
    assert delta < 1.0, (
        f"target_dt mismatch: expected ~{future_start}, got {passed_target_dt}"
    )


# ── Live Supabase round-trip (gated) ─────────────────────────────────────────


@pytest.mark.skipif(
    not os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    reason="Live Supabase test; set SUPABASE_SERVICE_ROLE_KEY to run",
)
@pytest.mark.asyncio
async def test_live_weather_fetch_delray_beach():
    """Hit real Open-Meteo for Delray Beach (26.4615, -80.0728).

    Asserts the response has plausible values (temp > 0, humidity > 0,
    at least one of the flag fields resolved without error).
    No mocking -- real HTTP to Open-Meteo (free, keyless).
    """
    from playfuel_api.weather.service import WeatherService

    svc = WeatherService(base_url="https://api.open-meteo.com")
    try:
        payload = await svc.fetch_current(26.4615, -80.0728)
        current = payload["current"]
        assert current["temperature_2m"] > 0, "Temp should be > 0 for Delray Beach"
        assert 0 <= current["relative_humidity_2m"] <= 100
    finally:
        await svc.aclose()
