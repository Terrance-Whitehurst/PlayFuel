"""Gap-bucket boundary tests — RULES_CONSTANTS_V1.md §B.2 / §B.3.

13 boundary cases covering every half-open interval edge for both
food_bucket_for() and pickup_bucket_for().

Half-open intervals are lower-inclusive: gap ∈ [a, b) means a ≤ gap < b.
Boundary values fall into the UPPER bucket:
    gap=45  → portable       (not bag_only)
    gap=90  → quick_pickup   (not portable)
    gap=150 → light_meal     (not quick_pickup)
    gap=60  → pickup_during_match (not bring_portable)
    gap=120 → wait_until_end      (not pickup_during_match)

Headlined regression (OQ-13 resolution):
    test_gap_120_is_quick_pickup — gap=120 falls in [90, 150) → quick_pickup for food
                                   AND in [120, ∞) → wait_until_end for pickup.
"""
import pytest

from playfuel_api.models.enums import FoodBucket, PickupBucket
from playfuel_api.rules.buckets import food_bucket_for, pickup_bucket_for


# ── Food bucket tests ─────────────────────────────────────────────────────────

class TestFoodBuckets:
    def test_gap_0_is_bag_only(self):
        """gap=0 — bottom of [0, 45) → bag_only."""
        assert food_bucket_for(0) == FoodBucket.bag_only

    def test_gap_44_is_bag_only(self):
        """gap=44 — inside [0, 45) → bag_only."""
        assert food_bucket_for(44) == FoodBucket.bag_only

    def test_gap_45_is_portable(self):
        """gap=45 — lower bound of [45, 90) → portable (NOT bag_only)."""
        assert food_bucket_for(45) == FoodBucket.portable

    def test_gap_89_is_portable(self):
        """gap=89 — inside [45, 90) → portable."""
        assert food_bucket_for(89) == FoodBucket.portable

    def test_gap_90_is_quick_pickup(self):
        """gap=90 — lower bound of [90, 150) → quick_pickup (NOT portable)."""
        assert food_bucket_for(90) == FoodBucket.quick_pickup

    def test_gap_149_is_quick_pickup(self):
        """gap=149 — inside [90, 150) → quick_pickup."""
        assert food_bucket_for(149) == FoodBucket.quick_pickup

    def test_gap_150_is_light_meal(self):
        """gap=150 — lower bound of [150, ∞) → light_meal (NOT quick_pickup)."""
        assert food_bucket_for(150) == FoodBucket.light_meal

    def test_gap_165_is_light_meal(self):
        """gap=165 — inside [150, ∞) → light_meal."""
        assert food_bucket_for(165) == FoodBucket.light_meal


# ── Pickup bucket tests ───────────────────────────────────────────────────────

class TestPickupBuckets:
    def test_gap_59_is_bring_portable(self):
        """gap=59 — inside [0, 60) → bring_portable."""
        assert pickup_bucket_for(59) == PickupBucket.bring_portable

    def test_gap_60_is_pickup_during_match(self):
        """gap=60 — lower bound of [60, 120) → pickup_during_match (NOT bring_portable)."""
        assert pickup_bucket_for(60) == PickupBucket.pickup_during_match

    def test_gap_119_is_pickup_during_match(self):
        """gap=119 — inside [60, 120) → pickup_during_match."""
        assert pickup_bucket_for(119) == PickupBucket.pickup_during_match

    def test_gap_120_is_wait_until_end(self):
        """gap=120 — lower bound of [120, ∞) → wait_until_end (NOT pickup_during_match)."""
        assert pickup_bucket_for(120) == PickupBucket.wait_until_end


# ── Headlined regression (OQ-13) ─────────────────────────────────────────────

def test_gap_120_is_quick_pickup():
    """OQ-13 regression — gap=120 falls in food [90, 150) → quick_pickup.

    Pre-OQ-13, conflicting prose vs. pseudocode placed gap=120 in either
    quick_pickup or light_meal. OQ-13 canonical resolution: [90, 150) is correct
    → gap=120 → quick_pickup. This matches §B.4 worked example (Normal scenario).

    Also asserts: pickup at gap=120 is wait_until_end (boundary of [120, ∞)).
    """
    assert food_bucket_for(120) == FoodBucket.quick_pickup
    assert pickup_bucket_for(120) == PickupBucket.wait_until_end
