"""Gap-to-bucket classification — RULES_CONSTANTS_V1.md §B.2 / §B.3.

All intervals are half-open, lower-inclusive: gap ∈ [a, b).

Food bucket boundaries (FOOD_BUCKET_BOUNDARIES = [45, 90, 150]):
  [0,   45) → bag_only
  [45,  90) → portable
  [90,  150) → quick_pickup
  [150, ∞)  → light_meal

Pickup bucket boundaries (PICKUP_BUCKET_BOUNDARIES = [60, 120]):
  [0,   60)  → bring_portable
  [60,  120) → pickup_during_match
  [120, ∞)   → wait_until_end

These functions are pure: no I/O, no side effects, no LLM calls.
Callers are responsible for ensuring gap_minutes >= 0 (i.e. not an overrun).
"""
from playfuel_api.models.enums import FoodBucket, PickupBucket
from playfuel_api.rules.constants import (
    FOOD_BUCKET_BOUNDARIES,
    PICKUP_BUCKET_BOUNDARIES,
)


def food_bucket_for(gap_minutes: int) -> FoodBucket:
    """Return the FoodBucket for a non-negative gap duration.

    Uses half-open, lower-inclusive intervals per §B.2.
    Boundary values (45, 90, 150) fall into the *upper* bucket:
      gap=45  → portable  (not bag_only)
      gap=90  → quick_pickup  (not portable)
      gap=150 → light_meal    (not quick_pickup)

    Args:
        gap_minutes: Minutes between estimated match end and next match start.
                     Must be >= 0; overrun scenarios are handled upstream.

    Returns:
        FoodBucket enum value.
    """
    lo_portable, lo_quick_pickup, lo_light_meal = FOOD_BUCKET_BOUNDARIES

    if gap_minutes < lo_portable:       # [0, 45)
        return FoodBucket.bag_only
    if gap_minutes < lo_quick_pickup:   # [45, 90)
        return FoodBucket.portable
    if gap_minutes < lo_light_meal:     # [90, 150)
        return FoodBucket.quick_pickup
    return FoodBucket.light_meal        # [150, ∞)


def pickup_bucket_for(gap_minutes: int) -> PickupBucket:
    """Return the PickupBucket for a non-negative gap duration.

    Uses half-open, lower-inclusive intervals per §B.3.
    Boundary values (60, 120) fall into the *upper* bucket:
      gap=60  → pickup_during_match  (not bring_portable)
      gap=120 → wait_until_end       (not pickup_during_match)

    Args:
        gap_minutes: Minutes between estimated match end and next match start.
                     Must be >= 0; overrun scenarios are handled upstream.

    Returns:
        PickupBucket enum value.
    """
    lo_pickup_during, lo_wait_until_end = PICKUP_BUCKET_BOUNDARIES

    if gap_minutes < lo_pickup_during:   # [0, 60)
        return PickupBucket.bring_portable
    if gap_minutes < lo_wait_until_end:  # [60, 120)
        return PickupBucket.pickup_during_match
    return PickupBucket.wait_until_end   # [120, ∞)
