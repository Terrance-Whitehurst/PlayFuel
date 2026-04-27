"""Tests for rules/food.py assemble_food_options().

Covers bag_only shortcut, drive-time filtering, sorting, and result shape.
Phase 5 / Task #8.
"""
import pytest
from playfuel_api.rules.food import assemble_food_options
from playfuel_api.services.places import RawPlace


# ── Helper fixtures ───────────────────────────────────────────────────────────


def _chipotle(drive_min: int = 4, dist_m: int = 1200) -> RawPlace:
    return RawPlace(
        name="Chipotle Mexican Grill",
        types=["restaurant", "meal_takeaway"],
        distance_meters=dist_m,
        drive_time_minutes=drive_min,
        place_id="mock_chipotle",
        provider="mock",
    )


def _jimmy_johns(drive_min: int = 3, dist_m: int = 800) -> RawPlace:
    return RawPlace(
        name="Jimmy John's",
        types=["restaurant", "sandwich_shop"],
        distance_meters=dist_m,
        drive_time_minutes=drive_min,
        place_id="mock_jimmys",
        provider="mock",
    )


def _central_market(drive_min: int = 9, dist_m: int = 3500) -> RawPlace:
    return RawPlace(
        name="Central Market",
        types=["supermarket", "grocery_store"],
        distance_meters=dist_m,
        drive_time_minutes=drive_min,
        place_id="mock_cm",
        provider="mock",
    )


# ── bag_only shortcut ─────────────────────────────────────────────────────────


def test_bag_only_bucket_returns_empty_list_and_flag():
    """All bag_only buckets → empty list + bag_fallback_only=True."""
    places = [_chipotle(), _jimmy_johns()]
    options, bag_only = assemble_food_options(places, ["bag_only"])
    assert options == []
    assert bag_only is True


def test_bag_only_with_multiple_bag_buckets_still_returns_empty():
    """Multiple bag_only entries still produce empty + flag."""
    options, bag_only = assemble_food_options([_chipotle()], ["bag_only", "bag_only"])
    assert options == []
    assert bag_only is True


def test_empty_raw_places_with_bag_only():
    """Empty places list with bag_only → empty + flag."""
    options, bag_only = assemble_food_options([], ["bag_only"])
    assert options == []
    assert bag_only is True


# ── non-bag buckets → places returned ────────────────────────────────────────


def test_quick_pickup_includes_chipotle_at_4min():
    """quick_pickup allows ≤8 min drive; 4-min Chipotle should be included."""
    options, bag_only = assemble_food_options([_chipotle(drive_min=4)], ["quick_pickup"])
    assert bag_only is False
    assert len(options) == 1
    assert options[0].name == "Chipotle Mexican Grill"
    assert options[0].category == "fast_casual_bowl"


def test_portable_bucket_excludes_9min_place():
    """portable allows ≤5 min drive; 9-min Central Market should be filtered out."""
    options, bag_only = assemble_food_options([_central_market(drive_min=9)], ["portable"])
    assert bag_only is False
    assert options == []


def test_portable_bucket_includes_3min_place():
    """portable allows ≤5 min; 3-min Jimmy John's should be included."""
    options, bag_only = assemble_food_options([_jimmy_johns(drive_min=3)], ["portable"])
    assert bag_only is False
    assert len(options) == 1
    assert options[0].name == "Jimmy John's"


def test_light_meal_bucket_includes_9min_place():
    """light_meal allows ≤15 min; 9-min Central Market should be included."""
    options, bag_only = assemble_food_options([_central_market(drive_min=9)], ["light_meal"])
    assert bag_only is False
    assert len(options) == 1


def test_mixed_buckets_use_most_permissive_drive_time():
    """With portable + light_meal, most permissive drive time (15 min) applies."""
    places = [_chipotle(drive_min=4), _central_market(drive_min=9)]
    options, bag_only = assemble_food_options(places, ["portable", "light_meal"])
    assert bag_only is False
    assert len(options) == 2


# ── none drive time → included conservatively ─────────────────────────────────


def test_none_drive_time_place_is_included():
    """Places with drive_time_minutes=None are included (unknown = conservative accept)."""
    place = RawPlace(
        name="Mystery Diner",
        types=["restaurant"],
        distance_meters=500,
        drive_time_minutes=None,
        place_id="mystery",
        provider="mock",
    )
    options, _ = assemble_food_options([place], ["quick_pickup"])
    assert len(options) == 1


# ── sorting ───────────────────────────────────────────────────────────────────


def test_results_sorted_by_drive_time_ascending():
    """Options sorted: shortest drive first."""
    places = [_central_market(drive_min=9), _jimmy_johns(drive_min=3), _chipotle(drive_min=4)]
    options, _ = assemble_food_options(places, ["light_meal"])
    drive_times = [o.drive_time_minutes for o in options]
    assert drive_times == sorted(drive_times)


# ── max_results cap ────────────────────────────────────────────────────────────


def test_max_results_cap_is_respected():
    """assemble_food_options respects max_results cap."""
    places = [_chipotle(), _jimmy_johns(), _central_market(drive_min=5)]
    options, _ = assemble_food_options(places, ["light_meal"], max_results=2)
    assert len(options) <= 2


# ── result model shape ────────────────────────────────────────────────────────


def test_food_option_has_correct_fields():
    """Returned FoodOption has all expected fields."""
    options, _ = assemble_food_options([_chipotle()], ["quick_pickup"])
    assert len(options) == 1
    opt = options[0]
    assert opt.name == "Chipotle Mexican Grill"
    assert opt.category == "fast_casual_bowl"
    assert opt.drive_time_minutes == 4
    assert isinstance(opt.recommended_order, str) and len(opt.recommended_order) > 10
    assert opt.is_draft is False  # fast_casual_bowl is confirmed
    assert opt.distance_meters == 1200
    assert opt.place_id == "mock_chipotle"
    assert opt.provider == "mock"


def test_jimmy_johns_food_option_is_draft():
    """sandwich_shop category yields is_draft=True (OQ-B pending review)."""
    options, _ = assemble_food_options([_jimmy_johns()], ["portable"])
    assert len(options) == 1
    assert options[0].is_draft is True
