"""Tests for LLM safety guardrails — Phase 6 / Task #9.

validate_explanation() must catch each violation type.
sanitize_or_fallback() must return TemplateProvider output on any violation.

Test cases (5 named violation types + passthrough):
    1. Prohibited phrase in summary → violation detected.
    2. Prohibited phrase in scenario_explanations → violation detected.
    3. Missing user_disclaimer in safety_note → violation detected.
    4. Missing heat_emergency_text when extreme_heat_risk=True → violation detected.
    5. Non-canonical duration (e.g. "90 min") in scenario text → violation detected.
    6. Clean explanation passes validation.
    7. sanitize_or_fallback returns TemplateProvider output when validation fails.
    8. sanitize_or_fallback returns the original explanation when validation passes.
"""
from __future__ import annotations

import pytest

from playfuel_api.models.api import (
    FoodRecommendationSummary,
    PlanExplanation,
    PlanExplanationInput,
    ScenarioSummary,
)
from playfuel_api.rules.hard_coded_strings import HEAT_EMERGENCY_TEXT, USER_DISCLAIMER
from playfuel_api.services.llm_safety import (
    PROHIBITED_PHRASES,
    sanitize_or_fallback,
    validate_explanation,
)

# ── Shared helpers ─────────────────────────────────────────────────────────────


def _base_input(*, extreme_heat_risk: bool = False) -> PlanExplanationInput:
    return PlanExplanationInput(
        venue_name="SMU Tennis Center",
        match_start_iso="2026-05-15T14:00:00+00:00",
        match_round_label="R16",
        weather_temp_f=98.0,
        weather_humidity_pct=55,
        weather_flags=["very_hot"],
        extreme_heat_risk=extreme_heat_risk,
        scenarios=[
            ScenarioSummary(
                scenario="short", duration_min=75, gap_status="ok",
                food_bucket="quick_pickup", pickup_bucket="wait_until_end",
            ),
            ScenarioSummary(
                scenario="normal", duration_min=120, gap_status="ok",
                food_bucket="quick_pickup", pickup_bucket="wait_until_end",
            ),
            ScenarioSummary(
                scenario="long", duration_min=180, gap_status="tight",
                food_bucket="bag_only", pickup_bucket="bring_portable",
            ),
        ],
        food_recommendations=[
            FoodRecommendationSummary(name="Chipotle", category="fast_casual_bowl"),
        ],
        bag_fallback_only=False,
        heat_emergency_text=HEAT_EMERGENCY_TEXT if extreme_heat_risk else None,
        user_disclaimer=USER_DISCLAIMER,
    )


def _clean_explanation(inp: PlanExplanationInput) -> PlanExplanation:
    """Return a clean PlanExplanation that passes all safety checks."""
    from datetime import datetime, timezone
    safety = inp.user_disclaimer
    if inp.extreme_heat_risk and inp.heat_emergency_text:
        safety = f"{inp.heat_emergency_text}\n\n{inp.user_disclaimer}"
    return PlanExplanation(
        summary="Your player's match starts at 2 PM. Three scenarios are prepared.",
        scenario_explanations={
            "short": "In the short scenario (75 min match): comfortable break.",
            "normal": "In the normal scenario (120 min match): comfortable break.",
            "long": "In the long scenario (180 min match): tight turnaround.",
        },
        weather_note="Today is 98°F with 55% humidity. Keep the player cool.",
        food_note="Nearby options: Chipotle (fast_casual_bowl, 5 min drive).",
        safety_note=safety,
        provider="template",
        model=None,
        generated_at=datetime.now(tz=timezone.utc),
    )


# ── Test: clean explanation passes ────────────────────────────────────────────

def test_clean_explanation_passes_validation() -> None:
    """A properly constructed explanation passes all 5 checks."""
    inp = _base_input()
    exp = _clean_explanation(inp)
    is_safe, violations = validate_explanation(exp, inp)
    assert is_safe, f"Expected clean explanation to pass. Violations: {violations}"
    assert violations == []


# ── Test: prohibited phrase in summary ────────────────────────────────────────

def test_prohibited_phrase_in_summary_is_caught() -> None:
    """Prohibited phrase 'will prevent' in summary triggers a violation."""
    from datetime import datetime, timezone
    inp = _base_input()
    exp = _clean_explanation(inp)
    exp = exp.model_copy(update={
        "summary": "This plan will prevent cramps during the match."
    })
    is_safe, violations = validate_explanation(exp, inp)
    assert not is_safe
    assert any("will prevent" in v.lower() or "prevent cramps" in v.lower() for v in violations), (
        f"Expected prohibited-phrase violation. Got: {violations}"
    )


# ── Test: prohibited phrase in scenario_explanations ──────────────────────────

def test_prohibited_phrase_in_scenario_text_is_caught() -> None:
    """Prohibited phrase 'guarantees better performance' caught in scenario text."""
    inp = _base_input()
    exp = _clean_explanation(inp)
    exp = exp.model_copy(update={
        "scenario_explanations": {
            "short": "This food guarantees better performance.",
            "normal": "In the normal scenario (120 min match): comfortable break.",
            "long": "In the long scenario (180 min match): tight turnaround.",
        }
    })
    is_safe, violations = validate_explanation(exp, inp)
    assert not is_safe
    assert any("guarantees" in v.lower() for v in violations), (
        f"Expected prohibited-phrase violation. Got: {violations}"
    )


# ── Test: missing user_disclaimer in safety_note ──────────────────────────────

