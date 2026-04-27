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

    async def aclose(self) -> None:
        """Close the underlying httpx client if this service owns it."""
        if self._owns_client:
            await self._client.aclose()
