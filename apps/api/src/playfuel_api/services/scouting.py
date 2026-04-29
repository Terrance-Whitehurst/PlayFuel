"""Player scouting services — opponent notes sanitization and fetch.

Sanitization pipeline (applied before any note reaches PlanExplanationInput):
  1. Strip URLs           (re.sub(r'https?://\S+', '', text))
  2. Strip email patterns (re.sub(r'\S+@\S+\.\S+', '', text))
  3. Strip phone patterns (re.sub(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '', text))
  4. Truncate to 200 chars
  5. Scan for §C prohibited phrases (via llm_safety.contains_prohibited_phrase)
     → If any match, return None (caller drops the note)

Order matters: strip URL/email/phone BEFORE truncating to 200 chars so that
partial URL fragments cannot leak through the truncation boundary.

Notes where sanitize_note_for_llm returns None are dropped entirely from the
list passed to PlanExplanationInput — they carry zero signal and may confuse
the template.

References: PLAYER_SCOUTING_V1.md §D.2 – §D.3
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playfuel_api.models.api import OpponentNoteForLLM
    from playfuel_api.models.db import MatchRow, PlayerNoteRow

# ── Sanitization regexes ──────────────────────────────────────────────────────

_URL_RE = re.compile(r'https?://\S+')
_EMAIL_RE = re.compile(r'\S+@\S+\.\S+')
_PHONE_RE = re.compile(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b')

_MAX_NOTE_CHARS = 200


def sanitize_note_for_llm(body: str) -> Optional[str]:
    """Strip PII patterns, truncate to 200 chars, scan for §C prohibited phrases.

    Returns:
        Sanitized text (≤200 chars) if safe.
        None if a §C prohibited phrase was found — caller should drop this note.

    Order: strip → truncate → scan. This ensures a partial URL at position 195
    doesn't slip through after truncation.
    """
    text = _URL_RE.sub('', body)
    text = _EMAIL_RE.sub('', text)
    text = _PHONE_RE.sub('', text)
    text = text[:_MAX_NOTE_CHARS].strip()

    from playfuel_api.services.llm_safety import contains_prohibited_phrase
    if contains_prohibited_phrase(text):
        return None

    return text


def build_opponent_note_for_llm(
    note_row: "PlayerNoteRow",
    now: datetime,
) -> Optional["OpponentNoteForLLM"]:
    """Build a sanitized OpponentNoteForLLM from a PlayerNoteRow.

    Returns None if the note should be redacted (prohibited phrase detected).
    Callers should skip None results.
    """
    from playfuel_api.models.api import OpponentNoteForLLM

    sanitized = sanitize_note_for_llm(note_row.body)
    if sanitized is None:
        return None

    # Ensure created_at is tz-aware for subtraction.
    created = note_row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - created).days)

    return OpponentNoteForLLM(
        source=note_row.source,
        age_days=age_days,
        body_paraphrasable=sanitized,
    )


def fetch_opponent_notes_for_match(
    match_row: "MatchRow",
    client,  # supabase Client (sync) — same pattern as routes/plans.py
    now: Optional[datetime] = None,
) -> "list[OpponentNoteForLLM]":
    """Fetch and sanitize opponent notes for a given match.

    Steps:
      1. Check match_row.opponent_player_id. If None, return [].
      2. Query player_notes for that player (RLS-scoped; up to 5 most recent).
      3. Sanitize each note via build_opponent_note_for_llm.
      4. Drop None results (redacted notes).
      5. Return list (may be empty).

    The Supabase client is already auth-scoped via Depends(authed_client), so
    RLS filters player_notes to the current user's players automatically.
    """
    from playfuel_api.models.db import PlayerNoteRow

    if match_row.opponent_player_id is None:
        return []

    if now is None:
        now = datetime.now(tz=timezone.utc)

    try:
        result = (
            client.table("player_notes")
            .select("*")
            .eq("player_id", str(match_row.opponent_player_id))
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
    except Exception:  # noqa: BLE001
        return []

    notes: list["OpponentNoteForLLM"] = []
    for row_data in (result.data or []):
        try:
            note_row = PlayerNoteRow(**row_data)
            note = build_opponent_note_for_llm(note_row, now)
            if note is not None:
                notes.append(note)
        except Exception:  # noqa: BLE001
            continue

    return notes
