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
