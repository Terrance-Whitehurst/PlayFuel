"""
PlayFuel rules constants — version 1.0.0.

Source of truth: RULES_CONSTANTS_V1.md (FROZEN, Phase 0 Task #2 complete).
All values here are traceable to a named section in that document.
No runtime code may mutate these constants; changes require a version bump (§J).
"""

# ─── Version (§J.1) ──────────────────────────────────────────────────────────

RULES_CONSTANTS_VERSION = "1.0.0"

# ─── Scenario durations (§A.1) ────────────────────────────────────────────────

SCENARIO_DURATIONS_MIN: dict[str, int] = {
    "short": 75,    # minutes
    "normal": 120,  # minutes
    "long": 180,    # minutes
}

# ─── Gap-bucket boundaries (§B.2 / §B.3) ─────────────────────────────────────
#
# All intervals are half-open, lower-inclusive: gap ∈ [a, b).
#
# Food buckets:
#   bag_only     [0,   45)
#   portable     [45,  90)
#   quick_pickup [90,  150)
#   light_meal   [150, ∞)
#
# Pickup buckets:
#   bring_portable      [0,   60)
#   pickup_during_match [60,  120)
#   wait_until_end      [120, ∞)

FOOD_BUCKET_BOUNDARIES: list[int] = [45, 90, 150]    # lower bounds of portable/quick_pickup/light_meal
PICKUP_BUCKET_BOUNDARIES: list[int] = [60, 120]       # lower bounds of pickup_during_match/wait_until_end

# ─── Gap-status thresholds (§G.1) ────────────────────────────────────────────
#
# [DRAFT — OQ-E] tight threshold is Engineering1's proposal (30 min).
# No Phase 0 source document defines this value. Confirm before Phase 3 cutover.

TIGHT_GAP_THRESHOLD_MIN: int = 30  # DRAFT — OQ-E

# ─── Re-warm-up parameters (§D.2) ────────────────────────────────────────────
#
# rewarm_up is non-null only when gap_minutes >= REWARM_UP_MIN_GAP.
# [DRAFT — OQ-C] offset/duration values pending Planning confirmation.

REWARM_UP_MIN_GAP: int = 60        # minimum gap (min) for rewarm_up to be scheduled
REWARM_UP_OFFSET_MIN: int = -30    # relative to next match start (negative = before)
REWARM_UP_DURATION_MIN: int = 20   # duration of dynamic re-warm-up

# ─── Weather thresholds (§E.1) ───────────────────────────────────────────────

WEATHER_THRESHOLDS: dict[str, float] = {
    "hot":        85.0,   # temp_f >= 85
    "very_hot":   90.0,   # temp_f >= 90 (independent; 92°F sets BOTH hot AND very_hot)
    "humid":      65.0,   # humidity_pct >= 65
    "cold":       50.0,   # temp_f <= 50
    "windy":      15.0,   # wind_mph >= 15
    "rain_risk":  40.0,   # precipitation_probability >= 40
}
# Derived: extreme_heat_risk = very_hot OR (hot AND humid) — §E.2
