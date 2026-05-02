"""Tests for rules/food.py categorize_place().

6+ cases covering every category path including name heuristics and type-map fallback.
Phase 5 / Task #8.
"""
import pytest
from playfuel_api.rules.food import CATEGORIES, categorize_place


# ── Name heuristic cases ──────────────────────────────────────────────────────


def test_chipotle_name_yields_fast_casual_bowl():
    """'chipotle' in name → fast_casual_bowl regardless of types."""
    result = categorize_place(["restaurant", "food"], name="Chipotle Mexican Grill")
    assert result == "fast_casual_bowl"


def test_cava_name_yields_fast_casual_bowl():
    """'cava' in name → fast_casual_bowl (same name-heuristic bucket)."""
    result = categorize_place(["restaurant", "meal_takeaway"], name="CAVA")
    assert result == "fast_casual_bowl"


def test_jimmy_johns_name_yields_sandwich_shop():
    """'jimmy john' in name → sandwich_shop via name heuristic."""
    result = categorize_place(["restaurant", "food"], name="Jimmy John's")
    assert result == "sandwich_shop"


def test_subway_name_yields_sandwich_shop():
    """'subway' in name → sandwich_shop."""
    result = categorize_place(["restaurant", "meal_takeaway"], name="Subway")
    assert result == "sandwich_shop"


# ── Type-map cases ────────────────────────────────────────────────────────────


def test_supermarket_type_yields_grocery_prepared():
    """types=['supermarket'] → grocery_prepared via type map."""
    result = categorize_place(["supermarket", "grocery_store", "food"], name="Generic Market")
    assert result == "grocery_prepared"


def test_grocery_store_type_yields_grocery_prepared():
    """types=['grocery_store'] → grocery_prepared via type map."""
    result = categorize_place(["grocery_store", "establishment"], name="Fresh Foods")
    assert result == "grocery_prepared"


def test_cafe_type_yields_breakfast_cafe():
    """types=['cafe'] → breakfast_cafe via type map."""
    result = categorize_place(["cafe", "food", "establishment"], name="Morning Brew")
    assert result == "breakfast_cafe"


def test_bakery_type_yields_breakfast_cafe():
    """types=['bakery'] → breakfast_cafe via type map."""
    result = categorize_place(["bakery", "food"], name="Corner Bakery")
    assert result == "breakfast_cafe"


# ── Fallback cases ────────────────────────────────────────────────────────────


def test_generic_restaurant_type_yields_restaurant():
    """types=['restaurant'] → generic restaurant fallback."""
    result = categorize_place(["restaurant", "food", "establishment"], name="Local Diner")
    assert result == "restaurant"


def test_empty_types_yields_restaurant():
    """Empty types list → generic restaurant fallback."""
    result = categorize_place([], name="Unknown Eatery")
    assert result == "restaurant"


def test_unknown_types_yields_restaurant():
    """Completely unknown types → generic restaurant fallback."""
    result = categorize_place(["health", "beauty", "spa"], name="Weird Place")
    assert result == "restaurant"


# ── Return values are always valid CATEGORIES ─────────────────────────────────


@pytest.mark.parametrize("types,name", [
    (["meal_takeaway"], "Chipotle"),
    (["sandwich_shop"], "Jimmy John's"),
    (["supermarket"], "Whole Foods"),
    (["cafe"], "Starbucks"),
    (["restaurant"], "Fine Dining"),
    ([], ""),
])
def test_categorize_always_returns_valid_category(types, name):
    """categorize_place() always returns a value in CATEGORIES."""
    result = categorize_place(types, name)
    assert result in CATEGORIES


# ── Phase 5-polish: cuisine-specific type tests ──────────────────────────────────────────


def test_italian_restaurant_type_yields_italian_restaurant():
    """types=['italian_restaurant'] → italian_restaurant bucket."""
    result = categorize_place(["italian_restaurant", "restaurant", "food"], name="Local Italian")
    assert result == "italian_restaurant"


def test_mexican_restaurant_type_yields_mexican_restaurant_for_non_chain():
    """Non-Chipotle Mexican restaurant → mexican_restaurant bucket (not fast_casual_bowl)."""
    result = categorize_place(["mexican_restaurant", "restaurant", "food"], name="Casa Grande")
    assert result == "mexican_restaurant"


def test_pizza_restaurant_type_yields_pizza_restaurant():
    """types=['pizza_restaurant'] → pizza_restaurant bucket."""
    result = categorize_place(["pizza_restaurant", "restaurant", "food"], name="Marco's Pizza")
    assert result == "pizza_restaurant"


def test_fast_food_restaurant_type_yields_fast_food_restaurant():
    """types=['fast_food_restaurant'] → fast_food_restaurant bucket."""
    result = categorize_place(["fast_food_restaurant", "restaurant", "food"], name="Local Burger")
    assert result == "fast_food_restaurant"


def test_chinese_restaurant_type_yields_chinese_restaurant():
    """types=['chinese_restaurant'] → chinese_restaurant bucket."""
    result = categorize_place(["chinese_restaurant", "restaurant"], name="Panda Garden")
    assert result == "chinese_restaurant"


def test_japanese_restaurant_type_yields_japanese_restaurant():
    """types=['japanese_restaurant'] → japanese_restaurant bucket."""
    result = categorize_place(["japanese_restaurant", "restaurant"], name="Sakura Sushi")
    assert result == "japanese_restaurant"


def test_american_restaurant_type_yields_american_restaurant():
    """types=['american_restaurant'] → american_restaurant bucket."""
    result = categorize_place(["american_restaurant", "restaurant"], name="Main Street Grill")
    assert result == "american_restaurant"


def test_breakfast_restaurant_type_maps_to_breakfast_cafe():
    """types=['breakfast_restaurant'] → reuses breakfast_cafe bucket (no new template needed)."""
    result = categorize_place(["breakfast_restaurant", "restaurant"], name="Morning Glory Diner")
    assert result == "breakfast_cafe"


def test_name_heuristic_wins_over_mexican_restaurant_type():
    """Chipotle name → fast_casual_bowl even when type is mexican_restaurant.

    Name heuristics run before the type map. Chipotle is correctly treated as
    fast_casual_bowl regardless of what Google Places types it reports.
    """
    result = categorize_place(
        ["mexican_restaurant", "restaurant", "meal_takeaway"],
        name="Chipotle Mexican Grill",
    )
    assert result == "fast_casual_bowl"


def test_precedence_italian_over_restaurant():
    """types=['italian_restaurant', 'restaurant', 'food'] → italian_restaurant (most specific wins)."""
    result = categorize_place(["italian_restaurant", "restaurant", "food"], name="Pasta House")
    assert result == "italian_restaurant"


def test_bowling_alley_type_falls_back_to_restaurant():
    """types=['bowling_alley'] → unknown type → restaurant fallback."""
    result = categorize_place(["bowling_alley", "food"], name="Bowl & Grill")
    assert result == "restaurant"


@pytest.mark.parametrize("cuisine_type", [
    "italian_restaurant",
    "mexican_restaurant",
    "pizza_restaurant",
    "fast_food_restaurant",
    "chinese_restaurant",
    "japanese_restaurant",
    "american_restaurant",
])
def test_new_cuisine_buckets_are_in_categories(cuisine_type):
    """All 7 new cuisine buckets are declared in CATEGORIES."""
    assert cuisine_type in CATEGORIES
