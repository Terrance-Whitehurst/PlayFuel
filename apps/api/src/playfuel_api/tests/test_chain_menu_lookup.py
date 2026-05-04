"""Tests for chain-menu-items feature — rules/chain_lookup.py + food.py integration.

Covers spec §J required tests (7) plus one additional stub-safety test (total 8).

Chain-menu-items feature: rules/chain_menus.json + rules/chain_lookup.py +
FoodOption.chain_matched / FoodOption.chain_as_of fields.

§G.0 note: live Places API spot-check deferred (no live traffic in test env).
  Dallas MockPlacesProvider returns "Chipotle Mexican Grill" and "Starbucks"
  which are exercised in test_assemble_food_options_chain_matched_uses_registry
  and the Dallas integration path in test_food_suggestions.py.
"""
from __future__ import annotations

import json

import pytest

from playfuel_api.rules.chain_lookup import lookup_chain, normalize_name
from playfuel_api.rules.food import assemble_food_options
from playfuel_api.services.places import RawPlace


# ── normalize_name() unit tests ───────────────────────────────────────────────


def test_normalize_name_strips_hyphens_chick_fil_a() -> None:
    """Chick-fil-A → 'chickfila' (hyphens stripped leaving concatenated tokens).

    ``[^\\w\\s]`` strips the hyphen as an empty replacement (not a space), so
    'chick-fil-a' → 'chickfila'.  The 'chickfila' alias in chain_menus.json
    accounts for this.
    """
    assert normalize_name("Chick-fil-A") == "chickfila"


def test_normalize_name_strips_hash_store_number() -> None:
    """'Chick-fil-A #4521' → 'chickfila' (store number stripped THEN hyphens stripped).

    Store-number regex strips ' #4521' before punctuation removal, leaving
    'chick-fil-a' → 'chickfila'.  Confirmed by lookup test below.
    """
    assert normalize_name("Chick-fil-A #4521") == "chickfila"


def test_normalize_name_preserves_multi_word() -> None:
    """'Chipotle Mexican Grill' → 'chipotle mexican grill' (no punctuation to strip)."""
    assert normalize_name("Chipotle Mexican Grill") == "chipotle mexican grill"


# ── lookup_chain() — happy path ───────────────────────────────────────────────


def test_lookup_chain_exact_match_chick_fil_a() -> None:
    """'Chick-fil-A' normalizes to 'chick fil a' and matches the registry entry."""
    entry = lookup_chain("Chick-fil-A")
    assert entry is not None
    assert entry["id"] == "chick-fil-a"
    assert entry["display_name"] == "Chick-fil-A"
    # Populated entry must carry real suggestions
    assert len(entry["suggestions"]["main_options"]) >= 1
    assert entry["as_of"] != "TBD"


def test_lookup_chain_store_number_stripped() -> None:
    """'Chick-fil-A #4521' → store number stripped → same registry entry."""
    entry = lookup_chain("Chick-fil-A #4521")
    assert entry is not None
    assert entry["id"] == "chick-fil-a"


def test_lookup_chain_no_match_returns_none() -> None:
    """An unknown restaurant name returns None (no match, no crash)."""
    assert lookup_chain("Tony's Pizza Palace") is None
    assert lookup_chain("") is None
    assert lookup_chain("XYZ Diner 99") is None


def test_lookup_chain_case_insensitive() -> None:
    """'CHIPOTLE' normalizes to 'chipotle' and matches registry alias."""
    entry = lookup_chain("CHIPOTLE")
    assert entry is not None
    assert entry["id"] == "chipotle"


def test_lookup_chain_chipotle_full_name() -> None:
    """'Chipotle Mexican Grill' (mock fixture exact name) matches registry."""
    entry = lookup_chain("Chipotle Mexican Grill")
    assert entry is not None
    assert entry["id"] == "chipotle"
    # Verify registry suggestions shape
    sugg = entry["suggestions"]
    assert len(sugg.get("main_options", [])) >= 1
    assert len(sugg.get("drinks", [])) >= 1


def test_lookup_chain_starbucks() -> None:
    """'Starbucks' (mock fixture exact name) matches registry."""
    entry = lookup_chain("Starbucks")
    assert entry is not None
    assert entry["id"] == "starbucks"


# ── lookup_chain() — stub safety ─────────────────────────────────────────────


def test_stub_entries_never_match() -> None:
    """Stub entries (as_of='TBD') must never be returned, even if their alias
    would otherwise match the normalized input.

    Panera Bread is a stub in the registry with alias 'panera bread'.
    lookup_chain('Panera Bread') must return None.
    """
    result = lookup_chain("Panera Bread")
    assert result is None, (
        "Stub entry 'panera-bread' (as_of=TBD) must not match — "
        "lookup_chain must skip stubs before alias comparison"
    )
    # Verify Subway, Jimmy John's, and CAVA stubs also never match
    assert lookup_chain("Subway") is None
    assert lookup_chain("Jimmy John's") is None
    assert lookup_chain("CAVA") is None


