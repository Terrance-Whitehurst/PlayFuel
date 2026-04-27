"""Weather provider integration — Open-Meteo + read-through Supabase cache.

Public API:
    get_or_fetch_weather(client, tournament_id, *, lat, lng, weather_service, ttl_seconds)
        → Optional[WeatherSnapshotRow]

Phase 4 (Task #7). Provider: Open-Meteo (free, keyless, global).
Cache key: tournament_id (per-tournament, matches weather_snapshots FK).
"""
from playfuel_api.weather.cache import get_or_fetch_weather

__all__ = ["get_or_fetch_weather"]
