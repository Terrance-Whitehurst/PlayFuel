"""Tournament CRUD + current-user endpoint — /v1/tournaments, /v1/me.

Auth required on all endpoints. Ownership enforced by RLS.

Endpoints:
    GET    /v1/me                       current user record
    GET    /v1/tournaments              list tournaments for caller
    POST   /v1/tournaments              create tournament
    GET    /v1/tournaments/{tid}        fetch single tournament
    PUT    /v1/tournaments/{tid}        update tournament
    DELETE /v1/tournaments/{tid}        delete tournament (204)
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client
from playfuel_api.rules.constants import DRAW_SIZES

router = APIRouter(prefix="/v1", tags=["tournaments"])

_TABLE = "tournaments"


# ── Request bodies ────────────────────────────────────────────────────────────

class TournamentCreate(BaseModel):
    # camelCase aliases: iOS sends venueLat, venueLng, startDate, endDate etc.
    # populate_by_name=True allows both snake_case (tests) and camelCase (iOS).
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str
    draw_size: int                         # required — 32 | 64 | 128 | 256
    start_date: date
    end_date: Optional[date] = None
    venue_name: Optional[str] = None
    venue_address: Optional[str] = None
    venue_city: Optional[str] = None
    venue_region: Optional[str] = None
    venue_postal: Optional[str] = None
    venue_lat: Optional[float] = None
    venue_lng: Optional[float] = None
    # venue_place_id: stable place ID from a Places provider (e.g. Google Places).
    # Nullable: MapKit results do not carry a stable place ID.
    # Added migration 0012 (TOURNAMENT_LOCATION_V1.md §C.2).
    venue_place_id: Optional[str] = None

    @field_validator("draw_size")
    @classmethod
    def validate_draw_size(cls, v: int) -> int:
        if v not in DRAW_SIZES:
            raise ValueError(f"draw_size must be one of {DRAW_SIZES}")
        return v


class TournamentUpdate(BaseModel):
    # camelCase aliases: iOS sends venueLat, venueLng, startDate, endDate etc.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: Optional[str] = None
    draw_size: Optional[int] = None        # optional for partial update
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    venue_name: Optional[str] = None
    venue_address: Optional[str] = None
    venue_city: Optional[str] = None
    venue_region: Optional[str] = None
    venue_postal: Optional[str] = None
    venue_lat: Optional[float] = None
    venue_lng: Optional[float] = None
    venue_place_id: Optional[str] = None

    @field_validator("draw_size")
    @classmethod
    def validate_draw_size(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in DRAW_SIZES:
            raise ValueError(f"draw_size must be one of {DRAW_SIZES}")
        return v


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/me", summary="Current user")
def get_current_user(
    user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Return the authenticated user's row from the public.users shadow table."""
    result = client.table("users").select("*").eq("id", str(user_id)).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="User record not found")
    return result.data[0]


@router.get("/tournaments", summary="List tournaments")
def list_tournaments(
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> list[dict[str, Any]]:
    """Return all tournaments visible to the authenticated user (RLS-filtered)."""
    result = client.table(_TABLE).select("*").execute()
    return result.data


@router.post("/tournaments", status_code=status.HTTP_201_CREATED,
             summary="Create tournament")
def create_tournament(
    body: TournamentCreate,
    user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Create a new tournament owned by the authenticated caller."""
    payload = body.model_dump(exclude_none=True)
    payload["user_id"] = str(user_id)  # required: NOT NULL, no DEFAULT; RLS enforces owner
    # date → ISO string for PostgREST
    for k in ("start_date", "end_date"):
        if k in payload:
            payload[k] = payload[k].isoformat()
    result = client.table(_TABLE).insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Insert returned no data")
    return result.data[0]


@router.get("/tournaments/{tid}", summary="Get tournament")
def get_tournament(
    tid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Fetch a single tournament by ID (RLS enforces ownership)."""
    result = client.table(_TABLE).select("*").eq("id", str(tid)).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Tournament not found")
    return result.data[0]


@router.put("/tournaments/{tid}", summary="Update tournament")
def update_tournament(
    tid: UUID,
    body: TournamentUpdate,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Update a tournament. RLS ensures only the owner can update."""
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="No fields to update")
    for k in ("start_date", "end_date"):
        if k in payload:
            payload[k] = payload[k].isoformat()
    result = client.table(_TABLE).update(payload).eq("id", str(tid)).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Tournament not found or not owned by caller")
    return result.data[0]


@router.delete("/tournaments/{tid}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response,
               summary="Delete tournament")
def delete_tournament(
    tid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Response:
    """Delete a tournament. RLS enforces ownership. Cascades to matches/plans.

    Returns 404 when the row doesn't exist or RLS filtered it out (caller doesn't
    own it). RLS makes 404 == 403 from the caller's POV — intentional per spec §C.1.
    """
    result = client.table(_TABLE).delete().eq("id", str(tid)).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Tournament not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
