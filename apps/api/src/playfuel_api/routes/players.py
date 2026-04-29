"""Player scouting CRUD — /v1/players.

Auth required on all endpoints. Ownership enforced by RLS (direct on players;
chain-through for player_notes: note.player_id → players.user_id = auth.uid()).

See PLAYER_SCOUTING_V1.md §C for endpoint spec and error-handling conventions.

Endpoints:
    GET    /v1/players                        list caller's players
    POST   /v1/players                        create player
    GET    /v1/players/{pid}                  get one player (metadata)
    PATCH  /v1/players/{pid}                  update player metadata
    DELETE /v1/players/{pid}                  delete player (cascades notes)
    GET    /v1/players/{pid}/notes            list notes for player (newest first)
    POST   /v1/players/{pid}/notes            add note
    PATCH  /v1/players/{pid}/notes/{nid}      edit note (within 24h window)
    DELETE /v1/players/{pid}/notes/{nid}      delete note
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client
from playfuel_api.models.api import (
    Player,
    PlayerCreate,
    PlayerNote,
    PlayerNoteCreate,
    PlayerNoteUpdate,
    PlayerUpdate,
)

router = APIRouter(prefix="/v1/players", tags=["players"])

_PLAYERS_TABLE = "players"
_NOTES_TABLE = "player_notes"

# Edit window for notes: 24 hours after created_at (OQ-SCOUT-API-2).
_NOTE_EDIT_WINDOW = timedelta(hours=24)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_player_or_404(pid: UUID, client: Client) -> dict[str, Any]:
    """Fetch a player row by ID (RLS-scoped). Raises 404 if not found."""
    result = (
        client.table(_PLAYERS_TABLE)
        .select("*")
        .eq("id", str(pid))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Player not found")
    return result.data[0]


def _get_note_or_404(nid: UUID, pid: UUID, client: Client) -> dict[str, Any]:
    """Fetch a note by ID and player ID (RLS chain-through). Raises 404 if not found."""
    result = (
        client.table(_NOTES_TABLE)
        .select("*")
        .eq("id", str(nid))
        .eq("player_id", str(pid))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Note not found")
    return result.data[0]


def _row_to_player(p: dict[str, Any], note_count: int = 0) -> Player:
    return Player(
        id=UUID(p["id"]),
        user_id=UUID(p["user_id"]),
        display_name=p["display_name"],
        club=p.get("club"),
        city=p.get("city"),
        notes_summary=p.get("notes_summary"),
        note_count=note_count,
        created_at=p["created_at"],
        updated_at=p["updated_at"],
    )


def _row_to_note(n: dict[str, Any]) -> PlayerNote:
    return PlayerNote(
        id=UUID(n["id"]),
        player_id=UUID(n["player_id"]),
        user_id=UUID(n["user_id"]),
        source=n["source"],
        body=n["body"],
        match_id=UUID(n["match_id"]) if n.get("match_id") else None,
        created_at=n["created_at"],
    )


# ── Player CRUD ────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[Player],
    response_model_by_alias=True,
    summary="List players",
)
def list_players(
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> list[Player]:
    """Return all scouted players for the caller (RLS-filtered), ordered by
    updated_at DESC. Includes derived note_count per player."""
    players_result = (
        client.table(_PLAYERS_TABLE)
        .select("*")
        .order("updated_at", desc=True)
        .execute()
    )
    players_data = players_result.data or []
    if not players_data:
        return []

    # Efficient note count: one query for all player IDs, then tally.
    player_ids = [p["id"] for p in players_data]
    note_counts: dict[str, int] = {}
    try:
        notes_result = (
            client.table(_NOTES_TABLE)
            .select("player_id")
            .in_("player_id", player_ids)
            .execute()
        )
        for note in (notes_result.data or []):
            pid_str = note["player_id"]
            note_counts[pid_str] = note_counts.get(pid_str, 0) + 1
    except Exception:  # noqa: BLE001
        pass  # note_count defaults to 0 on failure

    return [_row_to_player(p, note_counts.get(p["id"], 0)) for p in players_data]


@router.post(
    "",
    response_model=Player,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Create player",
)
def create_player(
    body: PlayerCreate,
    user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Player:
    """Create a new scouted player. RLS verifies ownership via user_id."""
    payload: dict[str, Any] = {
        "user_id": str(user_id),
        "display_name": body.display_name,
    }
    if body.club is not None:
        payload["club"] = body.club
    if body.city is not None:
        payload["city"] = body.city
    if body.notes_summary is not None:
        payload["notes_summary"] = body.notes_summary

    result = client.table(_PLAYERS_TABLE).insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Insert returned no data")
    return _row_to_player(result.data[0], note_count=0)


@router.get(
    "/{pid}",
    response_model=Player,
    response_model_by_alias=True,
    summary="Get player",
)
def get_player(
    pid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Player:
    """Fetch a single player. RLS enforces ownership; 404 on miss."""
    p = _get_player_or_404(pid, client)

    # Fetch exact note count for the detail view.
    try:
        notes_result = (
            client.table(_NOTES_TABLE)
            .select("id")
            .eq("player_id", str(pid))
            .execute()
        )
        note_count = len(notes_result.data or [])
    except Exception:  # noqa: BLE001
        note_count = 0

    return _row_to_player(p, note_count=note_count)


@router.patch(
    "/{pid}",
    response_model=Player,
    response_model_by_alias=True,
    summary="Update player",
)
def update_player(
    pid: UUID,
    body: PlayerUpdate,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Player:
    """Update player metadata (display_name, club, city, notes_summary).
    RLS enforces ownership. updated_at is bumped by the DB trigger."""
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )
    result = (
        client.table(_PLAYERS_TABLE)
        .update(payload)
        .eq("id", str(pid))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Player not found")
    return _row_to_player(result.data[0])


@router.delete(
    "/{pid}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete player",
)
def delete_player(
    pid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Response:
    """Delete a player. DB cascade removes all associated player_notes."""
    client.table(_PLAYERS_TABLE).delete().eq("id", str(pid)).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Player Notes CRUD ─────────────────────────────────────────────────────────


@router.get(
    "/{pid}/notes",
    response_model=list[PlayerNote],
    response_model_by_alias=True,
    summary="List notes for player",
)
def list_player_notes(
    pid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> list[PlayerNote]:
    """List all notes for a player, newest first. RLS enforces ownership."""
    # Verify player exists (returns 404 for unknown / unowned players)
    _get_player_or_404(pid, client)

    result = (
        client.table(_NOTES_TABLE)
        .select("*")
        .eq("player_id", str(pid))
        .order("created_at", desc=True)
        .execute()
    )
    return [_row_to_note(n) for n in (result.data or [])]


@router.post(
    "/{pid}/notes",
    response_model=PlayerNote,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Add note",
)
def add_player_note(
    pid: UUID,
    body: PlayerNoteCreate,
    user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> PlayerNote:
    """Add a note for a player. Body ≤ 2000 chars enforced by Pydantic + DB CHECK.
    Optional match_id: if provided, verify the match belongs to the same user."""
    # Verify player ownership
    _get_player_or_404(pid, client)

    # If match_id provided, verify the caller owns that match (via RLS-scoped fetch)
    if body.match_id is not None:
        match_result = (
            client.table("matches")
            .select("id")
            .eq("id", str(body.match_id))
            .limit(1)
            .execute()
        )
        if not match_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Match not found or not owned by you",
            )

    payload: dict[str, Any] = {
        "player_id": str(pid),
        "user_id": str(user_id),
        "source": body.source,
        "body": body.body,
    }
    if body.match_id is not None:
        payload["match_id"] = str(body.match_id)

    result = client.table(_NOTES_TABLE).insert(payload).execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Insert returned no data")
    return _row_to_note(result.data[0])


@router.patch(
    "/{pid}/notes/{nid}",
    response_model=PlayerNote,
    response_model_by_alias=True,
    summary="Edit note (24h window)",
)
def edit_player_note(
    pid: UUID,
    nid: UUID,
    body: PlayerNoteUpdate,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> PlayerNote:
    """Edit a note body. Only allowed within 24h of created_at (OQ-SCOUT-API-2).
    Returns 422 if the edit window has passed."""
    note_data = _get_note_or_404(nid, pid, client)

    # Parse created_at and enforce 24h edit window.
    raw_created = note_data["created_at"]
    if isinstance(raw_created, str):
        created_at = datetime.fromisoformat(raw_created.replace("Z", "+00:00"))
    else:
        created_at = raw_created

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    now = datetime.now(tz=timezone.utc)
    if (now - created_at) > _NOTE_EDIT_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Note cannot be edited after 24 hours",
        )

    result = (
        client.table(_NOTES_TABLE)
        .update({"body": body.body})
        .eq("id", str(nid))
        .eq("player_id", str(pid))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Note not found")
    return _row_to_note(result.data[0])


@router.delete(
    "/{pid}/notes/{nid}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete note",
)
def delete_player_note(
    pid: UUID,
    nid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Response:
    """Delete a note."""
    client.table(_NOTES_TABLE).delete().eq("id", str(nid)).eq("player_id", str(pid)).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