# ── registry load ─────────────────────────────────────────────────────────────


def test_chain_menus_json_loads_without_error() -> None:
    """chain_menus.json is present, valid JSON, and has the expected top-level shape."""
    from pathlib import Path

    registry_path = (
        Path(__file__).parent.parent / "rules" / "chain_menus.json"
    )
    assert registry_path.exists(), f"chain_menus.json not found at {registry_path}"
    with open(registry_path, encoding="utf-8") as fh:
        data = json.load(fh)

    assert data.get("version") == "1.0.0"
    chains = data.get("chains", [])
    assert len(chains) == 26, f"Expected 26 chains, got {len(chains)}"

    # All entries must have required keys
    for chain in chains:
        assert "id" in chain
        assert "display_name" in chain
        assert "match_aliases" in chain
        assert "as_of" in chain
        assert "suggestions" in chain

    # Exactly 3 fully populated entries (non-TBD)
    populated = [c for c in chains if c["as_of"] != "TBD"]
    assert len(populated) == 3, f"Expected 3 populated entries, got {len(populated)}"
    populated_ids = {c["id"] for c in populated}
    assert populated_ids == {"chick-fil-a", "chipotle", "starbucks"}

    # The other 23 are stubs
    stubs = [c for c in chains if c["as_of"] == "TBD"]
    assert len(stubs) == 23


# ── assemble_food_options() integration ───────────────────────────────────────


def _make_place(
    name: str,
    types: list[str] | None = None,
    drive: int = 4,
    dist: int = 1200,
) -> RawPlace:
    return RawPlace(
        name=name,
        types=types or ["restaurant", "meal_takeaway"],
        distance_meters=dist,
        drive_time_minutes=drive,
        place_id=f"mock_{name.lower().replace(' ', '_')}",
        provider="mock",
    )


def test_assemble_food_options_chain_matched_uses_registry() -> None:
    """Chipotle Mexican Grill → chain_matched=True, suggestions from registry, is_draft=False.

    Exercises AC#1 + AC#5(a): matched chain carries registry-sourced suggestions
    and correct chain_matched / chain_as_of values.
    """
    place = _make_place("Chipotle Mexican Grill")
    options, bag_only = assemble_food_options([place], ["quick_pickup"])

    assert bag_only is False
    assert len(options) == 1
    opt = options[0]

    # Chain-match fields
    assert opt.chain_matched is True
    assert opt.chain_as_of == "2026-05-04"

    # Suggestions come from registry, not generic template
    assert "Rice bowl" in opt.suggestions.main_options[0] or "rice" in opt.suggestions.main_options[0].lower()
    assert len(opt.suggestions.main_options) >= 1
    assert len(opt.suggestions.drinks) >= 1

    # Category still set from categorize_place (chain lookup is independent)
    assert opt.category == "fast_casual_bowl"
    # is_draft=False for chain-matched entries
    assert opt.is_draft is False


def test_assemble_food_options_chain_matched_starbucks() -> None:
    """Starbucks (mock fixture name) → chain_matched=True, oatmeal in suggestions."""
    place = _make_place("Starbucks", types=["cafe", "bakery"])
    options, _ = assemble_food_options([place], ["quick_pickup"])
    assert len(options) == 1
    opt = options[0]

    assert opt.chain_matched is True
    assert opt.chain_as_of == "2026-05-04"
    assert any("oatmeal" in item.lower() or "Oatmeal" in item for item in opt.suggestions.main_options)
    assert opt.is_draft is False


def test_assemble_food_options_unmatched_uses_category_template() -> None:
    """An unmatched restaurant → chain_matched=False, chain_as_of=None, template used.

    Exercises AC#2 + AC#5(b): zero regression for non-chain restaurants.
    """
    place = _make_place("Tony's Pizza Palace", types=["pizza_restaurant", "restaurant"])
    options, bag_only = assemble_food_options([place], ["quick_pickup"])

    assert bag_only is False
    assert len(options) == 1
    opt = options[0]

    # No chain match
    assert opt.chain_matched is False
    assert opt.chain_as_of is None

    # Template-sourced suggestions (pizza_restaurant template)
    assert opt.category == "pizza_restaurant"
    # is_draft=True for DRAFT template categories
    assert opt.is_draft is True


def test_assemble_food_options_stub_chain_falls_back_to_template() -> None:
    """A stub chain name → lookup returns None → falls back to category template.

    Panera Bread is a stub.  It has category_hint 'breakfast_cafe' which maps
    through categorize_place via the 'cafe' / 'bakery' type.
    """
    place = _make_place("Panera Bread", types=["bakery", "cafe"])
    options, _ = assemble_food_options([place], ["quick_pickup"])
    assert len(options) == 1
    opt = options[0]

    assert opt.chain_matched is False
    assert opt.chain_as_of is None
    # Fell back to breakfast_cafe template (is_draft=True per OQ-B)
    assert opt.is_draft is True
