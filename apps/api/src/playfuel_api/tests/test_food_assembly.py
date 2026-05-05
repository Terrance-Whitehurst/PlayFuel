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


def test_light_meal_bucket_includes_9min_food_primary_place():
    """light_meal allows ≤15 min; a 9-min food-primary place should be included.

    Central Market (supermarket type) is now filtered by _is_food_primary (Pass 1);
    replaced with a genuine restaurant fixture. FOOD_PLACES_FILTER_V1 \u00a7H.2.
    """
    nine_min_restaurant = RawPlace(
        name="Texas Roadhouse",
        types=["restaurant", "american_restaurant"],
        distance_meters=3200,
        drive_time_minutes=9,
        place_id="tx_roadhouse_001",
        provider="mock",
    )
    options, bag_only = assemble_food_options([nine_min_restaurant], ["light_meal"])
    assert bag_only is False
    assert len(options) == 1


def test_mixed_buckets_use_most_permissive_drive_time():
    """With portable + light_meal, most permissive drive time (15 min) applies.

    Central Market (supermarket) is now filtered by _is_food_primary (Pass 1);
    only Chipotle (food-primary) remains. FOOD_PLACES_FILTER_V1 \u00a7H.2.
    """
    places = [_chipotle(drive_min=4), _central_market(drive_min=9)]
    options, bag_only = assemble_food_options(places, ["portable", "light_meal"])
    assert bag_only is False
    assert len(options) == 1  # Central Market excluded by food-primary filter
    assert options[0].name == "Chipotle Mexican Grill"


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


def test_results_sorted_by_distance_ascending():
    """Options sorted by ascending haversine distance from venue.

    This test is intentionally discriminating: Chipotle has a SLOWER drive time (4 min)
    but is physically CLOSER to the venue than Jimmy John's (3 min drive, farther away).
    The old drive-time sort would put Jimmy John's first; the new distance sort puts Chipotle first.
    FOOD_PLACES_FILTER_V1 \u00a7E, \u00a7H.2.
    """
    # Venue: 32.78, -96.80
    # Chipotle: 0.0003\u00b0 north of venue \u2248 33m — fast drive but physically close
    chipotle_close = RawPlace(
        name="Chipotle Mexican Grill",
        types=["restaurant", "meal_takeaway"],
        distance_meters=300,
        drive_time_minutes=4,  # slower drive time but closer by haversine
        place_id="chip_close",
        provider="mock",
        lat=32.7803,
        lng=-96.80,
    )
    # Jimmy John's: 0.02\u00b0 north of venue \u2248 2226m — fast drive but physically far
    jimmy_far = RawPlace(
        name="Jimmy John's",
        types=["restaurant", "sandwich_shop"],
        distance_meters=2000,
        drive_time_minutes=3,  # faster drive time but farther by haversine
        place_id="jimmy_far",
        provider="mock",
        lat=32.80,
        lng=-96.80,
    )
    options, _ = assemble_food_options(
        [jimmy_far, chipotle_close],  # jimmy first in input (intentionally reversed)
        ["light_meal"],
        venue_lat=32.78,
        venue_lng=-96.80,
    )
    # haversine: Chipotle \u224833m < Jimmy John's \u22482226m — Chipotle first
    # old drive-time: Jimmy John's 3 min < Chipotle 4 min — Jimmy first (would fail here)
    assert options[0].name == "Chipotle Mexican Grill"
    assert options[1].name == "Jimmy John's"


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


# ── FOOD_PLACES_FILTER_V1 §H.1 — new tests ───────────────────────────────────


def test_food_primary_filter_excludes_supermarket():
    """Publix (supermarket type) is excluded; Starbucks + Chipotle remain.

    FOOD_PLACES_FILTER_V1 §H.1 Test 1.
    """
    publix = RawPlace(
        name="Publix",
        types=["supermarket", "grocery_store"],
        distance_meters=300,
        drive_time_minutes=2,
        place_id="publix_1",
        provider="mock",
    )
    starbucks = RawPlace(
        name="Starbucks",
        types=["cafe", "coffee_shop"],
        distance_meters=500,
        drive_time_minutes=3,
        place_id="sbux_1",
        provider="mock",
        lat=32.781,
        lng=-96.799,
    )
    chipotle = RawPlace(
        name="Chipotle",
        types=["restaurant", "meal_takeaway"],
        distance_meters=700,
        drive_time_minutes=4,
        place_id="chip_1",
        provider="mock",
        lat=32.782,
        lng=-96.798,
    )
    options, bag_only = assemble_food_options(
        [publix, starbucks, chipotle],
        ["quick_pickup"],
        venue_lat=32.78,
        venue_lng=-96.80,
    )
    names = [o.name for o in options]
    assert "Publix" not in names
    assert "Starbucks" in names
    assert "Chipotle" in names
    assert bag_only is False


