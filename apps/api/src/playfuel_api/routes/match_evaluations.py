"""Post-match evaluation CRUD — /v1/matches/{mid}/evaluation.

Auth required on all endpoints. Ownership enforced by RLS (two-hop:
match_evaluations.user_id = auth.uid(), plus INSERT/UPDATE chain-check
through match → tournament).

Endpoints:
    GET    /v1/matches/{mid}/evaluation    fetch the evaluation; 404 if none
    POST   /v1/matches/{mid}/evaluation    upsert (201 on create, 200 on update)
    PATCH  /v1/matches/{mid}/evaluation    partial update
    DELETE /v1/matches/{mid}/evaluation    delete eval + auto-created post_match note

POST acts as upsert because match_evaluations has UNIQUE(match_id). A second POST
to the same match replaces the evaluation and returns 200 rather than 409.

Auto-player-note loop (POST_MATCH_EVAL_V1.md §D):
After creating or updating an eval, services.post_match_sync.sync_player_note_from_eval
is called. If the match has opponent_player_id AND opponent_observations is non-empty,
a player_note with source='post_match' is idempotently upserted. Failures are
silently logged — the eval write always wins.

See POST_MATCH_EVAL_V1.md §C for endpoint spec.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client
from playfuel_api.models.api import MatchEvalCreate, MatchEvalUpdate, MatchEvaluation
from playfuel_api.services.post_match_sync import (
    delete_post_match_note,
    sync_player_note_from_eval,
)

router = APIRouter(prefix="/v1/matches", tags=["match_evaluations"])

_EVALS_TABLE = "match_evaluations"
_MATCHES_TABLE = "matches"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_match_or_404(mid: UUID, client: Client) -> dict[str, Any]:
    """Fetch the match row (RLS-scoped). Raises 404 if not found / not owned."""
    result = (
        client.table(_MATCHES_TABLE)
        .select("*")
        .eq("id", str(mid))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found or not owned by caller",
        )
    return result.data[0]


def _get_eval_or_none(mid: UUID, client: Client) -> dict[str, Any] | None:
    """Fetch the evaluation row for this match. Returns None if not yet created."""
    result = (
        client.table(_EVALS_TABLE)
        .select("*")
        .eq("match_id", str(mid))
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _build_eval_payload(body: MatchEvalCreate | MatchEvalUpdate, exclude_none: bool) -> dict[str, Any]:
    """Serialise the request body to a PostgREST-safe dict."""
    payload = body.model_dump(exclude_none=exclude_none)
    # MatchEvalResult enum → string for PostgREST
    if "result" in payload and hasattr(payload["result"], "value"):
        payload["result"] = payload["result"].value
    return payload


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get(
    "/{mid}/evaluation",
    response_model=MatchEvaluation,
    response_model_by_alias=True,
    summary="Get post-match evaluation",
)
def get_evaluation(
    mid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Fetch the evaluation for a match. 404 if not yet created."""
    # Verify match ownership first (gives a clear 404 before the eval query)
    _get_match_or_404(mid, client)

    eval_row = _get_eval_or_none(mid, client)
    if eval_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No evaluation found for this match",
        )
    return eval_row


@router.post(
    "/{mid}/evaluation",
    response_model=MatchEvaluation,
    response_model_by_alias=True,
    summary="Create or update post-match evaluation (upsert)",
)
def create_or_upsert_evaluation(
    mid: UUID,
    body: MatchEvalCreate,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Any:
    """Upsert the evaluation for a match.

    Returns 201 on creation, 200 on update. A second POST to the same match
    replaces the evaluation (UNIQUE constraint on match_id).

    Also fires sync_player_note_from_eval if opponent_observations is non-empty
    and the match has opponent_player_id set.
    """
    match_row = _get_match_or_404(mid, client)

    payload = _build_eval_payload(body, exclude_none=False)
    # Postgres requires explicit nulls in the insert for optional fields
    payload.setdefault("score_text", None)
    payload.setdefault("effort_rating", None)
    payload.setdefault("focus_rating", None)
    payload.setdefault("opponent_observations", None)
    payload.setdefault("key_moments", None)
    payload["match_id"] = str(mid)
    payload["user_id"] = str(_user_id)

    existing = _get_eval_or_none(mid, client)
    is_create = existing is None

    if is_create:
        result = client.table(_EVALS_TABLE).insert(payload).execute()
    else:
        result = (
            client.table(_EVALS_TABLE)
            .update(payload)
            .eq("match_id", str(mid))
            .execute()
        )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation write returned no data",
        )

    eval_row = result.data[0]

    # Auto-player-note loop — silently no-ops if conditions aren't met
    sync_player_note_from_eval(eval_row, match_row, client)

    from fastapi.responses import JSONResponse  # noqa: PLC0415

    status_code = status.HTTP_201_CREATED if is_create else status.HTTP_200_OK
    return Response(
        content=MatchEvaluation(**eval_row).model_dump_json(by_alias=True),
        status_code=status_code,
        media_type="application/json",
    )


@router.patch(
    "/{mid}/evaluation",
    response_model=MatchEvaluation,
    response_model_by_alias=True,
    summary="Partially update post-match evaluation",
)
def patch_evaluation(
    mid: UUID,
    body: MatchEvalUpdate,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Partially update the evaluation for a match. 404 if not yet created."""
    match_row = _get_match_or_404(mid, client)

    # Verify eval exists
    existing = _get_eval_or_none(mid, client)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No evaluation found for this match — POST to create one first",
        )

    payload = _build_eval_payload(body, exclude_none=True)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields provided to update",
        )

    result = (
        client.table(_EVALS_TABLE)
        .update(payload)
        .eq("match_id", str(mid))
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found or not owned by caller",
        )

    eval_row = result.data[0]

    # Re-sync player note with potentially updated opponent_observations
    sync_player_note_from_eval(eval_row, match_row, client)

    return eval_row


@router.delete(
    "/{mid}/evaluation",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete post-match evaluation",
)
def delete_evaluation(
    mid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Response:
    """Delete the evaluation for a match.

    Also deletes any auto-created post_match player_note for this match
    (keyed by match_id + source='post_match'). If no such note exists, silently
    no-ops.
    """
    # Verify ownership (returns 404 if match not owned / not found)
    _get_match_or_404(mid, client)

    client.table(_EVALS_TABLE).delete().eq("match_id", str(mid)).execute()

    # Clean up auto-created player note (silently no-ops if it doesn't exist)
    delete_post_match_note(mid, client)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
