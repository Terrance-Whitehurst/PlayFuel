"""Post-match evaluation → player note synchronisation.

When a match_evaluation is created or updated with non-empty opponent_observations
AND the match has opponent_player_id set, we idempotently UPSERT a player_note row
keyed by (player_id, match_id, source='post_match').

Design decisions (POST_MATCH_EVAL_V1.md §D):
  - NO sanitisation here — body is stored as-is (parent's authentic words).
    Sanitisation fires at plan-generation time via services/scouting.py.
  - If the note already exists for this (player_id, match_id, source='post_match'),
    UPDATE it rather than INSERT a duplicate. Re-saving the eval never grows
    player_notes count.
  - Exceptions are logged but NOT re-raised — the eval write is the primary
    operation; a sync failure is background. (OQ-EVAL-3)
  - Also exports delete_post_match_note() for the DELETE evaluation endpoint
    to clean up the corresponding auto-created note.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

_NOTES_TABLE = "player_notes"
_SOURCE = "post_match"


def sync_player_note_from_eval(
    eval_row: dict[str, Any],
    match_row: dict[str, Any],
    client: Any,
) -> None:
    """Idempotently UPSERT a player_note from a match evaluation's opponent observations.

    Skips silently when:
      - match_row has no opponent_player_id (None or absent)
      - eval_row.opponent_observations is None or whitespace-only

    On subsequent saves of the same eval (re-POST / PATCH), the existing note
    is UPDATE-d so the body stays current. No duplicate rows are created.

    Args:
        eval_row:   Full match_evaluations row dict (from Supabase response data[0]).
        match_row:  Full matches row dict (fetched by the route to supply opp_player_id).
        client:     Supabase RLS-scoped client (already authed to the current user).
    """
    opp_player_id: str | None = match_row.get("opponent_player_id")
    obs: str = (eval_row.get("opponent_observations") or "").strip()

    if not opp_player_id or not obs:
        return   # nothing to sync

    match_id_str: str = str(eval_row["match_id"])
    user_id_str: str = str(eval_row["user_id"])

    try:
        # Check if a post_match note already exists for this (player_id, match_id)
        existing = (
            client.table(_NOTES_TABLE)
            .select("id")
            .eq("player_id", str(opp_player_id))
            .eq("match_id", match_id_str)
            .eq("source", _SOURCE)
            .limit(1)
            .execute()
        )

        if existing.data:
            # UPDATE existing note body
            note_id = existing.data[0]["id"]
            client.table(_NOTES_TABLE).update({"body": obs}).eq("id", note_id).execute()
            logger.debug(
                "sync_player_note_from_eval: updated note %s for match %s",
                note_id,
                match_id_str,
            )
        else:
            # INSERT new note
            client.table(_NOTES_TABLE).insert(
                {
                    "player_id": str(opp_player_id),
                    "user_id": user_id_str,
                    "source": _SOURCE,
                    "body": obs,
                    "match_id": match_id_str,
                }
            ).execute()
            logger.debug(
                "sync_player_note_from_eval: created note for player %s / match %s",
                opp_player_id,
                match_id_str,
            )

    except Exception:  # noqa: BLE001
        logger.exception(
            "sync_player_note_from_eval: failed for match_id=%s — eval write still succeeded",
            match_id_str,
        )


def delete_post_match_note(match_id: UUID, client: Any) -> None:
    """Delete the auto-created post_match player_note for a given match_id.

    Called from DELETE /v1/matches/{mid}/evaluation to keep the player_notes
    table in sync when an evaluation is deleted.

    Silently no-ops if no such note exists (eval was created without opp obs).
    """
    match_id_str = str(match_id)
    try:
        client.table(_NOTES_TABLE).delete().eq("match_id", match_id_str).eq(
            "source", _SOURCE
        ).execute()
        logger.debug(
            "delete_post_match_note: removed post_match note(s) for match_id=%s",
            match_id_str,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "delete_post_match_note: failed for match_id=%s", match_id_str
        )
