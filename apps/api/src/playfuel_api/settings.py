"""Application settings loaded from environment / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""  # Legacy HS256 path only — optional. Removal: 2026-05-12.
    # Loaded but NOT used for RLS-protected routes in MVP.
    # Kept for Phase 6 / server-side admin use only.
    supabase_service_role_key: str = ""
    api_port: int = 8000
    cors_origins: list[str] = ["*"]

    # Weather provider (Phase 4) — Open-Meteo is keyless and free.
    weather_provider: str = "open-meteo"
    open_meteo_base_url: str = "https://api.open-meteo.com"
    weather_cache_ttl_sec: int = 1800

    # Places provider (Phase 5 / Task #8) — Google Places or deterministic mock.
    # places_provider: "auto" | "google" | "mock"
    #   auto   → Google if GOOGLE_PLACES_API_KEY is set, else Mock.
    #   google → Google (key required; falls back to Mock if key missing).
    #   mock   → MockPlacesProvider always (demo + tests).
    places_provider: str = "auto"
    google_places_api_key: str = ""
    places_search_radius_m: int = 4828   # ~3 miles
    places_max_results: int = 6

    # LLM provider (Phase 6 / Task #9) — Anthropic, OpenAI, or deterministic template.
    # llm_provider: "auto" | "template" | "anthropic" | "openai"
    #   auto      → Anthropic if ANTHROPIC_API_KEY set, else OpenAI if OPENAI_API_KEY set,
    #               else TemplateProvider (deterministic, no network).
    #   template  → TemplateProvider always (used in tests + demo; no keys needed).
    #   anthropic → AnthropicProvider (requires 'anthropic' SDK + key).
    #   openai    → OpenAIProvider    (requires 'openai'    SDK + key).
    llm_provider: str = "auto"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 600
    llm_temperature: float = 0.3

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
