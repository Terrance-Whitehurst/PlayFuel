"""
Hard-coded string registry — RULES_CONSTANTS_V1.md §H.

THESE STRINGS ARE NEVER LLM-GENERATED. They are compiled into the backend.
The LLM must not modify or re-interpret them at runtime.
Any change requires a RULES_CONSTANTS_VERSION bump (§J).

OQ-11 PRE-LAUNCH BLOCKER:
  HEAT_EMERGENCY_TEXT is DRAFT pending attorney review before App Store submission.
  Verbatim from SAFETY_DISCLAIMERS.md §B. Do not alter wording here without
  legal sign-off.
"""

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
# ⚠️  DRAFT — OQ-11 (pre-launch blocker).
# Verbatim from SAFETY_DISCLAIMERS.md §B. Pending attorney review.
# Surface this string ONLY through this constant — never re-type it in views,
# routes, or LLM prompts.

HEAT_EMERGENCY_TEXT: str = (
    "If the player feels faint, confused, has chest pain, stops sweating in "
    "extreme heat, has severe cramps, vomits repeatedly, or shows signs of "
    "heat illness, stop play and seek medical help immediately."
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
