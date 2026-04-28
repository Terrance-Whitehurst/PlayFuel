"""Tests for structured FoodSuggestions — rules/food.py suggestions_for() +
derive_recommended_order() + assemble_food_options() lat/lng surfacing.

Covers FOOD_DECK_AND_MAP_V1.md §G.4 acceptance criteria (10 named tests ≥ spec
requirement of 8).

Phase 8.3 — FOOD_DECK_AND_MAP_V1.md
"""
from __future__ import annotations

import pytest

from playfuel_api.models.api import FoodSuggestions
from playfuel_api.rules.food import (
    assemble_food_options,
    derive_recommended_order,
    suggestions_for,
)
from playfuel_api.services.places import RawPlace


# ── suggestions_for() — per-category structured templates ────────────────────


def test_suggestions_fast_casual_bowl_non_empty_and_confirmed() -> None:
    """fast_casual_bowl returns all non-empty buckets; is_draft=False."""
    sugg, is_draft = suggestions_for("fast_casual_bowl")
    assert is_draft is False
    assert len(sugg.main_options) >= 1, "main_options must have ≥1 item"
    assert len(sugg.drinks) >= 1, "drinks must have ≥1 item"
    assert len(sugg.avoid) >= 1, "avoid must have ≥1 item"
    assert len(sugg.notes) >= 1, "notes must have ≥1 item"


def test_suggestions_fast_casual_bowl_contains_rice_and_protein() -> None:
    """fast_casual_bowl main_options[0] references rice AND protein (chicken/steak)."""
    sugg, _ = suggestions_for("fast_casual_bowl")
    first = sugg.main_options[0].lower()
    assert "rice" in first
    assert "chicken" in first or "steak" in first


def test_suggestions_breakfast_cafe_has_oatmeal_and_is_draft() -> None:
    """breakfast_cafe returns oatmeal in main_options; is_draft=True (OQ-B)."""
    sugg, is_draft = suggestions_for("breakfast_cafe")
    assert is_draft is True
    assert any("oat" in item.lower() for item in sugg.main_options), (
        "breakfast_cafe main_options must mention oatmeal (per user story US-FOOD-2)"
    )


def test_suggestions_sandwich_shop_mentions_turkey_or_chicken_and_is_draft() -> None:
    """sandwich_shop main_options[0] references lean protein; is_draft=True."""
    sugg, is_draft = suggestions_for("sandwich_shop")
    assert is_draft is True
    combined = " ".join(sugg.main_options).lower()
    assert "turkey" in combined or "chicken" in combined


def test_suggestions_grocery_prepared_mentions_rotisserie_and_is_draft() -> None:
    """grocery_prepared main_options references rotisserie; is_draft=True."""
    sugg, is_draft = suggestions_for("grocery_prepared")
    assert is_draft is True
    combined = " ".join(sugg.main_options).lower()
    assert "rotisserie" in combined


def test_suggestions_restaurant_fallback_is_draft() -> None:
    """restaurant template returns a valid shape with is_draft=True."""
    sugg, is_draft = suggestions_for("restaurant")
    assert is_draft is True
    assert len(sugg.main_options) >= 1
    assert len(sugg.drinks) >= 1


def test_suggestions_unknown_category_falls_back_to_restaurant() -> None:
    """Unknown category string → restaurant fallback template."""
    sugg_unknown, draft_unknown = suggestions_for("totally_bogus_category_xyz")
    sugg_rest, draft_rest = suggestions_for("restaurant")
    # Both are the restaurant template — field-by-field equality via Pydantic model
    assert sugg_unknown == sugg_rest
    assert draft_unknown == draft_rest


# ── derive_recommended_order() ────────────────────────────────────────────────


def test_derive_recommended_order_chipotle_contains_rice_and_drinks() -> None:
    """Chipotle FoodSuggestions → derived string contains 'rice' and 'Drinks'."""
    sugg, _ = suggestions_for("fast_casual_bowl")
    result = derive_recommended_order(sugg)
    assert isinstance(result, str) and len(result) > 10
    assert "rice" in result.lower()
    assert "Drinks" in result


def test_derive_recommended_order_empty_suggestions_returns_empty_string() -> None:
    """All-empty FoodSuggestions → derive_recommended_order returns '' (not crash)."""
    empty = FoodSuggestions()
    result = derive_recommended_order(empty)
    assert result == ""


# ── assemble_food_options() — lat/lng surfacing ───────────────────────────────


def _make_place(
    name: str = "Test Place",
    types: list[str] | None = None,
    drive: int = 4,
    dist: int = 1000,
    lat: float | None = None,
    lng: float | None = None,
) -> RawPlace:
    return RawPlace(
        name=name,
        types=types or ["restaurant", "meal_takeaway"],
        distance_meters=dist,
        drive_time_minutes=drive,
        place_id="test_001",
        provider="mock",
        lat=lat,
        lng=lng,
    )


def test_assemble_food_options_surfaces_lat_lng_from_raw_place() -> None:
    """lat/lng on RawPlace propagates through to FoodOption.lat / FoodOption.lng."""
    place = _make_place(lat=32.7825, lng=-96.7975)
    options, bag_only = assemble_food_options([place], ["quick_pickup"])
    assert bag_only is False
    assert len(options) == 1
    opt = options[0]
    assert opt.lat == 32.7825
    assert opt.lng == -96.7975


def test_assemble_food_options_lat_lng_none_when_not_on_raw_place() -> None:
    """When RawPlace has lat=None/lng=None, FoodOption carries None coords."""
    place = _make_place(lat=None, lng=None)
    options, _ = assemble_food_options([place], ["quick_pickup"])
    assert len(options) == 1
    assert options[0].lat is None
    assert options[0].lng is None


def test_assemble_food_options_suggestions_non_empty_for_fast_casual_bowl() -> None:
    """fast_casual_bowl FoodOption carries non-empty structured suggestions."""
    place = _make_place(
        name="Chipotle Mexican Grill",
        types=["restaurant", "meal_takeaway"],
        lat=32.7825,
        lng=-96.7975,
    )
    options, _ = assemble_food_options([place], ["quick_pickup"])
    assert len(options) == 1
    opt = options[0]
    assert len(opt.suggestions.main_options) >= 1
    assert len(opt.suggestions.drinks) >= 1
    assert opt.is_draft is False  # fast_casual_bowl confirmed


def test_assemble_food_options_dallas_mock_provider_fixtures_have_coords() -> None:
    """All 4 Dallas mock fixtures surface non-None lat/lng through assemble_food_options."""
    from playfuel_api.services.places import MockPlacesProvider

    raw = list(MockPlacesProvider().search_nearby(32.78, -96.80, 4828, 10))
    options, bag_only = assemble_food_options(raw, ["light_meal"])
    assert bag_only is False
    assert len(options) == 4, f"Expected 4 Dallas fixtures, got {len(options)}"
    for opt in options:
        assert opt.lat is not None, f"{opt.name}.lat must not be None"
        assert opt.lng is not None, f"{opt.name}.lng must not be None"


def test_bag_fallback_only_path_does_not_crash_with_structured_suggestions() -> None:
    """bag_only bucket path returns ([], True) — no crash from suggestions refactor."""
    options, bag_only = assemble_food_options([_make_place()], ["bag_only"])
    assert options == []
    assert bag_only is True
