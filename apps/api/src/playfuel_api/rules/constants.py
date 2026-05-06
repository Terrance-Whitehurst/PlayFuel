"""
PlayFuel rules constants — version 1.0.0.

Source of truth: RULES_CONSTANTS_V1.md (FROZEN, Phase 0 Task #2 complete).
All values here are traceable to a named section in that document.
No runtime code may mutate these constants; changes require a version bump (§J).
"""

# ─── Version (§J.1) ──────────────────────────────────────────────────────────

RULES_CONSTANTS_VERSION = "2.2.2"  # bumped from 2.2.1 — DR-PLACES-1: places.distanceMeters removed from Google field mask (was 400 INVALID_ARGUMENT)

# ─── Scenario durations (§A.1 + DOUBLES_SPEC_V1.md §B.1) ─────────────────────────────────────────
#
# v1.1.0: CHANGED from flat dict[str,int] to nested dict keyed by (match_type, doubles_format).
# Callers: rules/scenarios.py uses SCENARIO_DURATIONS_MIN[(match_type, doubles_format)][kind].
# All doubles values are DRAFT — OQ-DBL-1 (validate with USTA junior coach before Phase 7).

SCENARIO_DURATIONS_MIN: dict[tuple[str, str | None], dict[str, int]] = {
    ("singles", None):          {"short": 75,  "normal": 120, "long": 180},  # v1.0.0 — FROZEN
    ("doubles", "best_of_3"):   {"short": 60,  "normal": 90,  "long": 135},  # [DRAFT — OQ-DBL-1]
    ("doubles", "pro_set_8"):   {"short": 45,  "normal": 70,  "long": 100},  # [DRAFT — OQ-DBL-1]
}

# ─── Arrival buffer (ACCOMMODATIONS_V1.md §F.3 / RULES_CONSTANTS_V1.md §D.1) ─────
#
# ARRIVE_SNACK_MIN: arrive at venue and have a light snack at T-60m before match start.
# Used as the anchor for departure event timing in build_timeline().
# See ACCOMMODATIONS_V1.md §E.2 for usage.

ARRIVE_SNACK_MIN: int = 60  # T-60m: arrive at venue and light snack

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
    "hot":        29.4,   # temp_c >= 29.4°C  (was 85°F)  §E.1
    "very_hot":   32.2,   # temp_c >= 32.2°C  (was 90°F)  §E.1
    "humid":      65.0,   # humidity_pct >= 65%            §E.1 — unchanged
    "cold":       10.0,   # temp_c <= 10.0°C  (was 50°F)  §E.1
    "windy":      24.0,   # wind_kmh >= 24.0 km/h (was 15 mph) §E.1
    "rain_risk":  40.0,   # precipitation_probability >= 40%    §E.1 — unchanged
}
# Derived: extreme_heat_risk = very_hot OR (hot AND humid) — §E.2
# DR_20 atomic-flip contract: WEATHER_THRESHOLDS and Open-Meteo unit params
# MUST change in the same commit. Splitting breaks EmergencyBanner silently.

# ─── Draw size + round vocab (draw-size-spec.md §3) ──────────────────────────
#
# draw_size: total bracket entries. The four values supported for junior draws.
# round: number of players still alive at this bracket stage. 2 = Final.
# round_label: short DB/wire abbreviation derived from round.
#
# Keep in sync with iOS RoundVocab.swift (Models/RoundVocab.swift).

DRAW_SIZES: list[int] = [32, 64, 128, 256]

ROUND_LABELS: dict[int, str] = {
    256: "R256",
    128: "R128",
    64:  "R64",
    32:  "R32",
    16:  "R16",
    8:   "QF",
    4:   "SF",
    2:   "F",
}

VALID_ROUNDS: set[int] = set(ROUND_LABELS.keys())


def rounds_for_draw(draw_size: int) -> list[int]:
    """Return valid round values for a draw size, largest first (earliest → latest bracket stage).

    Examples:
        rounds_for_draw(32)  → [32, 16, 8, 4, 2]
        rounds_for_draw(64)  → [64, 32, 16, 8, 4, 2]
        rounds_for_draw(256) → [256, 128, 64, 32, 16, 8, 4, 2]
    """
    rounds: list[int] = []
    r = draw_size
    while r >= 2:
        rounds.append(r)
        r //= 2
    return rounds
