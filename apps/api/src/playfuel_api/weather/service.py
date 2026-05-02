"""Open-Meteo HTTP client.

Returns raw provider payload. Classification (weather flags) lives in
rules/weather.py — this module only fetches.

Provider: https://api.open-meteo.com — free, keyless, global.
Rate limit: 10 000 requests/day (more than sufficient for v1).
Timeout: 10 s (hard limit; caller handles fallback).

Raises:
    httpx.HTTPError on transport or HTTP status failures. Callers should catch
    and fall back to cached/stale data where available.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx


class WeatherService:
    """Async HTTP wrapper around Open-Meteo /v1/forecast.

    No API key required. 10 s timeout. Caller handles retries / fallback.
    """

    def __init__(
        self,
        base_url: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        # Track ownership so aclose() only closes clients we created.
        self._owns_client = http_client is None

    async def fetch_current(self, lat: float, lng: float) -> dict:
        """Fetch current conditions from Open-Meteo.

        Returns the raw JSON payload. Raises httpx.HTTPError on failure.
        The caller (cache.py) is responsible for classification + persistence.

        Args:
            lat: Venue latitude.
            lng: Venue longitude.

        Returns:
            dict — raw Open-Meteo JSON response (access via payload["current"]).

        Raises:
            httpx.HTTPError — any transport / HTTP status failure.
        """
        url = f"{self._base_url}/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lng,
            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "weather_code,"
                "wind_speed_10m,"
                "precipitation_probability"
            ),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
        }
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def fetch_forecast_at(
        self,
        lat: float,
        lng: float,
        target_dt: datetime,
    ) -> dict:
        """Fetch hourly forecast from Open-Meteo and return the slot closest to target_dt.

        Uses the Open-Meteo /v1/forecast hourly endpoint.  Response is normalised
        to the same ``{"current": {...}}`` shape as fetch_current() so cache.py
        doesn't need to distinguish which method was called.

        Args:
            lat:       Venue latitude.
            lng:       Venue longitude.
            target_dt: Target datetime (timezone-aware recommended; UTC assumed if naive).
                       Must be within the Open-Meteo 7-day forecast horizon.

        Returns:
            dict — normalised payload with key ``"current"`` containing the hourly
            slot values closest to target_dt.

        Raises:
            httpx.HTTPError — any transport / HTTP status failure.
            ValueError      — if the hourly response is missing expected keys.
        """
        # Normalise to UTC for reliable comparison.
        if target_dt.tzinfo is None:
            target_utc = target_dt.replace(tzinfo=timezone.utc)
        else:
            target_utc = target_dt.astimezone(timezone.utc)

        target_date = target_utc.date()
        # Fetch a 2-day window so edge cases near midnight resolve correctly.
        start_date = target_date.isoformat()
        end_date = (target_date + timedelta(days=1)).isoformat()

        url = f"{self._base_url}/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lng,
            "hourly": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "weather_code,"
                "wind_speed_10m,"
                "precipitation_probability"
            ),
            "start_date": start_date,
            "end_date": end_date,
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "UTC",
        }
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        # Find the hour index closest to target_dt.
        hourly = data["hourly"]
        times: list[str] = hourly["time"]

        def _parse_utc(t: str) -> datetime:
            # Open-Meteo UTC times look like "2026-05-03T12:00" — no offset suffix.
            return datetime.fromisoformat(t).replace(tzinfo=timezone.utc)

        idx = min(
            range(len(times)),
            key=lambda i: abs((_parse_utc(times[i]) - target_utc).total_seconds()),
        )

        return {
            "current": {
                "temperature_2m": hourly["temperature_2m"][idx],
                "relative_humidity_2m": hourly["relative_humidity_2m"][idx],
                "weather_code": hourly["weather_code"][idx],
                "wind_speed_10m": hourly["wind_speed_10m"][idx],
                "precipitation_probability": hourly["precipitation_probability"][idx],
            }
        }

    async def aclose(self) -> None:
        """Close the underlying httpx client if this service owns it."""
        if self._owns_client:
            await self._client.aclose()
