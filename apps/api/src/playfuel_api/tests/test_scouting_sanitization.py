"""Sanitization pipeline tests — services/scouting.py.

Covers:
  - URL stripping
  - Email stripping
  - Phone number stripping
  - 200-char truncation
  - §C prohibited-phrase scan triggers redaction
  - Combined attack input: email + prohibited phrase → fully redacted
  - contains_prohibited_phrase helper (extracted from llm_safety.py)
  - build_opponent_note_for_llm age_days computation
  - fetch_opponent_notes_for_match returns [] when opponent_player_id is None
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from playfuel_api.services.llm_safety import contains_prohibited_phrase
from playfuel_api.services.scouting import (
    build_opponent_note_for_llm,
    fetch_opponent_notes_for_match,
    sanitize_note_for_llm,
)


# ── sanitize_note_for_llm ─────────────────────────────────────────────────────


def test_sanitize_strips_url():
    """URL in note body is removed."""
    body = "Check his profile at https://example.com/player for more info."
    result = sanitize_note_for_llm(body)
    assert result is not None
    assert "https" not in result
    assert "example.com" not in result


def test_sanitize_strips_email():
    """Email pattern in note body is removed."""
    body = "Contact his coach at coach@example.com to confirm schedule."
    result = sanitize_note_for_llm(body)
    assert result is not None
    assert "@" not in result or "coach@example.com" not in result


def test_sanitize_strips_phone():
    """10-digit phone number in note body is removed."""
    body = "Call the tournament desk at 214-555-1234 for details."
    result = sanitize_note_for_llm(body)
    assert result is not None
    assert "214-555-1234" not in result


def test_sanitize_strips_phone_dotted():
    """Phone with dot separators is also stripped."""
    body = "Reach at 972.555.0199 or via text."
    result = sanitize_note_for_llm(body)
    assert result is not None
    assert "972.555.0199" not in result


def test_sanitize_truncates_200_chars():
    """Long note body is truncated to 200 chars."""
    body = "a" * 300
    result = sanitize_note_for_llm(body)
    assert result is not None
    assert len(result) <= 200


def test_sanitize_preserves_tactical_content():
    """Normal tactical note passes through unchanged."""
    body = "Moves well to the right side. Slice backhand is strong under pressure."
    result = sanitize_note_for_llm(body)
    assert result is not None
    assert "backhand" in result


def test_sanitize_prohibited_phrase_redacts():
    """Note containing a §C prohibited phrase → None (redacted)."""
    body = "His training guarantees better performance in the heat."
    result = sanitize_note_for_llm(body)
    assert result is None, "Expected None for note containing 'guarantees better performance'"


def test_sanitize_combined_attack_redacted():
    """Email + prohibited phrase in same note → fully redacted (None).

    Even after stripping the email, the prohibited phrase 'guarantees better performance'
    remains in the sanitized text → the note is redacted.
    """
    body = "Email me at foo@bar.com — guarantees better performance in hot conditions."
    # After email strip: "Email me at  — guarantees better performance in hot conditions."
    # 'guarantees better performance' is in PROHIBITED_PHRASES → None
    result = sanitize_note_for_llm(body)
    assert result is None, "Combined email + prohibited phrase must be fully redacted"


def test_sanitize_prohibited_phrase_case_insensitive():
    """Prohibited phrase matching is case-insensitive."""
    body = "This WILL PREVENT cramps in hot weather."
    result = sanitize_note_for_llm(body)
    assert result is None, "Case-insensitive match should redact 'WILL PREVENT'"


# ── contains_prohibited_phrase helper ─────────────────────────────────────────


def test_contains_prohibited_phrase_true():
    """Helper returns True for a phrase from PROHIBITED_PHRASES."""
    assert contains_prohibited_phrase("This guarantees better performance tomorrow.") is True


def test_contains_prohibited_phrase_false():
    """Helper returns False for clean tactical text."""
    assert contains_prohibited_phrase("Good backhand under pressure.") is False


def test_contains_prohibited_phrase_empty_string():
    """Helper returns False for empty string."""
    assert contains_prohibited_phrase("") is False


# ── build_opponent_note_for_llm ────────────────────────────────────────────────


def test_build_opponent_note_age_days():
    """age_days is computed correctly from created_at."""
    from playfuel_api.models.db import PlayerNoteRow

    note_row = PlayerNoteRow(
        id=uuid4(),
        player_id=uuid4(),
        user_id=uuid4(),
        source="observed",
        body="Strong serve.",
        match_id=None,
        created_at=datetime.now(tz=timezone.utc) - timedelta(days=5),
    )
    now = datetime.now(tz=timezone.utc)
    result = build_opponent_note_for_llm(note_row, now)
    assert result is not None
    assert result.age_days == 5


def test_build_opponent_note_prohibited_phrase_returns_none():
    """build_opponent_note_for_llm returns None when note contains §C phrase."""
    from playfuel_api.models.db import PlayerNoteRow

    note_row = PlayerNoteRow(
        id=uuid4(),
        player_id=uuid4(),
        user_id=uuid4(),
        source="secondhand",
        body="Will prevent all errors with this technique.",
        match_id=None,
        created_at=datetime.now(tz=timezone.utc),
    )
    result = build_opponent_note_for_llm(note_row, datetime.now(tz=timezone.utc))
    assert result is None


# ── fetch_opponent_notes_for_match ─────────────────────────────────────────────


def test_fetch_opponent_notes_no_player_id_returns_empty():
    """Returns [] immediately when match has no opponent_player_id."""
    from playfuel_api.models.db import MatchRow

    match = MatchRow(
        id=uuid4(),
        tournament_id=uuid4(),
        scheduled_start=datetime.now(tz=timezone.utc),
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        opponent_player_id=None,
    )
    client = MagicMock()
    result = fetch_opponent_notes_for_match(match, client)
    assert result == []
    client.table.assert_not_called()


def test_fetch_opponent_notes_with_player_id_returns_notes():
    """Returns sanitized notes when opponent_player_id is set."""
    from playfuel_api.models.db import MatchRow

    player_id = uuid4()
    match = MatchRow(
        id=uuid4(),
        tournament_id=uuid4(),
        scheduled_start=datetime.now(tz=timezone.utc),
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        opponent_player_id=player_id,
    )

    note_ts = datetime.now(tz=timezone.utc).isoformat()
    mock_chain = MagicMock()
    mock_chain.execute.return_value.data = [
        {
            "id": str(uuid4()),
            "player_id": str(player_id),
            "user_id": str(uuid4()),
            "source": "observed",
            "body": "Strong forehand down the line.",
            "match_id": None,
            "created_at": note_ts,
        }
    ]
    for attr in ("select", "eq", "order", "limit"):
        getattr(mock_chain, attr).return_value = mock_chain

    client = MagicMock()
    client.table.return_value = mock_chain

    result = fetch_opponent_notes_for_match(match, client)
    assert len(result) == 1
    assert result[0].source == "observed"
    assert "forehand" in result[0].body_paraphrasable


def test_fetch_opponent_notes_db_error_returns_empty():
    """Returns [] gracefully when DB raises an exception."""
    from playfuel_api.models.db import MatchRow

    match = MatchRow(
        id=uuid4(),
        tournament_id=uuid4(),
        scheduled_start=datetime.now(tz=timezone.utc),
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        opponent_player_id=uuid4(),
    )

    client = MagicMock()
    client.table.side_effect = RuntimeError("DB connection lost")

    result = fetch_opponent_notes_for_match(match, client)
    assert result == []
