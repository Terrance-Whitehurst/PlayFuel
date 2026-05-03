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
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client
from playfuel_api.rules.constants import ROUND_LABELS, VALID_ROUNDS

router = APIRouter(prefix="/v1/tournaments", tags=["matches"])

_TABLE = "matches"


# ── Request bodies ────────────────────────────────────────────────────────────

# Valid doubles format values
_VALID_DOUBLES_FORMATS = {"best_of_3", "pro_set_8"}


class MatchCreate(BaseModel):
    scheduled_start: datetime
    round: int                              # required — players still alive (32=R32, 8=QF, 2=Final)
    estimated_duration_minutes: Optional[int] = None
    surface: Optional[str] = None
    format: Optional[str] = None            # 'singles' | 'doubles'
    age_bracket: Optional[str] = None
    display_order: Optional[int] = None
    round_label: Optional[str] = None      # kept for back-compat; server ALWAYS overwrites from round
    opponent_label: Optional[str] = None
    court_label: Optional[str] = None
    # Doubles-spec extension — migration 0007_doubles_support.sql
    doubles_format: Optional[str] = None   # 'best_of_3' | 'pro_set_8'; null when format != 'doubles'
    # Player scouting extension — migration 0010_players_and_notes.sql
    opponent_player_id: Optional[UUID] = None  # FK to players.id; SET NULL on player delete

    @field_validator("round")
    @classmethod
    def validate_round(cls, v: int) -> int:
        if v not in VALID_ROUNDS:
            raise ValueError(f"round must be one of {sorted(VALID_ROUNDS)}")
        return v


class MatchUpdate(BaseModel):
    scheduled_start: Optional[datetime] = None
    round: Optional[int] = None             # optional for partial update
    estimated_duration_minutes: Optional[int] = None
    actual_end_at: Optional[datetime] = None
    surface: Optional[str] = None
    format: Optional[str] = None            # 'singles' | 'doubles'
    age_bracket: Optional[str] = None
    display_order: Optional[int] = None
    round_label: Optional[str] = None
    opponent_label: Optional[str] = None
    court_label: Optional[str] = None
    # Doubles-spec extension
    doubles_format: Optional[str] = None   # 'best_of_3' | 'pro_set_8'; null when format != 'doubles'
    # Player scouting extension
    opponent_player_id: Optional[UUID] = None  # FK to players.id

    @field_validator("round")
    @classmethod
    def validate_round(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in VALID_ROUNDS:
            raise ValueError(f"round must be one of {sorted(VALID_ROUNDS)}")
        return v


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


def _validate_opponent_player_id(
    opponent_player_id: Optional[UUID],
    client: Client,
) -> None:
    """Verify that opponent_player_id, if provided, belongs to the current user.

    Uses RLS-scoped client: if the player exists but belongs to a different user,
    RLS returns empty results and we raise 404 (don't leak existence).
    """
    if opponent_player_id is None:
        return
    result = (
        client.table("players")
        .select("id")
        .eq("id", str(opponent_player_id))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found or not owned by you",
        )


def _validate_doubles_format(format_val: Optional[str], doubles_format: Optional[str]) -> None:
    """Validate that doubles_format is consistent with the match format field.

    Rules (DOUBLES_SPEC_V1.md §A.2):
    - format == 'doubles' → doubles_format MUST be 'best_of_3' or 'pro_set_8'
    - format != 'doubles' → doubles_format MUST be null
    """
    if format_val == "doubles":
        if doubles_format not in _VALID_DOUBLES_FORMATS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"doubles_format must be one of {sorted(_VALID_DOUBLES_FORMATS)} "
                    "when format is 'doubles'. "
                    f"Got: {doubles_format!r}"
                ),
            )
    elif doubles_format is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "doubles_format must be null when format is not 'doubles'. "
                f"Got format={format_val!r}, doubles_format={doubles_format!r}"
            ),
        )


@router.post("/{tid}/matches", status_code=status.HTTP_201_CREATED,
             summary="Create match")
def create_match(
    tid: UUID,
    body: MatchCreate,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Create a match under a tournament. RLS verifies tournament ownership."""
    _validate_doubles_format(body.format, body.doubles_format)
    _validate_opponent_player_id(body.opponent_player_id, client)

    # Cross-table round validation: round must not exceed the tournament's draw_size.
    # Postgres CHECK on matches.round only validates the value is a power-of-2 bracket size;
    # it cannot subquery across tables. Enforced here (draw-size-spec.md §4.2).
    t_result = (
        client.table("tournaments")
        .select("draw_size")
        .eq("id", str(tid))
        .limit(1)
        .execute()
    )
    if not t_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found",
        )
    draw_size: int = t_result.data[0]["draw_size"]
    if body.round > draw_size:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"round {body.round} exceeds tournament draw size {draw_size}",
        )

    payload = body.model_dump(exclude_none=True)
    payload["tournament_id"] = str(tid)
    # Server is source of truth for round_label — always overwrite from the numeric round.
    payload["round_label"] = ROUND_LABELS[body.round]
    # UUID → string for PostgREST
    if payload.get("opponent_player_id") is not None:
        payload["opponent_player_id"] = str(payload["opponent_player_id"])
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
    _validate_doubles_format(body.format, body.doubles_format)
    _validate_opponent_player_id(body.opponent_player_id, client)
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="No fields to update")
    # UUID → string for PostgREST
    if payload.get("opponent_player_id") is not None:
        payload["opponent_player_id"] = str(payload["opponent_player_id"])
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
               response_class=Response,
               summary="Delete match")
def delete_match(
    tid: UUID,
    mid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Response:
    """Delete a match. RLS enforces ownership."""
    client.table(_TABLE).delete().eq("id", str(mid)).eq("tournament_id", str(tid)).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
