"""FastAPI application entry point — PlayFuel API.

Configures CORS, mounts all route modules, and logs RULES_CONSTANTS_VERSION
on startup so the deployed version is traceable in log aggregators.

Route mounting:
  /healthz          — health.router (no auth, no /v1 prefix)
  /v1/player-profiles    — player_profiles.router
  /v1/...                — tournaments, matches, plans routers

CORS:
  allow_origins read from Settings.cors_origins (default ["*"] for local dev).
  In production, override via CORS_ORIGINS env var (JSON array or comma-separated).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from playfuel_api.rules.constants import RULES_CONSTANTS_VERSION
from playfuel_api.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    logger.info(
        "PlayFuel API starting — RULES_CONSTANTS_VERSION=%s", RULES_CONSTANTS_VERSION
    )
    yield


app = FastAPI(
    title="PlayFuel API",
    version="1.0.0",
    lifespan=lifespan,
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import routers after app is constructed to avoid circular imports.
from playfuel_api.routes import routers  # noqa: E402

for _router in routers:
    app.include_router(_router)
