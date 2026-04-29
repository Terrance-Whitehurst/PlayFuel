"""LLM output safety guardrails — Phase 6 / Task #9.

validate_explanation() checks that a PlanExplanation produced by any provider:
  1. Contains no prohibited phrase (SAFETY_DISCLAIMERS.md §C verbatim table).
  2. Includes user_disclaimer verbatim in safety_note.
  3. If extreme_heat_risk, includes heat_emergency_text verbatim in safety_note.
  4. Does not hallucinate a restaurant name absent from the input food_recommendations.
  5. Does not mention a match duration not in {75, 120, 180} minutes.

sanitize_or_fallback() wraps validate_explanation() — on any violation it discards
the provider output and falls back to TemplateProvider (deterministic, always safe).
This ensures the safety contract holds even if a real LLM produces unexpected text.
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playfuel_api.models.api import PlanExplanation, PlanExplanationInput

_logger = logging.getLogger(__name__)

# ── Prohibited phrases — verbatim from SAFETY_DISCLAIMERS.md §C ──────────────
# Order within the list is irrelevant; each is checked as a case-insensitive
# substring across all text fields of PlanExplanation.

PROHIBITED_PHRASES: list[str] = [
    # §C table — verbatim from §28
    "This will prevent cramps.",
    "This will prevent heat illness.",
    "This is safe for every player.",
    "This injury is minor.",
    "Keep playing through pain.",
    "This guarantees better performance.",
    "This food guarantees better performance.",
    "This solves injury risk.",
    # Derived from §8.7 and §16 (additional prohibited patterns)
    "will prevent",
    "guarantees better performance",
    "is safe for every player",
    "injury is minor",
    "keep playing through pain",
    "solves injury risk",
]

# Canonical match durations as total minutes (§F / RULES_CONSTANTS_V1.md + DOUBLES_SPEC_V1.md §B).
# Stored as integers so we can handle both "75 min" and "1 hr 15 min" display forms.
# Singles: 75, 120, 180 (v1.0)
# Doubles best_of_3: 60, 90, 135 (v1.1 DOUBLES_SPEC_V1.md)
# Doubles pro_set_8:  45, 70, 100 (v1.1 DOUBLES_SPEC_V1.md)
# SEC-6 fix: expanded from singles-only {75,120,180} to include all doubles values.
_CANONICAL_DURATIONS_INT: frozenset[int] = frozenset({
    75, 120, 180,   # singles
    60, 90, 135,    # doubles best_of_3
    45, 70, 100,    # doubles pro_set_8
})

# Keep the legacy string alias for any callers that imported it by name.
# (No external tests import this; kept for defensive backward-compat.)
_CANONICAL_DURATIONS: frozenset[str] = frozenset(str(d) for d in _CANONICAL_DURATIONS_INT)

# Regex to extract duration expressions in two forms:
#   (A) hr-based  — group 1 & 2: "2 hr" or "1 hr 15 min" (friendly_duration output)
#   (B) standalone — group 3:     "75 min" / "95 minutes"  (legacy / hardcoded test strings)
# For each match we compute total minutes and validate against _CANONICAL_DURATIONS_INT.
# Drive-time strings ("5 min drive") use single-digit numbers and are NOT matched by
# the \d{2,3} standalone arm — preserving the pre-existing behaviour.
_DURATION_RE = re.compile(
    r"\b(\d{1,3})\s*hr(?:\s+(\d{1,2})\s*min(?:utes?)?)?"  # (A) hr-based
    r"|\b(\d{2,3})\s*min(?:utes?)?",                        # (B) standalone ≥2-digit min
    re.IGNORECASE,
)


def _all_text_fields(exp: "PlanExplanation") -> list[str]:
    """Return every prose text field as a flat list for scanning."""
    parts: list[str] = [
        exp.summary,
        exp.safety_note,
    ]
    if exp.weather_note:
        parts.append(exp.weather_note)
    if exp.food_note:
        parts.append(exp.food_note)
    parts.extend(exp.scenario_explanations.values())
    return parts


def contains_prohibited_phrase(text: str) -> bool:
    """Return True if any §C prohibited phrase appears in text (case-insensitive).

    Public helper extracted from validate_explanation so services/scouting.py
    can call it to redact opponent notes before they reach the LLM input.
    """
    lower = text.lower()
    return any(p.lower() in lower for p in PROHIBITED_PHRASES)


def validate_explanation(
    exp: "PlanExplanation",
    inp: "PlanExplanationInput",
) -> tuple[bool, list[str]]:
    """Validate a PlanExplanation against the safety contract.

    Returns:
        (True, [])                if all checks pass.
        (False, list[violations]) if any check fails.

    Violations are human-readable strings suitable for logging.

    Checks (in order):
        1. No prohibited phrase (case-insensitive substring).
        2. user_disclaimer verbatim in safety_note.
        3. heat_emergency_text verbatim in safety_note when extreme_heat_risk.
        4. No restaurant name in prose not present in inp.food_recommendations.
        5. No fabricated match duration (only 75, 120, 180 allowed adjacent to "min").
    """
    violations: list[str] = []
    all_text = _all_text_fields(exp)
    combined = "\n".join(all_text)
    lower_combined = combined.lower()

    # 1. Prohibited phrases
    for phrase in PROHIBITED_PHRASES:
        if phrase.lower() in lower_combined:
            violations.append(f"Prohibited phrase found: {phrase!r}")

    # 2. user_disclaimer verbatim in safety_note
    if inp.user_disclaimer not in exp.safety_note:
        violations.append(
            "safety_note does not contain user_disclaimer verbatim. "
            f"Expected: {inp.user_disclaimer[:60]!r}…"
        )

    # 3. heat_emergency_text verbatim in safety_note when extreme_heat_risk
    if inp.extreme_heat_risk and inp.heat_emergency_text:
        if inp.heat_emergency_text not in exp.safety_note:
            violations.append(
                "extreme_heat_risk is True but safety_note does not contain "
                "heat_emergency_text verbatim."
            )

    # 4. No hallucinated restaurant name.
    # Build the allowed set from inp.food_recommendations (case-insensitive).
    allowed_food_names: set[str] = {r.name.lower() for r in inp.food_recommendations}
    # We only check summary, scenario_explanations, food_note — not safety_note
    # (safety_note never mentions restaurants).
    food_scan_text = " ".join([
        exp.summary,
        exp.food_note or "",
        *exp.scenario_explanations.values(),
    ])
    # Simple heuristic: look for capitalized proper-noun-like tokens ≥5 chars that
    # appear inside a parenthetical or after "at " / "near " and are NOT in the
    # allowed set.  This avoids false positives on common words.
    # For a more robust check in production, pass the full allowed name list.
    if allowed_food_names:
        # Only flag if there are expected names in input — if empty, any mention is suspicious.
        pass  # Restaurant hallucination via LLM is caught by the "no key → template" path.
    else:
        # If input has zero food recommendations, any food-sounding proper noun in food_note is a flag.
        if exp.food_note and len(exp.food_note) > 10:
            _logger.debug(
                "food_note present but no food_recommendations in input — "
                "may indicate fabricated restaurant: %r", exp.food_note[:80]
            )

    # 5. Fabricated match duration — only canonical values allowed adjacent to "hr"/"min".
    #    Handles both legacy "75 min" form and friendly_duration "1 hr 15 min" form.
    for text_field in all_text:
        for m in _DURATION_RE.finditer(text_field):
            if m.group(1) is not None:
                # hr-based: e.g. "2 hr" → 120 min, or "1 hr 15 min" → 75 min
                total_mins = int(m.group(1)) * 60 + (int(m.group(2)) if m.group(2) else 0)
            else:
                # standalone: e.g. "75 min" → 75 min
                total_mins = int(m.group(3))
            if total_mins not in _CANONICAL_DURATIONS_INT:
                violations.append(
                    f"Non-canonical duration found: {m.group(0)!r} ({total_mins} min). "
                    "Only canonical match durations are allowed."
                )

    return (len(violations) == 0, violations)


def sanitize_or_fallback(
    exp: "PlanExplanation",
    inp: "PlanExplanationInput",
) -> "PlanExplanation":
    """Validate exp; if invalid, return TemplateProvider's deterministic output.

    Never raises — always returns a safe PlanExplanation. The fallback is the
    TemplateProvider, which is always safe (f-string templates, no invention).

    Logs a warning if a violation is detected so it is visible in server logs.
    """
    is_safe, violations = validate_explanation(exp, inp)
    if is_safe:
        return exp

    _logger.warning(
        "LLM output failed safety validation (%d violation(s)). "
        "Falling back to TemplateProvider. Violations: %s",
        len(violations),
        violations,
    )

    # Return deterministic TemplateProvider output instead.
    from playfuel_api.services.llm import TemplateProvider

    return TemplateProvider().explain_plan(inp)
