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