def test_missing_user_disclaimer_in_safety_note_is_caught() -> None:
    """Missing verbatim user_disclaimer in safety_note is a violation."""
    from datetime import datetime, timezone
    inp = _base_input()
    exp = _clean_explanation(inp)
    exp = exp.model_copy(update={
        "safety_note": "All good, no issues."  # missing USER_DISCLAIMER
    })
    is_safe, violations = validate_explanation(exp, inp)
    assert not is_safe
    assert any("user_disclaimer" in v.lower() or "disclaimer" in v.lower() for v in violations), (
        f"Expected disclaimer-missing violation. Got: {violations}"
    )


# ── Test: missing heat_emergency_text when extreme_heat_risk ──────────────────

def test_missing_heat_text_when_extreme_heat_is_caught() -> None:
    """Missing heat_emergency_text in safety_note when extreme_heat_risk=True."""
    inp = _base_input(extreme_heat_risk=True)
    exp = _clean_explanation(inp)
    # Overwrite safety_note to have user_disclaimer but NOT heat_emergency_text
    exp = exp.model_copy(update={"safety_note": USER_DISCLAIMER})
    is_safe, violations = validate_explanation(exp, inp)
    assert not is_safe
    assert any("heat_emergency_text" in v.lower() or "extreme_heat" in v.lower() for v in violations), (
        f"Expected heat-text violation. Got: {violations}"
    )


# ── Test: non-canonical duration in prose ─────────────────────────────────────

def test_non_canonical_duration_is_caught() -> None:
    """Duration '95 min' (not in any canonical set) is flagged as fabricated.

    NOTE: 90 min was the original test value but it was added to
    _CANONICAL_DURATIONS in the SEC-6 fix (doubles best_of_3 normal duration).
    Updated to use 95 min, which is not a canonical duration for any match type.
    """
    inp = _base_input()
    exp = _clean_explanation(inp)
    exp = exp.model_copy(update={
        "scenario_explanations": {
            "short": "In the short scenario (95 min match): comfortable break.",
            "normal": "In the normal scenario (120 min match): comfortable break.",
            "long": "In the long scenario (180 min match): tight turnaround.",
        }
    })
    is_safe, violations = validate_explanation(exp, inp)
    assert not is_safe
    assert any("95" in v for v in violations), (
        f"Expected non-canonical duration violation. Got: {violations}"
    )


# ── Test: sanitize_or_fallback on violation ────────────────────────────────────

def test_sanitize_or_fallback_returns_template_output_on_violation() -> None:
    """On a safety violation, sanitize_or_fallback returns TemplateProvider output."""
    from datetime import datetime, timezone
    inp = _base_input()
    bad_exp = _clean_explanation(inp)
    bad_exp = bad_exp.model_copy(update={
        "safety_note": "No disclaimer here."
    })
    result = sanitize_or_fallback(bad_exp, inp)
    # Result must be safe
    is_safe, violations = validate_explanation(result, inp)
    assert is_safe, f"sanitize_or_fallback returned unsafe output. Violations: {violations}"
    # And must be TemplateProvider output
    assert result.provider == "template"


# ── Test: sanitize_or_fallback passes through valid output ─────────────────────

def test_sanitize_or_fallback_passes_clean_explanation_through() -> None:
    """When validation passes, sanitize_or_fallback returns the original explanation."""
    inp = _base_input()
    exp = _clean_explanation(inp)
    result = sanitize_or_fallback(exp, inp)
    assert result is exp, "sanitize_or_fallback should return the same object when clean"


# ── Test: PROHIBITED_PHRASES constant is non-empty ────────────────────────────

def test_prohibited_phrases_list_is_populated() -> None:
    """PROHIBITED_PHRASES must be non-empty (§C verbatim phrases must be loaded)."""
    assert len(PROHIBITED_PHRASES) >= 8, (
        f"Expected ≥8 prohibited phrases from §C. Got {len(PROHIBITED_PHRASES)}."
    )


# -- Test: check #4 -- hallucinated restaurant name caught (SEC-P6-1) ----------

def test_hallucinated_restaurant_name_in_food_note_is_caught() -> None:
    """Check 4: LLM-hallucinated restaurant name in food_note triggers a violation.

    SEC-P6-1: at runtime food_recommendations is empty; food_categories has bucket
    names. A multi-word Title-Case proper noun ('Caffe Luna Rosa') in food_note
    that is NOT derivable from the input categories must be flagged as a violation.
    """
    inp = _base_input()
    inp = inp.model_copy(update={
        "food_recommendations": [],
        "food_categories": ["italian_restaurant"],
    })
    exp = _clean_explanation(inp)
    # Inject a hallucinated restaurant proper-noun into food_note.
    exp = exp.model_copy(update={
        "food_note": "Pick up food from Caffe Luna Rosa before the match.",
    })
    is_safe, violations = validate_explanation(exp, inp)
    assert not is_safe, (
        f"Expected violation for hallucinated restaurant name. Got safe. violations={violations}"
    )
    assert any(
        "caffe luna rosa" in v.lower() or "hallucinated" in v.lower()
        for v in violations
    ), f"Expected hallucination violation message. Got: {violations}"


def test_category_display_in_food_note_passes_check4() -> None:
    """Check 4: food_note using category display text (no restaurant names) passes.

    TemplateProvider produces: 'Nearby food options include: Italian restaurant.'
    'Italian' is Title-Case but 'restaurant' is lowercase -- no multi-word Title-Case
    match -- so check #4 does not fire.
    """
    inp = _base_input()
    inp = inp.model_copy(update={
        "food_recommendations": [],
        "food_categories": ["italian_restaurant"],
    })
    exp = _clean_explanation(inp)
    exp = exp.model_copy(update={
        "food_note": "Nearby food options include: Italian restaurant.",
    })
    is_safe, violations = validate_explanation(exp, inp)
    assert is_safe, (
        f"Expected category-based food note to pass. Got violations: {violations}"
    )
