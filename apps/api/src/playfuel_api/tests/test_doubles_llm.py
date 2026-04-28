"""TemplateProvider doubles-aware prose tests — DOUBLES_SPEC_V1.md §C.2.

When match_type == 'doubles', TemplateProvider must use "you and your partner" /
"your doubles team" subject language in summary and scenario_explanations.
When match_type == 'singles', those phrases must NOT appear.

Covers:
    1. Doubles input → summary contains "partner" or "team"
    2. Singles input → summary does NOT contain "partner"
    3. Doubles input → scenario_explanations contain "partner" or "team" for each scenario
    4. Singles input → scenario_explanations do NOT contain "partner"
    5. Doubles summary identifies the correct venue + round label
    6. Doubles plan provider is still "template"
    7. Doubles explanation has all 3 scenario_explanation keys (short/normal/long)
"""
from __future__ import annotations

import pytest

from playfuel_api.models.api import (
    FoodRecommendationSummary,
    PlanExplanationInput,
    ScenarioSummary,
)
from playfuel_api.rules.hard_coded_strings import USER_DISCLAIMER
from playfuel_api.services.llm import TemplateProvider

# ── Shared fixtures ───────────────────────────────────────────────────────────

_SCENARIOS_DOUBLES = [
    ScenarioSummary(
        scenario="short",
        duration_min=60,
        gap_status="ok",
        food_bucket="portable",
        pickup_bucket="wait_until_end",
    ),
    ScenarioSummary(
        scenario="normal",
        duration_min=90,
        gap_status="ok",
        food_bucket="quick_pickup",
        pickup_bucket="wait_until_end",
    ),
    ScenarioSummary(
        scenario="long",
        duration_min=135,
        gap_status="tight",
        food_bucket="bag_only",
        pickup_bucket="bring_portable",
    ),
]

_SCENARIOS_SINGLES = [
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
    FoodRecommendationSummary(
        name="Chipotle",
        category="fast_casual_bowl",
        drive_time_minutes=5,
        is_draft=False,
    ),
]


def _doubles_input(**overrides) -> PlanExplanationInput:
    defaults = dict(
        venue_name="SMU Tennis Center",
        match_start_iso="2026-06-14T09:00:00+00:00",
        match_round_label="QF",
        next_match_estimated_iso="2026-06-14T13:00:00+00:00",
        weather_temp_f=85.0,
        weather_humidity_pct=60,
        weather_flags=["hot"],
        extreme_heat_risk=False,
        scenarios=_SCENARIOS_DOUBLES,
        food_recommendations=_FOOD_RECS,
        bag_fallback_only=False,
        heat_emergency_text=None,
        user_disclaimer=USER_DISCLAIMER,
        match_type="doubles",
    )
    defaults.update(overrides)
    return PlanExplanationInput(**defaults)


def _singles_input(**overrides) -> PlanExplanationInput:
    defaults = dict(
        venue_name="SMU Tennis Center",
        match_start_iso="2026-06-14T09:00:00+00:00",
        match_round_label="R16",
        next_match_estimated_iso="2026-06-14T13:00:00+00:00",
        weather_temp_f=85.0,
        weather_humidity_pct=60,
        weather_flags=["hot"],
        extreme_heat_risk=False,
        scenarios=_SCENARIOS_SINGLES,
        food_recommendations=_FOOD_RECS,
        bag_fallback_only=False,
        heat_emergency_text=None,
        user_disclaimer=USER_DISCLAIMER,
        match_type="singles",
    )
    defaults.update(overrides)
    return PlanExplanationInput(**defaults)


# ── Test 1: doubles summary contains partner/team ────────────────────────────


def test_doubles_summary_contains_partner_or_team():
    """Doubles explain_plan summary must contain 'partner' or 'team'."""
    exp = TemplateProvider().explain_plan(_doubles_input())
    summary_lower = exp.summary.lower()
    assert "partner" in summary_lower or "team" in summary_lower, (
        f"Doubles summary should mention 'partner' or 'team'. Got: {exp.summary!r}"
    )


# ── Test 2: singles summary does NOT contain 'partner' ───────────────────────


def test_singles_summary_does_not_contain_partner():
    """Singles explain_plan summary must NOT contain 'partner'."""
    exp = TemplateProvider().explain_plan(_singles_input())
    assert "partner" not in exp.summary.lower(), (
        f"Singles summary must not mention 'partner'. Got: {exp.summary!r}"
    )


# ── Test 3: doubles scenario_explanations contain partner/team ───────────────


def test_doubles_scenario_explanations_contain_partner_or_team():
    """Each doubles scenario explanation must contain 'partner' or 'team'."""
    exp = TemplateProvider().explain_plan(_doubles_input())
    for key in ("short", "normal", "long"):
        text = exp.scenario_explanations.get(key, "").lower()
        assert "partner" in text or "team" in text, (
            f"Doubles scenario_explanations['{key}'] should mention 'partner' or 'team'. "
            f"Got: {exp.scenario_explanations.get(key)!r}"
        )


# ── Test 4: singles scenario_explanations do NOT contain 'partner' ───────────


def test_singles_scenario_explanations_do_not_contain_partner():
    """Singles scenario explanations must NOT contain 'partner'."""
    exp = TemplateProvider().explain_plan(_singles_input())
    for key in ("short", "normal", "long"):
        text = exp.scenario_explanations.get(key, "").lower()
        assert "partner" not in text, (
            f"Singles scenario_explanations['{key}'] must not mention 'partner'. "
            f"Got: {exp.scenario_explanations.get(key)!r}"
        )


# ── Test 5: doubles summary includes correct venue + round ───────────────────


def test_doubles_summary_includes_venue_and_round():
    """Doubles summary must include venue_name and match_round_label."""
    inp = _doubles_input(venue_name="SMU Tennis Center", match_round_label="QF")
    exp = TemplateProvider().explain_plan(inp)
    assert "SMU Tennis Center" in exp.summary, (
        f"Doubles summary should include venue name. Got: {exp.summary!r}"
    )
    assert "QF" in exp.summary, (
        f"Doubles summary should include round label. Got: {exp.summary!r}"
    )


# ── Test 6: doubles provider is still 'template' ─────────────────────────────


def test_doubles_explain_plan_provider_is_template():
    """TemplateProvider.explain_plan for doubles must return provider='template'."""
    exp = TemplateProvider().explain_plan(_doubles_input())
    assert exp.provider == "template", (
        f"Expected provider='template'. Got: {exp.provider!r}"
    )
    assert exp.model is None


# ── Test 7: doubles explanation has all 3 scenario keys ──────────────────────


def test_doubles_explain_plan_has_all_three_scenario_keys():
    """Doubles explain_plan must return short/normal/long scenario explanations."""
    exp = TemplateProvider().explain_plan(_doubles_input())
    assert set(exp.scenario_explanations.keys()) == {"short", "normal", "long"}, (
        f"Expected short/normal/long. Got: {list(exp.scenario_explanations.keys())}"
    )
