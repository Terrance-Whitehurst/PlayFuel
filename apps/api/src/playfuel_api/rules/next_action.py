"""Deterministic 'what's next' derivation — NUTRITION_FIRST_IA_V1.md §D.

Pure rules engine. NEVER LLM-generated.

Algorithm:
  1. Parse each timeline event's time string to a timezone-aware datetime.
  2. Filter to events in (now, now + lookahead_hours].
  3. Sort ascending by event time.
  4. Take the first event as the next action.
  5. Compute mins_until = floor((event_time - now).total_seconds() / 60).
  6. Look up detail in NEXT_ACTION_COPY_MAP; fall back to event.title if kind
     is not in the map.
  7. If extreme_heat_risk and event.kind in HEAT_SENSITIVE_KINDS, prepend
     "Extreme heat — extra hydration. " to detail (verbatim, never replace).
  8. If no event in window: return recovery_fallback NextAction.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playfuel_api.models.api import NextAction, TimelineEventOut

# ── Copy map (hardcoded, NUTRITION_FIRST_IA_V1.md §D.4) ─────────────────────
# Keys are TimelineEventKind string values (camelCase, matching models/enums.py).
# "recovery_fallback" is a string literal (no DB enum entry per OQ-IA-7).

NEXT_ACTION_COPY_MAP: dict[str, str] = {
    # Canonical TimelineEventKind.value strings
    "match":                "Head to court — match starting soon",
    "warmUp":               "Begin warm-up with your player",
    "meal":                 "Light, easy carbs — see food options below",
    "hydration":            "Offer water or electrolyte drink now",
    "foodWindow":           "Time to pick up food — see options below",
    "pickup":               "Head out now for pickup — see food options below",
    "recovery":             "Refuel within 30 min — see food options below",
    "matchEnd":             "Match over — begin recovery routine",
    "partnerCoordination":  "Confirm warm-up time with your player's partner",
    # Fallback copy
    "recovery_fallback":    "Refuel within 30 min — see food options below",
}

# Kinds that get the heat prepend when extreme_heat_risk=True.
# Values must match TimelineEventKind string values exactly (camelCase).
HEAT_SENSITIVE_KINDS: frozenset[str] = frozenset({
    "match",    # TimelineEventKind.match
    "warmUp",   # TimelineEventKind.warmUp
    "hydration",  # TimelineEventKind.hydration
})

_HEAT_PREPEND: str = "Extreme heat — extra hydration. "

_FALLBACK_TITLE: str = "Recovery"
_FALLBACK_KIND: str = "recovery_fallback"


def _parse_event_time(time_str: str) -> Optional[datetime]:
    """Parse ISO 8601 string from TimelineEventOut.time → timezone-aware datetime.

    Returns None on parse failure so the event is silently skipped.
    """
    try:
        clean = time_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        # Ensure timezone-aware (assume UTC if naive)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:  # noqa: BLE001
        return None


def derive_next_action(
    timeline: "list[TimelineEventOut]",
    now: datetime,
    extreme_heat_risk: bool = False,
    lookahead_hours: int = 6,
) -> "NextAction":
    """Pick the most actionable next event from the plan timeline.

    Args:
        timeline:          list[TimelineEventOut] from plan.timeline.
        now:               Server clock at generation time (inject for testability).
                           Should be timezone-aware (UTC).
        extreme_heat_risk: When True, prepend heat warning on sensitive event kinds.
        lookahead_hours:   How far ahead to look (default 6h per NUTRITION_FIRST_IA_V1 §D).

    Returns:
        NextAction — always non-None; falls back to recovery_fallback copy when
        no qualifying event is found in the window.
    """
    from playfuel_api.models.api import NextAction  # deferred to avoid circular

    # Ensure 'now' is timezone-aware
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    horizon = now + timedelta(hours=lookahead_hours)

    # Parse + filter upcoming events within the lookahead window.
    upcoming: list[tuple[datetime, "TimelineEventOut"]] = []
    for event in timeline:
        event_dt = _parse_event_time(event.time)
        if event_dt is None:
            continue
        if now < event_dt <= horizon:
            upcoming.append((event_dt, event))

    if upcoming:
        # Sort ascending — pick the soonest event.
        upcoming.sort(key=lambda x: x[0])
        event_dt, event = upcoming[0]

        kind: str = event.kind.value if hasattr(event.kind, "value") else str(event.kind)
        detail: str = NEXT_ACTION_COPY_MAP.get(kind, event.title)

        if extreme_heat_risk and kind in HEAT_SENSITIVE_KINDS:
            detail = _HEAT_PREPEND + detail

        mins_until: int = int((event_dt - now).total_seconds() // 60)

        return NextAction(
            title=event.title,
            detail=detail,
            scheduled_for=event_dt,
            kind=kind,
            mins_until=mins_until,
        )

    # No upcoming event in window — return deterministic recovery fallback.
    return NextAction(
        title=_FALLBACK_TITLE,
        detail=NEXT_ACTION_COPY_MAP[_FALLBACK_KIND],
        scheduled_for=None,
        kind=_FALLBACK_KIND,
        mins_until=None,
    )
