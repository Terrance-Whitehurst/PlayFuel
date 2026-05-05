"""Post-tournament feedback CRUD — /v1/tournaments/{tid}/feedback.

Auth required on all endpoints. Ownership enforced at the route level (404
on tournament-not-found or not-owned) and by RLS as a second layer.

Endpoints:
    POST   /v1/tournaments/{tid}/feedback   UPSERT feedback (201 create / 200 update)
    GET    /v1/tournaments/{tid}/feedback   Fetch own feedback (200 / 404 if none)

UPSERT semantics:
    The unique constraint ``feedback_tournament_user_uq`` on
    ``(tournament_id, user_id)`` means one feedback row per parent per
    tournament. A second POST updates the row in-place and returns 200.
    We distinguish create vs update by checking whether the row existed before
    the write (SELECT-then-UPSERT pattern — simple and RLS-safe).

Security note:
    Both endpoints return 404 (never 403) when a tournament is not found or
    not owned by the caller. This prevents info-leak: the caller cannot tell
    whether a tournament_id belongs to another user or simply doesn't exist.

See phase7-feedback-spec.md §C for the full API contract.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client
from playfuel_api.models.api import FeedbackCreate, FeedbackResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tournaments", tags=["feedback"])

_FEEDBACK_TABLE = "feedback"
_TOURNAMENTS_TABLE = "tournaments"
_PLANS_TABLE = "plans"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_tournament_or_404(tid: UUID, user_id: UUID, client: Client) -> dict[str, Any]:
    """Verify the tournament exists and belongs to the caller.

    Returns the tournament row on success.
    Raises HTTP 404 on not-found or ownership mismatch — no 403 to avoid
    leaking information about tournaments owned by other users.
    """
    result = (
        client.table(_TOURNAMENTS_TABLE)
        .select("id, user_id")
        .eq("id", str(tid))
        .limit(1)
        .execute()
    )
    if not result.data:
        logger.info("feedback 404: tournament_id=%s not found", str(tid))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found",
        )
    row = result.data[0]
    # RLS already enforces user_id scoping, but we do an explicit check so the
    # error surface is 404 regardless (no 403 info-leak).
    if row.get("user_id") != str(user_id):
        logger.info("feedback 404: tournament_id=%s ownership mismatch", str(tid))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tournament not found",
        )
    return row


def _get_latest_plan_id(tid: UUID, client: Client) -> str | None:
    """Look up the most recently generated plan for this tournament.

    Returns the plan UUID as a string, or None if no plans exist.
    The plan_id on the feedback row is informational — feedback survives
    plan deletion (ON DELETE SET NULL in migration 0013).
    """
    result = (
        client.table(_PLANS_TABLE)
        .select("id")
        .eq("tournament_id", str(tid))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"]
    return None


def _get_feedback_row(tid: UUID, user_id: UUID, client: Client) -> dict[str, Any] | None:
    """Fetch the feedback row for this (tournament, user) pair. None if not yet created."""
    result = (
        client.table(_FEEDBACK_TABLE)
        .select("*")
        .eq("tournament_id", str(tid))
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post(
    "/{tid}/feedback",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
    summary="Submit or update tournament feedback (UPSERT)",
)
def submit_feedback(
    tid: UUID,
    body: FeedbackCreate,
    user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> Response:
    """Submit post-tournament feedback for a tournament.

    First submission → HTTP 201 (Created).
    Re-submission (same parent, same tournament) → HTTP 200 (OK), row updated.

    The ``plan_id`` field on the stored row is set to the most recently
    generated plan for this tournament (nullable — cleared to NULL if the plan
    is later deleted, but the feedback row itself persists).

    Returns ``FeedbackResponse`` in both 201 and 200 cases.
    """
    # Verify tournament ownership (404 on mismatch — no info-leak)
    _get_tournament_or_404(tid, user_id, client)

    # Resolve latest plan_id for audit linkage (nullable, best-effort)
    latest_plan_id = _get_latest_plan_id(tid, client)

    # Determine whether this is a create or update
    existing = _get_feedback_row(tid, user_id, client)
    is_create = existing is None

    payload: dict[str, Any] = {
        "tournament_id": str(tid),
        "user_id": str(user_id),
        "plan_id": latest_plan_id,
        "what_worked": body.what_worked,
        "what_didnt_work": body.what_didnt_work,
    }
    if body.overall_rating is not None:
        payload["overall_rating"] = body.overall_rating
    if body.free_text is not None:
        payload["free_text"] = body.free_text

    # FB-F1 fix: use DB-level upsert instead of SELECT-then-INSERT/UPDATE.
    # The old pattern raced on concurrent submits (double-tap): both requests
    # could observe is_create=True, both attempt INSERT, second hits the
    # UNIQUE(tournament_id, user_id) constraint -> 500 APIError 23505.
    # upsert(on_conflict=...) handles the conflict atomically in Postgres.
    # We still run the pre-check SELECT (_get_feedback_row above) to determine
    # the 201/200 status code semantics; the race only affects the write, not
    # the status code, and double-tap is a UX concern not a data-integrity one.
    result = (
        client.table(_FEEDBACK_TABLE)
        .upsert(payload, on_conflict="tournament_id,user_id")
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feedback write returned no data",
        )

    feedback_row = result.data[0]
    http_status = status.HTTP_201_CREATED if is_create else status.HTTP_200_OK

    # FB-LOG-1: wire operational INFO logs (no free_text — user content stays out of logs).
    logger.info(
        "feedback %s: tournament_id=%s rating=%s",
        "created" if is_create else "updated",
        str(tid),
        body.overall_rating,
    )

    return Response(
        content=FeedbackResponse(**feedback_row).model_dump_json(by_alias=True),
        status_code=http_status,
        media_type="application/json",
    )


@router.get(
    "/{tid}/feedback",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
    summary="Get own tournament feedback",
)
def get_feedback(
    tid: UUID,
    user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Fetch the caller's feedback for a tournament.

    Returns HTTP 200 + ``FeedbackResponse`` if feedback exists.
    Returns HTTP 404 if:
      - The tournament does not exist
      - The tournament is not owned by the caller
      - No feedback has been submitted yet

    The same 404 is returned for all three cases to prevent info-leak.
    """
    # Verify tournament ownership first
    _get_tournament_or_404(tid, user_id, client)

    # Look up the feedback row
    feedback_row = _get_feedback_row(tid, user_id, client)
    if feedback_row is None:
        logger.info("feedback 404: no row found for tournament_id=%s", str(tid))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feedback found for this tournament",
        )

    return feedback_row
