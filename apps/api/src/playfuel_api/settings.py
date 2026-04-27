"""Application settings loaded from environment / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""
    # Loaded but NOT used for RLS-protected routes in MVP.
    # Kept for Phase 6 / server-side admin use only.
    supabase_service_role_key: str = ""
    api_port: int = 8000
    cors_origins: list[str] = ["*"]

    # Weather provider (Phase 4) — Open-Meteo is keyless and free.
    weather_provider: str = "open-meteo"
    open_meteo_base_url: str = "https://api.open-meteo.com"
    weather_cache_ttl_sec: int = 1800

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
