"""Feedback chip vocabulary — version-controlled constants for Phase 7.

These are the authoritative token definitions for the ``what_worked`` and
``what_didnt_work`` arrays on the ``public.feedback`` table.

Design decisions (see phase7-feedback-spec.md §D):
  - Tokens are NEUTRAL identifiers (e.g. ``food_timing``, not
    ``food_timing_helped``). The meaning — "helped" vs "didn't help" — is
    conveyed by which array field the token is stored in.
  - FEEDBACK_CHIPS_WORKED == FEEDBACK_CHIPS_DIDNT_WORK (symmetric vocabulary).
    Both fields accept the same 7 tokens; iOS renders the same chip group in
    each section.
  - Display labels are client-side concerns (see FEEDBACK_CHIP_LABELS below for
    the canonical mapping; iOS must mirror this).
  - Content is version-controlled in Python, NOT a DB lookup table — same
    pattern as ``rules/food.py`` template buckets.

IMPORTANT — SYNC CONTRACT:
  ``FEEDBACK_CHIP_LABELS`` below is the canonical human-readable label mapping.
  iOS ``FeedbackChips.swift`` (apps/ios/PlayFuel/Sources/PlayFuel/Views/)
  MUST stay in sync with this file. If you add or rename a token here,
  update the Swift ``chipLabel(_:)`` function in ``FeedbackChips.swift``.
  (No automated cross-language test; enforced by code review convention.)
"""

from __future__ import annotations

# ── Chip token vocabulary ─────────────────────────────────────────────────────

#: Tokens valid in ``feedback.what_worked``.
#: A parent selects from these when describing what aspects of the plan helped.
FEEDBACK_CHIPS_WORKED: frozenset[str] = frozenset({
    "food_timing",       # "Food timing felt right"
    "hydration",         # "Hydration advice was on point"
    "warmup_timing",     # "Warm-up timing worked well"
    "scenario_planning", # "Scenario cards were useful"
    "food_recs",         # "Food recommendations were helpful"
    "weather_forecast",  # "Weather call was accurate"
    "schedule",          # "Schedule felt realistic"
})

#: Tokens valid in ``feedback.what_didnt_work``.
#: Symmetric with FEEDBACK_CHIPS_WORKED — same vocab, different field context.
FEEDBACK_CHIPS_DIDNT_WORK: frozenset[str] = FEEDBACK_CHIPS_WORKED

#: Union of all valid chip tokens (convenience alias for validation).
ALL_FEEDBACK_CHIP_TOKENS: frozenset[str] = FEEDBACK_CHIPS_WORKED

# ── Display labels (canonical mapping) ───────────────────────────────────────

#: Human-readable labels keyed by chip token.
#: This is the canonical source of truth for display strings.
#: iOS FeedbackChips.swift MUST mirror this mapping exactly.
FEEDBACK_CHIP_LABELS: dict[str, str] = {
    "food_timing":       "Food Timing",
    "hydration":         "Hydration Advice",
    "warmup_timing":     "Warm-Up Timing",
    "scenario_planning": "Scenario Planning",
    "food_recs":         "Food Recommendations",
    "weather_forecast":  "Weather Forecast",
    "schedule":          "Schedule",
}

# ── Validation helper ─────────────────────────────────────────────────────────

_MAX_CHIPS_PER_FIELD = 7  # equals vocab size; allows selecting all chips


def validate_chip_list(
    value: list[str],
    allowed: frozenset[str],
    field_name: str,
) -> list[str]:
    """Validate a chip token list against an allowed vocabulary.

    Args:
        value:      The list of chip tokens to validate.
        allowed:    Frozenset of permitted token strings.
        field_name: Used in the error message for clarity.

    Returns:
        The validated list unchanged.

    Raises:
        ValueError if any token is not in ``allowed`` or if more than
        ``_MAX_CHIPS_PER_FIELD`` tokens are provided.
    """
    if len(value) > _MAX_CHIPS_PER_FIELD:
        raise ValueError(
            f"{field_name}: maximum {_MAX_CHIPS_PER_FIELD} chips allowed, "
            f"got {len(value)}"
        )
    invalid = sorted(set(value) - allowed)
    if invalid:
        raise ValueError(
            f"{field_name}: unrecognised chip token(s): {invalid}. "
            f"Allowed: {sorted(allowed)}"
        )
    return value
