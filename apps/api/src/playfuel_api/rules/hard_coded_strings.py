"""
Hard-coded string registry — RULES_CONSTANTS_V1.md §H.

THESE STRINGS ARE NEVER LLM-GENERATED. They are compiled into the backend.
The LLM must not modify or re-interpret them at runtime.
Any change requires a RULES_CONSTANTS_VERSION bump (§J).

OQ-11 PRE-LAUNCH BLOCKER:
  HEAT_EMERGENCY_TEXT is DRAFT pending attorney review before App Store submission.
  Verbatim from SAFETY_DISCLAIMERS.md §B. Do not alter wording here without
  legal sign-off.

Phase C-infrastructure additions (migration 0020 / INTERNATIONAL_SCOPE_V1.md §L):
    _EMERGENCY_NUMBERS          — per-country emergency dial strings.
    emergency_number_for()      — returns the country-appropriate number or fallback phrase.
    heat_emergency_text()       — returns HEAT_EMERGENCY_TEXT with country-specific substitution.
"""
from __future__ import annotations

from typing import Optional


# ─── §H.1 — OVERRUN_MESSAGE ──────────────────────────────────────────────────

OVERRUN_MESSAGE: str = (
    "Match 1 may not finish before Match 2's estimated start time. "
    "Alert the tournament desk."
)

# ─── §H.3 — BAG_FOOD_FALLBACK ────────────────────────────────────────────────

BAG_FOOD_FALLBACK: str = (
    "Use immediate bag food only: banana, pretzels, applesauce pouch, "
    "electrolyte drink, simple sandwich if tolerated."
)

# ─── §H.2 — HEAT_EMERGENCY_TEXT ──────────────────────────────────────────────
#
# v1.1 wording from SAFETY_DISCLAIMERS.md §B (revised 2026-04-27 per OQ-11).
# Pending legal sign-off (OQ-06). Surface this string ONLY through this
# constant — never re-type it in views, routes, or LLM prompts.
#
# The parenthetical "(or your local emergency number)" covers all jurisdictions
# when venue_country is unknown. Use heat_emergency_text(venue_country) to
# substitute the country-specific number for known markets.

HEAT_EMERGENCY_TEXT: str = (
    "If your player feels faint or confused, has chest pain, stops sweating in "
    "extreme heat, has severe cramps, vomits repeatedly, or shows signs of heat "
    "illness: stop play and seek medical help. Call 911 (or your local emergency "
    "number) in an emergency."
)

# ─── §A — USER_DISCLAIMER ──────────────────────────────────────────────────
#
# Verbatim from SAFETY_DISCLAIMERS.md §A. Surface in onboarding, settings,
# and as the base safety_note in every PlanExplanation.
# Never rephrase or paraphrase — used verbatim in LLM output validation.

USER_DISCLAIMER: str = (
    "This app provides general tournament preparation guidance. "
    "It is not medical advice, nutrition therapy, or a substitute for a coach, "
    "physician, athletic trainer, or registered dietitian. "
    "For injuries, illness, heat symptoms, allergies, eating disorders, or "
    "medical conditions, consult a qualified professional."
)

# ─── Food-bucket display text (§B.2) — maps FoodBucket value → text ──────────

FOOD_BUCKET_TEXT: dict[str, str] = {
    "bag_only":     BAG_FOOD_FALLBACK,
    "portable":     "Use pre-bought portable food immediately after match. Avoid waiting in line.",
    "quick_pickup": "Use quick pickup food: turkey sandwich, rice bowl, grocery prepared meal.",
    "light_meal":   "There is enough time for a light meal, but avoid heavy/greasy foods.",
}

# ─── Pickup-bucket display text (§B.3) — maps PickupBucket value → text ──────

PICKUP_BUCKET_TEXT: dict[str, str] = {
    "bring_portable": (
        "Parent should have portable food ready before match ends."
    ),
    "pickup_during_match": (
        "If match is trending long, parent should pick up food during the final "
        "portion of the match if another trusted adult is present."
    ),
    "wait_until_end": (
        "Parent can likely wait until the match ends before getting food."
    ),
}

# ─── Per-country emergency number lookup — Phase C-infrastructure ─────────────
#
# Source: country-official emergency numbers for Tier 1/2/3 markets
#   (INTERNATIONAL_SCOPE_V1.md §L).
# US/MX/CA: 911  (Mexico unified to 911 in 2017)
# GB:        999 (UK national emergency)
# AU:        000
# EU:        112 (pan-European standard)
# BR:        190 (police; medical uses 192 — 190 is the universal first-contact)
# JP:        119 (fire/ambulance; police is 110)
#
# Fallback when country unknown: "your local emergency number" (already in
# HEAT_EMERGENCY_TEXT parenthetical — covers any jurisdiction generically).

_EMERGENCY_NUMBERS: dict[str, str] = {
    "US": "911",
    "MX": "911",
    "CA": "911",
    "GB": "999",
    "AU": "000",
    # EU Tier 2 fast-follow:
    "ES": "112",
    "FR": "112",
    "DE": "112",
    "IT": "112",
    # Tier 2:
    "BR": "190",
    # Tier 3:
    "JP": "119",
}


def emergency_number_for(venue_country: Optional[str]) -> str:
    """Return the country-appropriate emergency number string.

    Falls back to 'your local emergency number' when venue_country is None,
    empty, or not in the lookup table.

    Args:
        venue_country: ISO 3166-1 alpha-2 code (e.g. 'US', 'MX', 'GB'). May be None.

    Returns:
        Emergency dial string (e.g. '911', '999') or 'your local emergency number'.
    """
    if not venue_country:
        return "your local emergency number"
    return _EMERGENCY_NUMBERS.get(venue_country, "your local emergency number")


def heat_emergency_text(venue_country: Optional[str] = None) -> str:
    """Return HEAT_EMERGENCY_TEXT with country-appropriate emergency number substituted.

    Regression invariant: heat_emergency_text(None) is byte-identical to HEAT_EMERGENCY_TEXT.

    When venue_country is None or not in _EMERGENCY_NUMBERS, returns HEAT_EMERGENCY_TEXT
    unchanged — the parenthetical '(or your local emergency number)' already covers
    any jurisdiction.

    When a country-specific number is known and it is NOT '911', the phrase
    'Call 911 (or your local emergency number)' is replaced with 'Call {number}'
    to give the parent the exact number to dial without the redundant parenthetical.

    '911' countries (US, MX, CA) return HEAT_EMERGENCY_TEXT unchanged — the existing
    parenthetical is already correct and avoids altering a legally-sensitive string
    without necessity.

    Args:
        venue_country: ISO 3166-1 alpha-2 code or None.

    Returns:
        Heat emergency guidance string with country-appropriate emergency number.
    """
    if not venue_country or venue_country not in _EMERGENCY_NUMBERS:
        return HEAT_EMERGENCY_TEXT
    number = _EMERGENCY_NUMBERS[venue_country]
    if number == "911":
        # 911 countries: existing parenthetical is already correct — leave verbatim.
        return HEAT_EMERGENCY_TEXT
    return HEAT_EMERGENCY_TEXT.replace(
        "Call 911 (or your local emergency number)",
        f"Call {number}",
    )
