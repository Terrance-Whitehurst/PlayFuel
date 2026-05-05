"""Health check — GET /healthz and GET /v1/version.

No authentication required. Used by load balancers, uptime monitors, and CI
readiness gates. Returns RULES_CONSTANTS_VERSION so callers can assert the
deployed rules engine version without reading any database.

/v1/version: returns git SHA + build time for deployment staleness detection.
GIT_SHA and BUILD_TIME are injected at Docker build time (ENV in Dockerfile).
Falls back to live `git rev-parse --short HEAD` if env vars are absent (local
development), and to "unknown" if git is also unavailable (Fly container).
"""
import os
import subprocess

from fastapi import APIRouter

from playfuel_api.rules.constants import RULES_CONSTANTS_VERSION

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Health check")
def health() -> dict:
    """Return API liveness and the active rules constants version.

    Response shape:
        {"status": "ok", "rules_version": "1.1.0"}
    """
    return {"status": "ok", "rules_version": RULES_CONSTANTS_VERSION}


@router.get("/v1/version", summary="Build/version info")
def version() -> dict:
    """Return git SHA + rules version so clients can detect stale deployments.

    Priority for git_sha:
      1. GIT_SHA env var — set at Docker build time via ARG/ENV in Dockerfile.
      2. Live `git rev-parse --short HEAD` — works in local development.
      3. "unknown" — fallback when running inside a Fly container without the
         GIT_SHA env var set (git binary not present in the prod image).

    Response shape:
        {
            "rules_version": "1.1.0",
            "git_sha": "abc1234",
            "build_time": "2026-05-04T15:00:00Z"
        }
    """
    sha = os.environ.get("GIT_SHA")
    if not sha:
        try:
            sha = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:  # noqa: BLE001
            sha = "unknown"
    return {
        "rules_version": RULES_CONSTANTS_VERSION,
        "git_sha": sha or "unknown",
        "build_time": os.environ.get("BUILD_TIME", "unknown"),
    }
