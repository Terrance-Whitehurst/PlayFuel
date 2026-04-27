"""Match CRUD — /v1/tournaments/{tid}/matches.

Auth required on all endpoints. Ownership enforced by RLS (one-hop:
matches.tournament_id → tournaments.user_id = auth.uid()).

Endpoints:
    GET    /v1/tournaments/{tid}/matches          list matches (ordered by display_order)
    POST   /v1/tournaments/{tid}/matches          create match
    GET    /v1/tournaments/{tid}/matches/{mid}    fetch single match
    PUT    /v1/tournaments/{tid}/matches/{mid}    update match
    DELETE /v1/tournaments/{tid}/matches/{mid}    delete match (204)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client

router = APIRouter(prefix="/v1/tournaments", tags=["matches"])

_TABLE = "matches"


# ── Request bodies ────────────────────────────────────────────────────────────

class MatchCreate(BaseModel):
    scheduled_start: datetime
    estimated_duration_minutes: Optional[int] = None
    surface: Optional[str] = None
    format: Optional[str] = None
    age_bracket: Optional[str] = None
    display_order: Optional[int] = None


class MatchUpdate(BaseModel):
    scheduled_start: Optional[datetime] = None
    estimated_duration_minutes: Optional[int] = None
    actual_end_at: Optional[datetime] = None
    surface: Optional[str] = None
    format: Optional[str] = None
    age_bracket: Optional[str] = None
    display_order: Optional[int] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{tid}/matches", summary="List matches")
def list_matches(
    tid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> list[dict[str, Any]]:
    """List matches for a tournament, ordered by display_order then scheduled_start."""
    result = (
        client.table(_TABLE)
        .select("*")
        .eq("tournament_id", str(tid))
        .order("display_order")
        .order("scheduled_start")
        .execute()
    )
    return result.data


@router.post("/{tid}/matches", status_code=status.HTTP_201_CREATED,
             summary="Create match")
def create_match(
    tid: UUID,
    body: MatchCreate,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Create a match under a tournament. RLS verifies tournament ownership."""
    payload = body.model_dump(exclude_none=True)
    payload["tournament_id"] = str(tid)
    # datetime → ISO string for PostgREST
    if "scheduled_start" in payload:
        payload["scheduled_start"] = payload["scheduled_start"].isoformat()
    result = client.table(_TABLE).insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Insert returned no data")
    return result.data[0]


@router.get("/{tid}/matches/{mid}", summary="Get match")
def get_match(
    tid: UUID,
    mid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Fetch a single match. RLS enforces one-hop ownership."""
    result = (
        client.table(_TABLE)
        .select("*")
        .eq("id", str(mid))
        .eq("tournament_id", str(tid))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Match not found")
    return result.data[0]


@router.put("/{tid}/matches/{mid}", summary="Update match")
def update_match(
    tid: UUID,
    mid: UUID,
    body: MatchUpdate,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Update a match. RLS enforces ownership."""
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="No fields to update")
    for k in ("scheduled_start", "actual_end_at"):
        if k in payload:
            payload[k] = payload[k].isoformat()
    result = (
        client.table(_TABLE)
        .update(payload)
        .eq("id", str(mid))
        .eq("tournament_id", str(tid))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Match not found or not owned by caller")
    return result.data[0]


@router.delete("/{tid}/matches/{mid}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete match")
def delete_match(
    tid: UUID,
    mid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> None:
    """Delete a match. RLS enforces ownership."""
    client.table(_TABLE).delete().eq("id", str(mid)).eq("tournament_id", str(tid)).execute()
