"""Read-through Supabase cache for tournament weather snapshots.

Cache key: tournament_id (per-tournament caching — matches weather_snapshots FK).
TTL default: 30 minutes (1800 s) — fresh enough for plan generation, low
rate-limit pressure against Open-Meteo's 10 000 req/day limit.

Behaviour matrix:
    lat or lng is None                              -> return None (no fetch)
    cache hit  (fetched_at within TTL)              -> return cached row
    cache miss + fetch ok                           -> persist + return new row
    cache miss + fetch fails + stale exists         -> return stale row (logged)
    cache miss + fetch fails + no stale             -> return None (logged)

Forecast dispatch (WX-G1):
    target_dt not provided OR <= 3h in future       -> fetch_current()
    target_dt > 3h in future AND <= 7 days out      -> fetch_forecast_at()
    target_dt > 7 days out                          -> log warning + fetch_current()

The route (routes/plans.py) computes is_stale from fetched_at age after
this function returns — cache.py does not set that flag itself.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import httpx
from supabase import Client

from playfuel_api.models.db import WeatherSnapshotRow
from playfuel_api.models.enums import WeatherCondition
from playfuel_api.rules.weather import classify_weather
from playfuel_api.weather.codes import wmo_to_condition
from playfuel_api.weather.service import WeatherService

_logger = logging.getLogger(__name__)
_TABLE = "weather_snapshots"

# WX-G1 forecast dispatch thresholds
_FORECAST_THRESHOLD_SEC: int = 10_800   # 3 hours — beyond this use hourly forecast
_FORECAST_MAX_DAYS: int = 7             # Open-Meteo hourly horizon (accuracy past 7d is low)


async def get_or_fetch_weather(
    client: Client,
    tournament_id: UUID,
    *,
    lat: Optional[float],
    lng: Optional[float],
    weather_service: WeatherService,
    ttl_seconds: int = 1800,
    target_dt: Optional[datetime] = None,
) -> Optional[WeatherSnapshotRow]:
    """Return a fresh-or-cached WeatherSnapshotRow for the tournament.

    Args:
        client:          Supabase client (user-scoped, for RLS).
        tournament_id:   Tournament UUID -- the cache key.
        lat:             Venue latitude. If None, returns None immediately.
        lng:             Venue longitude. If None, returns None immediately.
        weather_service: Async HTTP client for Open-Meteo.
        ttl_seconds:     Cache freshness window (default 1800 = 30 min).
        target_dt:       Optional target datetime for forecast dispatch (WX-G1).
                         If provided and > _FORECAST_THRESHOLD_SEC in the future
                         and within _FORECAST_MAX_DAYS, fetch_forecast_at() is
                         used instead of fetch_current().
                         Naive datetimes treated as UTC. None -> fetch_current().

    Returns:
        WeatherSnapshotRow if weather is available; None otherwise.
    """
    if lat is None or lng is None:
        _logger.info(
            "Tournament %s has no venue coords; skipping weather fetch",
            tournament_id,
        )
        return None

    # 1. Look up most recent snapshot for this tournament
    latest_result = (
        client.table(_TABLE)
        .select("*")
        .eq("tournament_id", str(tournament_id))
        .order("fetched_at", desc=True)
        .limit(1)
        .execute()
    )

    cached: Optional[WeatherSnapshotRow] = None
    age: timedelta = timedelta(seconds=ttl_seconds + 1)  # default = stale

    if latest_result.data:
        cached = WeatherSnapshotRow(**latest_result.data[0])
        age = datetime.now(tz=timezone.utc) - cached.fetched_at
        if age <= timedelta(seconds=ttl_seconds):
            return cached  # fresh cache hit -- no provider call needed

    # 2. Cache miss (or stale) -- decide forecast vs. current, then fetch.
    # Dispatch: if target_dt is >3h out and within 7 days, use fetch_forecast_at.
    use_forecast = False
    if target_dt is not None:
        target_utc = (
            target_dt.replace(tzinfo=timezone.utc)
            if target_dt.tzinfo is None
            else target_dt.astimezone(timezone.utc)
        )
        seconds_out = (target_utc - datetime.now(tz=timezone.utc)).total_seconds()
        if seconds_out > _FORECAST_THRESHOLD_SEC:
            days_out = (target_utc.date() - datetime.now(tz=timezone.utc).date()).days
            if days_out > _FORECAST_MAX_DAYS:
                _logger.warning(
                    "Tournament %s scheduled_start is %d days out (>%d-day Open-Meteo "
                    "forecast horizon); falling back to fetch_current",
                    tournament_id,
                    days_out,
                    _FORECAST_MAX_DAYS,
                )
                # use_forecast stays False
            else:
                use_forecast = True

    try:
        payload = (
            await weather_service.fetch_forecast_at(lat, lng, target_dt)
            if use_forecast
            else await weather_service.fetch_current(lat, lng)
        )
    except (httpx.HTTPError, ValueError) as exc:
        _logger.warning(
            "Weather provider fetch failed for tournament %s: %s", tournament_id, exc
        )
        if cached is not None:
            _logger.info(
                "Returning stale weather snapshot (age=%.0fs)", age.total_seconds()
            )
            return cached  # stale fallback
        return None  # no snapshot at all

    # 3. Classify and persist
    current = payload.get("current") or {}
    try:
        temp_f = float(current["temperature_2m"])
        humidity_pct = float(current["relative_humidity_2m"])
        weather_code = int(current["weather_code"])
    except (KeyError, TypeError, ValueError) as exc:
        _logger.warning(
            "Weather payload missing required fields for tournament %s: %s",
            tournament_id,
            exc,
        )
        return cached  # may be None if no stale snapshot

    condition: WeatherCondition = wmo_to_condition(weather_code)

    wind_raw = current.get("wind_speed_10m")
    precip_raw = current.get("precipitation_probability")
    wind_mph = float(wind_raw) if wind_raw is not None else 0.0
    precip_pp = float(precip_raw) if precip_raw is not None else 0.0

    flags = classify_weather(
        temp_f=temp_f,
        humidity_pct=humidity_pct,
        wind_mph=wind_mph,
        precipitation_probability=precip_pp,
    )

    insert_row = {
        "tournament_id": str(tournament_id),
        "temp_f": temp_f,
        "humidity_pct": humidity_pct,
        "wind_mph": float(wind_raw) if wind_raw is not None else None,
        "precipitation_probability": float(precip_raw) if precip_raw is not None else None,
        "condition": condition.value,
        "flag_hot": flags["flag_hot"],
        "flag_very_hot": flags["flag_very_hot"],
        "flag_humid": flags["flag_humid"],
        "flag_cold": flags["flag_cold"],
        "flag_windy": flags["flag_windy"],
        "flag_rain_risk": flags["flag_rain_risk"],
        "flag_extreme_heat_risk": flags["flag_extreme_heat_risk"],
        "provider": "open-meteo",
    }

    insert_result = (
        client.table(_TABLE).insert(insert_row).execute()
    )
    if not insert_result.data:
        _logger.warning(
            "Weather snapshot insert returned no data for tournament %s; "
            "returning stale if available",
            tournament_id,
        )
        return cached  # may be None

    return WeatherSnapshotRow(**insert_result.data[0])
