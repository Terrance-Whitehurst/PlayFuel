"""Player profile CRUD — /v1/player-profiles.

Auth required on all endpoints. Ownership enforced by RLS — no WHERE user_id
filters in route code; the per-request Supabase client authenticated via
authed_client() carries the caller's JWT so Postgres enforces row ownership.

Endpoints:
    GET    /v1/player-profiles              list profiles for caller
    POST   /v1/player-profiles              create profile
    GET    /v1/player-profiles/{profile_id} fetch single profile
    PUT    /v1/player-profiles/{profile_id} update profile
    DELETE /v1/player-profiles/{profile_id} delete profile (204)
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client
from playfuel_api.models.db import PlayerProfileRow

router = APIRouter(prefix="/v1/player-profiles", tags=["player-profiles"])

_TABLE = "player_profiles"


# ── Request bodies ────────────────────────────────────────────────────────────

class PlayerProfileCreate(BaseModel):
    display_name: str
    birth_year: Optional[int] = None
    age_bracket: Optional[str] = None
    dietary_notes: Optional[str] = None
    hydration_notes: Optional[str] = None
    injury_notes: Optional[str] = None


class PlayerProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    birth_year: Optional[int] = None
    age_bracket: Optional[str] = None
    dietary_notes: Optional[str] = None
    hydration_notes: Optional[str] = None
    injury_notes: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", summary="List player profiles")
def list_player_profiles(
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> list[dict[str, Any]]:
    """Return all player profiles visible to the authenticated user (RLS-filtered)."""
    result = client.table(_TABLE).select("*").execute()
    return result.data


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create player profile")
def create_player_profile(
    body: PlayerProfileCreate,
    user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Create a new player profile owned by the authenticated caller."""
    payload = body.model_dump(exclude_none=True)
    payload["user_id"] = str(user_id)  # required: NOT NULL, no DEFAULT; RLS enforces owner
    result = client.table(_TABLE).insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Insert returned no data")
    return result.data[0]


@router.get("/{profile_id}", summary="Get player profile")
def get_player_profile(
    profile_id: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Fetch a single player profile by ID (RLS enforces ownership)."""
    result = client.table(_TABLE).select("*").eq("id", str(profile_id)).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Profile not found")
    return result.data[0]


@router.put("/{profile_id}", summary="Update player profile")
def update_player_profile(
    profile_id: UUID,
    body: PlayerProfileUpdate,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Update a player profile. RLS ensures only the owner can update."""
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="No fields to update")
    result = (
        client.table(_TABLE).update(payload).eq("id", str(profile_id)).execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Profile not found or not owned by caller")
    return result.data[0]


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT,
               response_class=Response,
               summary="Delete player profile")
def delete_player_profile(
    profile_id: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Response:
    """Delete a player profile. RLS enforces ownership."""
    client.table(_TABLE).delete().eq("id", str(profile_id)).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
