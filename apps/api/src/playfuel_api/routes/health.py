"""Health check — GET /healthz.

No authentication required. Used by load balancers, uptime monitors, and CI
readiness gates. Returns RULES_CONSTANTS_VERSION so callers can assert the
deployed rules engine version without reading any database.
"""
from fastapi import APIRouter

from playfuel_api.rules.constants import RULES_CONSTANTS_VERSION

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Health check")
def health() -> dict:
    """Return API liveness and the active rules constants version.

    Response shape:
        {"status": "ok", "rules_version": "1.0.0"}
    """
    return {"status": "ok", "rules_version": RULES_CONSTANTS_VERSION}
