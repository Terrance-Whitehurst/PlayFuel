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

Timing middleware:
  RequestTimingMiddleware logs every request at INFO with method, path,
  status code, and total latency in ms.  Stays in production — operational
  visibility we should have had since day one.
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from playfuel_api.rules.constants import RULES_CONSTANTS_VERSION
from playfuel_api.settings import get_settings

logger = logging.getLogger(__name__)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, and duration_ms.

    Stays in production — provides baseline operational visibility.
    Log format (INFO):
        REQUEST GET /healthz → 200 in 2ms
        REQUEST POST /v1/tournaments/{tid}/plans/generate → 200 in 312ms
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "REQUEST %s %s → %d in %dms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


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
# Add timing middleware AFTER CORS so it wraps the full request lifecycle.
app.add_middleware(RequestTimingMiddleware)

# Import routers after app is constructed to avoid circular imports.
from playfuel_api.routes import routers  # noqa: E402

for _router in routers:
    app.include_router(_router)
