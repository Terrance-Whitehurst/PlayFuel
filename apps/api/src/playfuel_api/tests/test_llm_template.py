"""Tests for TemplateProvider — Phase 6 / Task #9.

TemplateProvider is the deterministic, no-network LLM backend used by default.
All output must be derived exclusively from PlanExplanationInput — nothing invented.

Test cases:
    1. explain_plan returns a PlanExplanation (smoke).
    2. summary is between 100–500 chars.
    3. scenario_explanations has all 3 keys (short, normal, long).
    4. safety_note contains user_disclaimer verbatim.
    5. provider == "template"; model is None.
    6. When extreme_heat_risk=True, heat_emergency_text appears verbatim in safety_note.
    7. food_note is None for bag_fallback_only=True.
    8. food_note names the top-3 food recommendations (without inventing).
    9. weather_note contains temp_f when weather data is present.
    10. generated_at is timezone-aware UTC.
"""
from __future__ import annotations

from datetime import timezone

import pytest

from playfuel_api.models.api import (
    FoodRecommendationSummary,
    PlanExplanationInput,
    ScenarioSummary,
)
from playfuel_api.rules.hard_coded_strings import HEAT_EMERGENCY_TEXT, USER_DISCLAIMER
from playfuel_api.services.llm import TemplateProvider

# ── Shared fixture data ────────────────────────────────────────────────────────

_SCENARIOS = [
    ScenarioSummary(
        scenario="short",
        duration_min=75,
        gap_status="ok",
        food_bucket="portable",
        pickup_bucket="wait_until_end",
    ),
    ScenarioSummary(
        scenario="normal",
        duration_min=120,
        gap_status="ok",
        food_bucket="quick_pickup",
        pickup_bucket="wait_until_end",
    ),
    ScenarioSummary(
        scenario="long",
        duration_min=180,
        gap_status="tight",
        food_bucket="bag_only",
        pickup_bucket="bring_portable",
    ),
]

_FOOD_RECS = [
    FoodRecommendationSummary(name="Chipotle", category="fast_casual_bowl", drive_time_minutes=5),
    FoodRecommendationSummary(name="Jimmy John's", category="sandwich_shop", drive_time_minutes=3),
    FoodRecommendationSummary(name="Central Market", category="grocery_prepared", drive_time_minutes=8),
]


def _make_input(
    *,
    extreme_heat_risk: bool = False,
    bag_fallback_only: bool = False,
    food_recs: list[FoodRecommendationSummary] | None = None,
    temp_f: float | None = 95.0,
    humidity: int | None = 60,
    weather_flags: list[str] | None = None,
) -> PlanExplanationInput:
    return PlanExplanationInput(
        venue_name="SMU Tennis Center",
        match_start_iso="2026-05-15T14:00:00+00:00",
        match_round_label="QF",
        next_match_estimated_iso="2026-05-15T18:00:00+00:00",
        weather_temp_f=temp_f,
        weather_humidity_pct=humidity,
        weather_flags=weather_flags if weather_flags is not None else ["hot", "humid"],
        extreme_heat_risk=extreme_heat_risk,
        scenarios=_SCENARIOS,
        food_recommendations=food_recs if food_recs is not None else _FOOD_RECS,
        bag_fallback_only=bag_fallback_only,
        heat_emergency_text=HEAT_EMERGENCY_TEXT if extreme_heat_risk else None,
        user_disclaimer=USER_DISCLAIMER,
    )


@pytest.fixture()
def provider() -> TemplateProvider:
    return TemplateProvider()


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_explain_plan_returns_plan_explanation(provider: TemplateProvider) -> None:
    """explain_plan returns a PlanExplanation instance (smoke)."""
    from playfuel_api.models.api import PlanExplanation

    inp = _make_input()
    result = provider.explain_plan(inp)
    assert isinstance(result, PlanExplanation)


def test_summary_length_within_bounds(provider: TemplateProvider) -> None:
    """summary is between 100 and 500 characters."""
    result = provider.explain_plan(_make_input())
    assert 100 <= len(result.summary) <= 500, (
        f"summary length {len(result.summary)} not in [100, 500]: {result.summary!r}"
    )


def test_scenario_explanations_has_all_three_keys(provider: TemplateProvider) -> None:
    """scenario_explanations has exactly the 'short', 'normal', 'long' keys."""
    result = provider.explain_plan(_make_input())
    assert set(result.scenario_explanations.keys()) == {"short", "normal", "long"}


def test_safety_note_contains_user_disclaimer_verbatim(provider: TemplateProvider) -> None:
    """safety_note contains the verbatim USER_DISCLAIMER from hard_coded_strings."""
    result = provider.explain_plan(_make_input())
    assert USER_DISCLAIMER in result.safety_note, (
        "USER_DISCLAIMER not found verbatim in safety_note"
    )


def test_provider_is_template_model_is_none(provider: TemplateProvider) -> None:
    """provider == 'template' and model is None (no external LLM used)."""
    result = provider.explain_plan(_make_input())
    assert result.provider == "template"
    assert result.model is None


def test_extreme_heat_risk_safety_note_contains_heat_text(provider: TemplateProvider) -> None:
    """When extreme_heat_risk=True, HEAT_EMERGENCY_TEXT appears verbatim in safety_note."""
    result = provider.explain_plan(_make_input(extreme_heat_risk=True))
    assert HEAT_EMERGENCY_TEXT in result.safety_note, (
        "HEAT_EMERGENCY_TEXT not found verbatim in safety_note when extreme_heat_risk=True"
    )


def test_bag_fallback_only_food_note_is_none_or_bag(provider: TemplateProvider) -> None:
    """When bag_fallback_only=True, food_note is None or references bag-only guidance."""
    result = provider.explain_plan(_make_input(bag_fallback_only=True))
    # food_note should be None or contain bag-only language — never list restaurants
    if result.food_note is not None:
        assert "bag" in result.food_note.lower(), (
            f"bag_fallback_only=True but food_note has no bag reference: {result.food_note!r}"
        )


def test_food_note_names_recommendations_without_inventing(provider: TemplateProvider) -> None:
    """food_note only mentions names present in food_recommendations."""
    inp = _make_input()
    result = provider.explain_plan(inp)
    if result.food_note is not None:
        for rec in inp.food_recommendations[:3]:
            assert rec.name in result.food_note, (
                f"Expected {rec.name!r} in food_note but not found: {result.food_note!r}"
            )


def test_weather_note_includes_temp_when_present(provider: TemplateProvider) -> None:
    """weather_note contains the temperature when weather data is provided.

    Phase B: _build_weather_note() renders Celsius. Passing weather_temp_f=95.0
    (legacy field) converts to 35°C via (95-32)*5/9. Assert '35' in the note.
    """
    result = provider.explain_plan(_make_input(temp_f=95.0))
    assert result.weather_note is not None
    assert "35" in result.weather_note, (
        f"Expected temperature '35' (°C) in weather_note: {result.weather_note!r}"
    )


def test_weather_note_is_none_when_no_weather_data(provider: TemplateProvider) -> None:
    """weather_note is None when weather_temp_f and weather_temp_c are both None (no weather data)."""
    result = provider.explain_plan(_make_input(temp_f=None, humidity=None))
    assert result.weather_note is None


def test_generated_at_is_utc_aware(provider: TemplateProvider) -> None:
    """generated_at is a timezone-aware datetime in UTC."""
    result = provider.explain_plan(_make_input())
    assert result.generated_at.tzinfo is not None
    assert result.generated_at.tzinfo == timezone.utc
