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
from pydantic import BaseModel
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client

router = APIRouter(prefix="/v1", tags=["tournaments"])

_TABLE = "tournaments"


# ── Request bodies ────────────────────────────────────────────────────────────

class TournamentCreate(BaseModel):
    name: str
    start_date: date
    end_date: Optional[date] = None
    venue_name: Optional[str] = None
    venue_address: Optional[str] = None
    venue_city: Optional[str] = None
    venue_region: Optional[str] = None
    venue_postal: Optional[str] = None
    venue_lat: Optional[float] = None
    venue_lng: Optional[float] = None


class TournamentUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    venue_name: Optional[str] = None
    venue_address: Optional[str] = None
    venue_city: Optional[str] = None
    venue_region: Optional[str] = None
    venue_postal: Optional[str] = None
    venue_lat: Optional[float] = None
    venue_lng: Optional[float] = None


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
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Create a new tournament. user_id set by DB trigger / RLS."""
    payload = body.model_dump(exclude_none=True)
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
    """Delete a tournament. RLS enforces ownership. Cascades to matches/plans."""
    client.table(_TABLE).delete().eq("id", str(tid)).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
