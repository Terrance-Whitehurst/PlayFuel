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

from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel
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
    # camelCase aliases: iOS sends scheduledStart, ageBracket, displayOrder, etc.
    # populate_by_name=True allows both snake_case (tests) and camelCase (iOS).
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    scheduled_start: datetime
    round: int                              # required — players still alive (32=R32, 8=QF, 2=Final)
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
    # camelCase aliases: iOS sends scheduledStart, ageBracket, doublesFormat, etc.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    scheduled_start: Optional[datetime] = None
    round: Optional[int] = None             # optional for partial update
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
    # match-done-state-cards spec §C — migration 0017
    is_done: Optional[bool] = None
    done_at: Optional[datetime] = None

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


def _validate_scheduled_start_in_range(
    scheduled_start: datetime,
    start_date_str: str,
    end_date_str: Optional[str],
) -> None:
    """Validate that scheduled_start falls within the tournament date range (inclusive).

    Date-level comparison only — no venue_tz field exists in the tournament schema.
    We extract the date portion of scheduled_start directly (.date()), which is
    UTC-aligned for tz-aware datetimes and local-naive for naive datetimes. For
    the vast majority of daylight tennis matches this is accurate. Adding a
    venue_tz field to remove the UTC-midnight edge case is tracked as OQ-DATE-1.

    end_date defaults to start_date when null (single-day tournament).
    """
    match_date = scheduled_start.date()
    t_start = date.fromisoformat(start_date_str)
    t_end = date.fromisoformat(end_date_str) if end_date_str else t_start
    if not (t_start <= match_date <= t_end):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Match start must fall within the tournament date range "
                f"({t_start.isoformat()} through {t_end.isoformat()} inclusive)."
            ),
        )


def _validate_round_progression(
    tournament_id: UUID,
    match_format: Optional[str],
    round_value: int,
    client: Client,
    exclude_match_id: Optional[UUID] = None,
) -> None:
    """Reject if another match in the same stream already has this round value.

    'Stream' is defined by (tournament_id, format). Enforces the no-duplicate
    invariant per round-progression-and-formats.md §D.4. Linear-progression
    (R64→R32→…) is enforced on the iOS side, not here.

    Skipped entirely when match_format is None (stream undetermined — caller did
    not supply format, so we cannot determine which stream to check).
    """
    if match_format is None:
        return
    query = (
        client.table(_TABLE)
        .select("id")
        .eq("tournament_id", str(tournament_id))
        .eq("format", match_format)
        .eq("round", round_value)
    )
    if exclude_match_id is not None:
        query = query.neq("id", str(exclude_match_id))
    result = query.limit(1).execute()
    if result.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Round {round_value} already exists for {match_format} in this tournament. "
                "Use a different round or edit the existing match."
            ),
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
        .select("draw_size,start_date,end_date")
        .eq("id", str(tid))
        .limit(1)
        .execute()
    )
    if not t_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found",
        )
    t_row = t_result.data[0]
    draw_size: int = t_row["draw_size"]
    if body.round > draw_size:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"round {body.round} exceeds tournament draw size {draw_size}",
        )
    # Date range validation — scheduled_start must fall within [start_date, end_date] inclusive.
    # .get() guards against sparse mock dicts in unit tests (production rows always have start_date).
    t_start_str: Optional[str] = t_row.get("start_date")
    if t_start_str is not None:
        _validate_scheduled_start_in_range(
            body.scheduled_start,
            t_start_str,
            t_row.get("end_date"),
        )
    # Round progression: no duplicate round per (tournament, format) stream — §D.4
    _validate_round_progression(
        tournament_id=tid,
        match_format=body.format,
        round_value=body.round,
        client=client,
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
    # Date range validation when scheduled_start is being changed.
    if body.scheduled_start is not None:
        t_res = (
            client.table("tournaments")
            .select("start_date,end_date")
            .eq("id", str(tid))
            .limit(1)
            .execute()
        )
        if t_res.data:
            t_start_str: Optional[str] = t_res.data[0].get("start_date")
            if t_start_str:
                _validate_scheduled_start_in_range(
                    body.scheduled_start,
                    t_start_str,
                    t_res.data[0].get("end_date"),
                )
    # Round progression: no duplicate round per (tournament, format) stream — §D.4
    if body.round is not None:
        _validate_round_progression(
            tournament_id=tid,
            match_format=body.format,
            round_value=body.round,
            client=client,
            exclude_match_id=mid,
        )
    # match-done-state-cards spec §C: handle is_done / done_at flip logic
    if body.is_done is True and body.done_at is None:
        # false → true transition with no explicit done_at: server sets it now
        payload["done_at"] = datetime.now(timezone.utc).isoformat()
    elif body.is_done is False:
        # undo: always clear done_at regardless of any client-provided value
        payload["done_at"] = None
    # When is_done is None (not in payload) or done_at is explicitly provided, pass through
    # UUID → string for PostgREST
    if payload.get("opponent_player_id") is not None:
        payload["opponent_player_id"] = str(payload["opponent_player_id"])
    for k in ("scheduled_start", "actual_end_at", "done_at"):
        if k in payload and payload[k] is not None and isinstance(payload[k], datetime):
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
    """Delete a match. RLS enforces ownership.

    Filters on both id AND tournament_id so a match from a different tournament
    (or one not owned by the caller, per RLS) returns 404 — not 204 — per spec §C.1.
    """
    result = (
        client.table(_TABLE)
        .delete()
        .eq("id", str(mid))
        .eq("tournament_id", str(tid))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Match not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
