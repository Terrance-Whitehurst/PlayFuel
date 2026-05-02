"""Tests for rules/food.py recommended_order_for() templates.

Verifies §F.3 template content + draft-flag correctness for all categories.
Phase 5 / Task #8.
"""
import pytest
from playfuel_api.rules.food import CATEGORIES, recommended_order_for


# ── fast_casual_bowl — CONFIRMED (is_draft=False) ─────────────────────────────


def test_fast_casual_bowl_returns_confirmed_template():
    """fast_casual_bowl template is confirmed (is_draft=False)."""
    text, is_draft = recommended_order_for("fast_casual_bowl")
    assert is_draft is False
    assert isinstance(text, str) and len(text) > 20


def test_fast_casual_bowl_contains_rice():
    """fast_casual_bowl template mentions rice (core of a Chipotle-style bowl)."""
    text, _ = recommended_order_for("fast_casual_bowl")
    assert "rice" in text.lower()


def test_fast_casual_bowl_mentions_protein():
    """fast_casual_bowl template mentions protein (chicken or steak)."""
    text, _ = recommended_order_for("fast_casual_bowl")
    assert "chicken" in text.lower() or "steak" in text.lower()


def test_fast_casual_bowl_mentions_hydration():
    """fast_casual_bowl template mentions water (hydration guidance)."""
    text, _ = recommended_order_for("fast_casual_bowl")
    assert "water" in text.lower()


# ── Draft templates (is_draft=True) ──────────────────────────────────────────


@pytest.mark.parametrize("category", [
    "sandwich_shop",
    "grocery_prepared",
    "breakfast_cafe",
    "restaurant",
])
def test_draft_categories_have_is_draft_true(category):
    """OQ-B draft categories all return is_draft=True."""
    _, is_draft = recommended_order_for(category)
    assert is_draft is True


@pytest.mark.parametrize("category", [
    "sandwich_shop",
    "grocery_prepared",
    "breakfast_cafe",
    "restaurant",
])
def test_draft_templates_are_non_empty_strings(category):
    """All draft templates return non-empty strings."""
    text, _ = recommended_order_for(category)
    assert isinstance(text, str) and len(text) > 20


# ── sandwich_shop template content ────────────────────────────────────────────


def test_sandwich_shop_template_mentions_turkey_or_chicken():
    """sandwich_shop template should recommend lean protein."""
    text, _ = recommended_order_for("sandwich_shop")
    assert "turkey" in text.lower() or "chicken" in text.lower()


# ── Unknown category fallback ─────────────────────────────────────────────────


def test_unknown_category_falls_back_to_restaurant_template():
    """Unknown category returns restaurant fallback template."""
    text, is_draft = recommended_order_for("non_existent_category")
    restaurant_text, restaurant_draft = recommended_order_for("restaurant")
    assert text == restaurant_text
    assert is_draft == restaurant_draft


# ── All known categories return a valid (str, bool) tuple ─────────────────────


@pytest.mark.parametrize("category", sorted(CATEGORIES))
def test_all_categories_return_valid_template(category):
    """Every value in CATEGORIES maps to a non-empty string template."""
    text, is_draft = recommended_order_for(category)
    assert isinstance(text, str) and len(text) > 10
    assert isinstance(is_draft, bool)


# ── Phase 5-polish: new cuisine bucket tests ───────────────────────────────────────


@pytest.mark.parametrize("category", [
    "italian_restaurant",
    "mexican_restaurant",
    "pizza_restaurant",
    "fast_food_restaurant",
    "chinese_restaurant",
    "japanese_restaurant",
    "american_restaurant",
])
def test_new_cuisine_buckets_are_draft(category):
    """All 7 new cuisine-specific buckets are is_draft=True (OQ-B carries)."""
    _, is_draft = recommended_order_for(category)
    assert is_draft is True


@pytest.mark.parametrize("category", [
    "italian_restaurant",
    "mexican_restaurant",
    "pizza_restaurant",
    "fast_food_restaurant",
    "chinese_restaurant",
    "japanese_restaurant",
    "american_restaurant",
])
def test_new_cuisine_buckets_return_non_empty_text(category):
    """All 7 new cuisine-specific buckets return non-empty recommended order text."""
    text, _ = recommended_order_for(category)
    assert isinstance(text, str) and len(text) > 20


def test_italian_restaurant_suggestions_mention_pasta():
    """Italian template main_options includes pasta/marinara content."""
    from playfuel_api.rules.food import _SUGGESTIONS
    data, is_draft = _SUGGESTIONS["italian_restaurant"]
    combined = " ".join(data["main_options"]).lower()
    assert "pasta" in combined or "marinara" in combined
    assert is_draft is True


def test_fast_food_restaurant_template_mentions_grilled_chicken():
    """fast_food_restaurant template recommends grilled (not fried) chicken."""
    from playfuel_api.rules.food import _SUGGESTIONS
    data, _ = _SUGGESTIONS["fast_food_restaurant"]
    combined = " ".join(data["main_options"]).lower()
    assert "grilled" in combined and "chicken" in combined


def test_chinese_restaurant_template_has_steamed_rice():
    """Chinese restaurant template recommends steamed rice."""
    from playfuel_api.rules.food import _SUGGESTIONS
    data, _ = _SUGGESTIONS["chinese_restaurant"]
    combined = " ".join(data["main_options"]).lower()
    assert "steamed" in combined and "rice" in combined


def test_japanese_restaurant_template_has_rice_bowl():
    """Japanese restaurant template recommends a rice bowl option."""
    from playfuel_api.rules.food import _SUGGESTIONS
    data, _ = _SUGGESTIONS["japanese_restaurant"]
    combined = " ".join(data["main_options"]).lower()
    assert "rice" in combined


def test_american_restaurant_template_recommends_grilled():
    """American restaurant template favors grilled over fried."""
    from playfuel_api.rules.food import _SUGGESTIONS
    data, _ = _SUGGESTIONS["american_restaurant"]
    combined = " ".join(data["main_options"]).lower()
    assert "grilled" in combined


def test_pizza_restaurant_template_limits_slices():
    """Pizza restaurant template mentions portion limits (1-2 slices)."""
    from playfuel_api.rules.food import _SUGGESTIONS
    data, _ = _SUGGESTIONS["pizza_restaurant"]
    combined = " ".join(data["main_options"] + data["notes"]).lower()
    assert "slice" in combined or "slices" in combined


def test_mexican_restaurant_template_mentions_grilled():
    """Mexican restaurant template recommends grilled protein."""
    from playfuel_api.rules.food import _SUGGESTIONS
    data, _ = _SUGGESTIONS["mexican_restaurant"]
    combined = " ".join(data["main_options"]).lower()
    assert "grilled" in combined