def test_food_primary_filter_all_excluded_returns_empty():
    """Payload with only excluded types (gas station, pharmacy) → empty options.

    FOOD_PLACES_FILTER_V1 §H.1 Test 2.
    """
    gas = RawPlace(
        name="Shell",
        types=["gas_station", "convenience_store"],
        distance_meters=200,
        drive_time_minutes=1,
        place_id="shell_1",
        provider="mock",
    )
    pharmacy = RawPlace(
        name="CVS Pharmacy",
        types=["pharmacy", "drugstore"],
        distance_meters=400,
        drive_time_minutes=2,
        place_id="cvs_1",
        provider="mock",
    )
    options, bag_only = assemble_food_options([gas, pharmacy], ["quick_pickup"])
    assert options == []
    assert bag_only is False  # bag_only only True when all buckets are bag_only


def test_central_market_excluded_as_mixed_venue():
    """Central Market [supermarket, restaurant] is excluded by _is_food_primary.

    Mixed-use venue policy: ANY non-food-primary type → exclude.
    FOOD_PLACES_FILTER_V1 §G.1, §H.1 Test 3.
    """
    central_market = RawPlace(
        name="Central Market",
        types=["supermarket", "grocery_store", "food", "establishment"],
        distance_meters=3500,
        drive_time_minutes=9,
        place_id="cm_1",
        provider="mock",
    )
    chipotle = RawPlace(
        name="Chipotle",
        types=["restaurant", "meal_takeaway"],
        distance_meters=1200,
        drive_time_minutes=4,
        place_id="chip_1",
        provider="mock",
        lat=32.7825,
        lng=-96.7975,
    )
    options, _ = assemble_food_options(
        [central_market, chipotle],
        ["light_meal"],
        venue_lat=32.78,
        venue_lng=-96.80,
    )
    names = [o.name for o in options]
    assert "Central Market" not in names
    assert "Chipotle" in names


def test_distance_sort_closer_place_first():
    """3 food-primary places at varying distances → sorted ascending by haversine.

    All three places have lat/lng so haversine is used as the primary sort key.
    FOOD_PLACES_FILTER_V1 §H.1 Test 4.

    Venue: (32.78, -96.80)
    Domino's: (32.7808, -96.7985) — ~166m haversine
    Chipotle:  (32.7825, -96.7975) — ~362m haversine
    Starbucks: (32.7950, -96.7900) — ~1913m haversine
    """
    dominos = RawPlace(
        name="Domino's",
        types=["restaurant", "pizza_restaurant"],
        distance_meters=450,
        drive_time_minutes=2,
        place_id="dom_1",
        provider="mock",
        lat=32.7808,
        lng=-96.7985,
    )
    chipotle = RawPlace(
        name="Chipotle",
        types=["restaurant", "meal_takeaway"],
        distance_meters=1200,
        drive_time_minutes=4,
        place_id="chip_1",
        provider="mock",
        lat=32.7825,
        lng=-96.7975,
    )
    starbucks = RawPlace(
        name="Starbucks",
        types=["cafe"],
        distance_meters=2500,
        drive_time_minutes=8,
        place_id="sbux_1",
        provider="mock",
        lat=32.7950,
        lng=-96.7900,
    )
    options, _ = assemble_food_options(
        [starbucks, chipotle, dominos],  # intentionally reverse distance order
        ["light_meal"],
        venue_lat=32.78,
        venue_lng=-96.80,
    )
    assert options[0].name == "Domino's"
    assert options[1].name == "Chipotle"
    assert options[2].name == "Starbucks"


def test_no_venue_coords_falls_back_to_distance_meters():
    """Without venue_lat/lng, sort falls back to distance_meters ascending.

    FOOD_PLACES_FILTER_V1 §H.1 Test 5 + §G.6.
    """
    far = RawPlace(
        name="Far Diner",
        types=["restaurant"],
        distance_meters=2000,
        drive_time_minutes=7,
        place_id="far_1",
        provider="mock",
    )
    near = RawPlace(
        name="Near Cafe",
        types=["cafe"],
        distance_meters=300,
        drive_time_minutes=2,
        place_id="near_1",
        provider="mock",
    )
    # No venue_lat / venue_lng passed → keyword-default None → fallback to distance_meters
    options, _ = assemble_food_options([far, near], ["quick_pickup"])
    assert options[0].name == "Near Cafe"
    assert options[1].name == "Far Diner"
