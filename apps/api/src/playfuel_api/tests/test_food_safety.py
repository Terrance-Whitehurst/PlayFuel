"""Safety lint for food templates — SAFETY_DISCLAIMERS §C compliance.

Scans all strings in rules/food._SUGGESTIONS against the prohibited
phrase list from SAFETY_DISCLAIMERS.md §C. Templates are static
(non-LLM) content but must still comply with the prohibited-phrase
contract so they don't appear as counterexamples during legal review.

Fails CI loudly — with bucket name + phrase — if any template string
contains a prohibited phrase.

Also verifies structural integrity: every bucket has the required keys
with ≥1 item in main_options, drinks, avoid, and notes. Catches
malformed buckets at CI time before they reach iOS.

Phase 5-polish — T-G2.
"""
import pytest
from playfuel_api.rules.food import CATEGORIES, _SUGGESTIONS

# ── §C prohibited phrase fragments (case-insensitive substring match) ──────────
# Verbatim from SAFETY_DISCLAIMERS.md §C (prohibited phrases + additional patterns).
# Using partial strings so minor phrasing variants are caught too.
_PROHIBITED_FRAGMENTS: list[str] = [
    # Explicit §C prohibited phrases
    "will prevent cramps",
    "will prevent heat illness",
    "is safe for every player",
    "this injury is minor",
    "keep playing through pain",
    "guarantees better performance",
    "food guarantees",
    "this food will",
    "this solves injury",
    # Additional implied prohibitions per §C and §8.7
    "prevents cramps",
    "prevents heat",
    "prevents injury",
    "prevents illness",
    "will cure",
    "medical advice",
]


def _all_strings_in_suggestions(category: str) -> list[str]:
    """Collect every string value from a _SUGGESTIONS bucket."""
    data, _ = _SUGGESTIONS[category]
    strings: list[str] = []
    for field in ("main_options", "add_ons", "drinks", "avoid", "notes"):
        strings.extend(data.get(field, []))
    return strings


# ── Safety compliance: no prohibited phrases ─────────────────────────────────


@pytest.mark.parametrize("category", sorted(_SUGGESTIONS.keys()))
def test_template_strings_have_no_prohibited_phrases(category: str) -> None:
    """No string in any template bucket contains a SAFETY_DISCLAIMERS §C prohibited phrase."""
    strings = _all_strings_in_suggestions(category)
    violations: list[str] = []
    for s in strings:
        for fragment in _PROHIBITED_FRAGMENTS:
            if fragment.lower() in s.lower():
                violations.append(
                    f"  [{category}] '{s[:80]}' matches '{fragment}'"
                )
    assert not violations, (
        f"Safety violations in {category} template:\n" + "\n".join(violations)
    )


# ── Structural integrity: required keys are present and non-empty ─────────────


@pytest.mark.parametrize("category", sorted(_SUGGESTIONS.keys()))
def test_template_has_at_least_three_main_options(category: str) -> None:
    """Every template bucket has ≥3 items in main_options.

    Threshold raised from >=1 to >=3 (GAP-5a, chore/cleanup-phases-5-7):
    the 7 cuisine buckets added in Phase 5-polish all ship with >=3 options;
    the 5 pre-existing buckets were tightened to match in food.py alongside
    this test change.  Enforcing >=3 gives iOS enough content for a useful card.
    """
    data, _ = _SUGGESTIONS[category]
    assert len(data.get("main_options", [])) >= 3, (
        f"{category}: main_options has fewer than 3 items (GAP-5a threshold). "
        "Add more options to food.py rather than lowering this threshold."
    )


@pytest.mark.parametrize("category", sorted(_SUGGESTIONS.keys()))
def test_template_has_at_least_one_drink(category: str) -> None:
    """Every template bucket has ≥1 item in drinks."""
    data, _ = _SUGGESTIONS[category]
    assert len(data.get("drinks", [])) >= 1, (
        f"{category}: drinks is empty or missing"
    )


@pytest.mark.parametrize("category", sorted(_SUGGESTIONS.keys()))
def test_template_has_at_least_two_avoid(category: str) -> None:
    """Every template bucket has ≥2 items in avoid.

    Threshold raised from >=1 to >=2 (GAP-5a, chore/cleanup-phases-5-7):
    a single avoid item is not actionable; two gives a clear pattern.
    All 12 existing buckets already satisfy >=2 avoid before this change.
    """
    data, _ = _SUGGESTIONS[category]
    assert len(data.get("avoid", [])) >= 2, (
        f"{category}: avoid has fewer than 2 items (GAP-5a threshold). "
        "Add more avoid items to food.py rather than lowering this threshold."
    )


@pytest.mark.parametrize("category", sorted(_SUGGESTIONS.keys()))
def test_template_has_at_least_one_note(category: str) -> None:
    """Every template bucket has ≥1 item in notes."""
    data, _ = _SUGGESTIONS[category]
    assert len(data.get("notes", [])) >= 1, (
        f"{category}: notes is empty or missing"
    )


# ── CATEGORIES ↔ _SUGGESTIONS completeness ───────────────────────────────────


def test_every_category_has_a_suggestions_entry() -> None:
    """Every value in CATEGORIES has an entry in _SUGGESTIONS.

    Catches the case where a new CATEGORIES value is added without a
    corresponding _SUGGESTIONS entry, which would cause suggestions_for()
    to silently fall back to the generic 'restaurant' template.

    Exception: 'breakfast_cafe' covers both 'cafe'/'bakery' type map entries
    AND 'breakfast_restaurant' type — one template serves multiple types by design.
    """
    missing = [c for c in CATEGORIES if c not in _SUGGESTIONS]
    assert not missing, (
        f"CATEGORIES values with no _SUGGESTIONS entry: {missing}. "
        "Add template data to _SUGGESTIONS for each missing category."
    )


def test_every_suggestions_entry_is_in_categories() -> None:
    """Every key in _SUGGESTIONS is declared in CATEGORIES.

    Catches orphaned template entries that would never be reachable via
    categorize_place() → suggestions_for() lookup.
    """
    orphaned = [k for k in _SUGGESTIONS if k not in CATEGORIES]
    assert not orphaned, (
        f"_SUGGESTIONS entries not in CATEGORIES: {orphaned}. "
        "Either add to CATEGORIES or remove the orphaned entry."
    )


# ── Negative test: verify the lint function actually catches violations ───────


def test_prohibited_phrase_lint_catches_violation() -> None:
    """Synthetic bucket with a known prohibited phrase causes the lint to detect it.

    This tests the test: confirms the lint function isn't silently passing
    everything due to a logic error.
    """
    synthetic: dict = {
        "main_options": ["This food guarantees better performance on court"],
        "add_ons": [],
        "drinks": ["Water"],
        "avoid": ["Nothing"],
        "notes": ["Eat before play"],
    }
    strings: list[str] = []
    for field in ("main_options", "add_ons", "drinks", "avoid", "notes"):
        strings.extend(synthetic.get(field, []))

    violations: list[str] = []
    for s in strings:
        for fragment in _PROHIBITED_FRAGMENTS:
            if fragment.lower() in s.lower():
                violations.append(f"  [synthetic] '{s}' matches '{fragment}'")

    # The synthetic bucket MUST produce at least one violation.
    assert violations, (
        "Lint did not catch the known prohibited phrase 'food guarantees' in the "
        "synthetic bucket. Check _PROHIBITED_FRAGMENTS logic."
    )
