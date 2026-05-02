"""Route collection — imported by main.py to mount all routers.

Import order determines the order routers appear in OpenAPI docs.
Each router carries its own prefix; health is prefix-less (mounts at /healthz).
"""
from playfuel_api.routes.feedback import router as feedback_router
from playfuel_api.routes.health import router as health_router
from playfuel_api.routes.match_evaluations import router as match_evaluations_router
from playfuel_api.routes.matches import router as matches_router
from playfuel_api.routes.plans import router as plans_router
from playfuel_api.routes.player_profiles import router as player_profiles_router
from playfuel_api.routes.players import router as players_router
from playfuel_api.routes.tournaments import router as tournaments_router

routers = [
    health_router,
    player_profiles_router,
    tournaments_router,
    matches_router,
    match_evaluations_router,
    plans_router,
    players_router,
    feedback_router,
]

__all__ = ["routers"]
