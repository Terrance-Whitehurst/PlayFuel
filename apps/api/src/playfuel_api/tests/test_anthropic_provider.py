"""Tests for AnthropicProvider — Phase 6 / Task #9.

AC-LLM-5: Happy path — mocked Anthropic client returns valid tool_use block →
           PlanExplanation with provider="anthropic", model="claude-3-5-haiku-latest".

AC-LLM-6: Prohibited phrase in LLM output → sanitize_or_fallback fires →
           returned PlanExplanation has provider="template" (never returns the bad text).

AC-LLM-7: httpx.TimeoutException raised by mocked client → plans.py outer except
           catches it → route returns HTTP 200 with llmSummary: null (graceful degrade).

AC-LLM-8: build_explanation_input() output serialization contains NO user_id,
           place_id, raw venue_lat, or raw venue_lng values (PII is stripped at source).
           Also: specific restaurant names are absent (SEC-P6-1) — food_categories
           only contains bucket names, not restaurant names.

AC-LLM-SEC-P6-2: build_explanation_input() never populates opponent_notes —
           serialized output does not contain any sentinel note body string.

Mocking strategy:
    - AC-LLM-5 / 6: patch `anthropic.Anthropic` (class in the installed module)
      so self._anthropic.Anthropic(...) returns the mock instance.
    - AC-LLM-7: inject a one-off provider stub via
      patch("playfuel_api.routes.plans.get_llm_provider").
    - AC-LLM-8: no mocking needed — build_explanation_input() is a pure function.

Rule: anthropic SDK (installed as dep) is never called with real network.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from playfuel_api.models.api import (
    FoodOption,
    FoodRecommendationSummary,
    PlanExplanationInput,
    ScenarioSummary,
)
from playfuel_api.rules.hard_coded_strings import USER_DISCLAIMER
from playfuel_api.services.llm import AnthropicProvider, build_explanation_input

# ── Shared test IDs ────────────────────────────────────────────────────────────

_TID = "b2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_MID1 = "c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_MID2 = "d2eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

# ── Shared plan input ──────────────────────────────────────────────────────────


def _make_plan_input(
    *,
    extra_scenarios: bool = False,
) -> PlanExplanationInput:
    """Build a minimal PlanExplanationInput for use in unit tests."""
    scenarios = [
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
    return PlanExplanationInput(
        venue_name="Delray Beach Tennis Center",
        match_start_iso="2026-06-01T09:00:00+00:00",
        match_round_label="QF",
        next_match_estimated_iso="2026-06-01T14:00:00+00:00",
        weather_temp_f=88.0,
        weather_humidity_pct=72,
        weather_flags=["hot", "humid"],
        extreme_heat_risk=False,
        scenarios=scenarios,
        food_recommendations=[
            FoodRecommendationSummary(
                name="Caffe Luna Rosa",
                category="italian_restaurant",
                drive_time_minutes=6,
            ),
        ],
        bag_fallback_only=False,
        heat_emergency_text=None,
        user_disclaimer=USER_DISCLAIMER,
        match_type="singles",
    )


# ── Mock DB helper (mirrors test_llm_routes._make_mock_db) ────────────────────


def _make_mock_db() -> MagicMock:
    """Build a per-table dispatching MagicMock for the plans-generate route."""
    match1 = {
        "id": _MID1,
        "tournament_id": _TID,
        "scheduled_start": "2026-06-01T09:00:00+00:00",
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "age_bracket": "14U",
        "display_order": 1,
        "round_label": "QF",
        "opponent_label": None,
        "court_label": "Court 1",
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }
    match2 = {
        **match1,
        "id": _MID2,
        "scheduled_start": "2026-06-01T14:00:00+00:00",
        "display_order": 2,
        "round_label": "SF",
    }

    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = [
        match1,
        match2,
    ]

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {
            "venue_lat": 26.4615,
            "venue_lng": -80.0728,
            "venue_name": "Delray Beach Tennis Center",
        },
    ]

    plans_chain = MagicMock()  # upsert return value is ignored by the route

    mock_db = MagicMock()

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "plans": plans_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch
    return mock_db


# ── AC-LLM-5: happy path ──────────────────────────────────────────────────────


def test_anthropic_provider_happy_path_returns_plan_explanation() -> None:
    """AC-LLM-5: Mocked Anthropic client returns valid tool_use block.

    Asserts:
    - Returned PlanExplanation has provider="anthropic".
    - model matches the value passed to AnthropicProvider.__init__.
    - summary, scenario_explanations, safety_note are populated.
    - scenario_explanations has all three scenario keys.
    """
    model_name = "claude-3-5-haiku-latest"

    # Build a fake tool_use content block.
    fake_tool = MagicMock()
    fake_tool.type = "tool_use"
    fake_tool.input = {
        "summary": (
            "Your player's tournament day at Delray Beach Tennis Center "
            "includes a QF match scheduled to start at Sunday at 9:00 AM. "
            "We've prepared three scenarios—short, normal, and long."
        ),
        "scenario_explanations": {
            "short": "Short scenario (1 hr 15 min): comfortable break.",
            "normal": "Normal scenario (2 hr): comfortable break. Quick pickup recommended.",
            "long": "Long scenario (3 hr): tight turnaround. Bag food only.",
        },
        "safety_note": USER_DISCLAIMER,
    }

    fake_response = MagicMock()
    fake_response.content = [fake_tool]
    fake_response.usage.input_tokens = 350
    fake_response.usage.output_tokens = 175

    # Patch anthropic.Anthropic so no real network call is made.
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client_instance = mock_anthropic_cls.return_value
        mock_client_instance.messages.create.return_value = fake_response

        provider = AnthropicProvider(api_key="sk-ant-test", model=model_name)
        result = provider.explain_plan(_make_plan_input())

    assert result.provider == "anthropic", (
        f"Expected provider='anthropic', got {result.provider!r}"
    )
    assert result.model == model_name, (
        f"Expected model={model_name!r}, got {result.model!r}"
    )
    assert result.summary, "summary must not be empty"
    assert "short" in result.scenario_explanations, "scenario_explanations must contain 'short'"
    assert "normal" in result.scenario_explanations, "scenario_explanations must contain 'normal'"
    assert "long" in result.scenario_explanations, "scenario_explanations must contain 'long'"
    assert result.safety_note, "safety_note must not be empty"
    assert result.generated_at.tzinfo is not None, "generated_at must be timezone-aware"


# ── AC-LLM-6: prohibited phrase triggers sanitize_or_fallback ─────────────────


def test_anthropic_provider_prohibited_phrase_triggers_template_fallback() -> None:
    """AC-LLM-6: LLM returns §C prohibited phrase → sanitize_or_fallback fires.

    Asserts:
    - Returned PlanExplanation has provider="template" (not "anthropic").
    - The prohibited phrase does NOT appear in any field of the returned explanation.
    """
    _PROHIBITED = "This will prevent cramps."  # verbatim from PROHIBITED_PHRASES

    fake_tool = MagicMock()
    fake_tool.type = "tool_use"
    fake_tool.input = {
        "summary": (
            f"Your player's day includes a QF match. "
            f"{_PROHIBITED}"  # ← prohibited phrase injected
        ),
        "scenario_explanations": {
            "short": "Short scenario (1 hr 15 min): comfortable break.",
            "normal": "Normal scenario (2 hr): comfortable break.",
            "long": "Long scenario (3 hr): tight turnaround.",
        },
        "safety_note": USER_DISCLAIMER,
    }

    fake_response = MagicMock()
    fake_response.content = [fake_tool]
    fake_response.usage.input_tokens = 300
    fake_response.usage.output_tokens = 150

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client_instance = mock_anthropic_cls.return_value
        mock_client_instance.messages.create.return_value = fake_response

        provider = AnthropicProvider(
            api_key="sk-ant-test", model="claude-3-5-haiku-latest"
        )
        result = provider.explain_plan(_make_plan_input())

    assert result.provider == "template", (
        f"Expected provider='template' (fallback), got {result.provider!r}"
    )
    # Prohibited phrase must NOT appear anywhere in the explanation.
    all_text = " ".join(
        [result.summary]
        + list(result.scenario_explanations.values())
        + [result.safety_note or ""]
        + [result.weather_note or ""]
        + [result.food_note or ""]
    )
    assert _PROHIBITED.lower() not in all_text.lower(), (
        f"Prohibited phrase '{_PROHIBITED}' must not appear in fallback output"
    )


# ── AC-LLM-7: httpx.TimeoutException → 200 with llmSummary: null ─────────────


def test_anthropic_provider_timeout_returns_null_llm_summary(
    client_with_auth,  # type: ignore[no-untyped-def]
    mock_db,           # type: ignore[no-untyped-def]
) -> None:
    """AC-LLM-7: provider.explain_plan() raises httpx.TimeoutException.

    The outer try/except in routes/plans.py:279–282 catches it and sets
    llm_summary = None. The route must still return HTTP 200 with
    singlesPlans[0].llmSummary == null — not a 500.
    """
    mock_db.table.side_effect = _make_mock_db().table.side_effect

    class _TimeoutProvider:
        """Stub provider that always raises httpx.TimeoutException."""

        def explain_plan(self, inp):  # noqa: ANN001, ANN201
            raise httpx.TimeoutException("Simulated Anthropic timeout")

    with (
        patch(
            "playfuel_api.routes.plans.get_or_fetch_weather",
            new_callable=AsyncMock,
        ) as mock_wx,
        patch("playfuel_api.routes.plans.find_nearby_food") as mock_food,
        patch(
            "playfuel_api.routes.plans.get_llm_provider",
            return_value=_TimeoutProvider(),
        ),
    ):
        mock_wx.return_value = None  # no weather snapshot
        mock_food.return_value = []  # no food recs

        resp = client_with_auth.post(f"/v1/tournaments/{_TID}/plans/generate")

    assert resp.status_code == 200, (
        f"Expected 200 on provider timeout, got {resp.status_code}. Body: {resp.text[:500]}"
    )
    body = resp.json()
    assert "singlesPlans" in body, f"Expected 'singlesPlans' key. Got: {list(body.keys())}"
    assert len(body["singlesPlans"]) > 0, "singlesPlans must be non-empty"

    plan = body["singlesPlans"][0]
    assert plan is not None, "singlesPlans[0] must not be null"

    # The critical assertion: llmSummary must be null (not an error, not a crash).
    assert plan.get("llmSummary") is None, (
        f"Expected llmSummary=null on timeout. Got: {plan.get('llmSummary')!r}"
    )


# ── AC-LLM-8: build_explanation_input() strips PII ───────────────────────────


def test_build_explanation_input_strips_pii() -> None:
    """AC-LLM-8: build_explanation_input() output contains no PII.

    Verifies that the following values never appear in the serialized
    PlanExplanationInput JSON:
    - A user_id UUID (a0eebc99-...) — not a field in PlanExplanationInput
    - A food-option place_id string (ChIJABC123xyzPlaceId)
    - Raw venue latitude (26.4615) or longitude (-80.0728)

    build_explanation_input() only copies name/category/drive_time/is_draft
    from FoodOption, dropping place_id, lat, lng.
    """
    import uuid
    from unittest.mock import MagicMock

    # Sentinel values that should NOT appear in the output.
    _SENTINEL_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    _SENTINEL_PLACE_ID = "ChIJABC123xyzPlaceId"
    _SENTINEL_LAT = "26.4615"
    _SENTINEL_LNG = "-80.0728"

    # ── Build mock plan (Plan model) ──────────────────────────────────────────
    # build_explanation_input only reads: plan.scenario_plans, plan.bag_fallback_only
    from playfuel_api.models.enums import FoodBucket, GapStatus, PickupBucket, ScenarioKind

    mock_food_strategy = MagicMock()
    mock_food_strategy.bucket = FoodBucket.quick_pickup

    mock_pickup_strategy = MagicMock()
    mock_pickup_strategy.bucket = PickupBucket.wait_until_end

    mock_scenario = MagicMock()
    mock_scenario.scenario = ScenarioKind.normal
    mock_scenario.duration_min = 120
    mock_scenario.gap_status = GapStatus.ok
    mock_scenario.food_strategy = mock_food_strategy
    mock_scenario.pickup_strategy = mock_pickup_strategy

    mock_plan = MagicMock()
    mock_plan.scenario_plans = [mock_scenario]
    mock_plan.bag_fallback_only = False

    # ── Build mock match (MatchRow) ───────────────────────────────────────────
    # build_explanation_input reads: match.scheduled_start, match.round_label, match.format
    mock_match = MagicMock()
    mock_match.scheduled_start = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
    mock_match.round_label = "QF"
    mock_match.format = "singles"
    mock_match.opponent_player_id = None

    # ── Build FoodOption with PII fields set ──────────────────────────────────
    food_option = FoodOption(
        name="Caffe Luna Rosa",
        category="italian_restaurant",
        drive_time_minutes=6,
        recommended_order="Pasta with marinara sauce",
        is_draft=True,
        place_id=_SENTINEL_PLACE_ID,  # ← PII: should NOT appear in output
        provider="google",
        lat=float(_SENTINEL_LAT),    # ← PII: should NOT appear in output
        lng=float(_SENTINEL_LNG),    # ← PII: should NOT appear in output
    )

    # ── Call build_explanation_input ──────────────────────────────────────────
    # venue_name is passed as a plain string (no lat/lng/place_id here).
    result = build_explanation_input(
        plan=mock_plan,
        match=mock_match,
        next_match=None,
        snapshot=None,
        food_options_list=[food_option],
        venue_name="Delray Beach Tennis Center",
    )

    # ── Serialize and check for PII ───────────────────────────────────────────
    serialized = result.model_dump_json()

    assert _SENTINEL_PLACE_ID not in serialized, (
        f"place_id '{_SENTINEL_PLACE_ID}' must not appear in PlanExplanationInput output. "
        f"Found in: {serialized}"
    )
    assert _SENTINEL_LAT not in serialized, (
        f"Raw lat '{_SENTINEL_LAT}' must not appear in PlanExplanationInput output. "
        f"Found in: {serialized}"
    )
    assert _SENTINEL_LNG not in serialized, (
        f"Raw lng '{_SENTINEL_LNG}' must not appear in PlanExplanationInput output. "
        f"Found in: {serialized}"
    )
    assert _SENTINEL_USER_ID not in serialized, (
        f"user_id '{_SENTINEL_USER_ID}' must not appear in PlanExplanationInput output. "
        f"Found in: {serialized}"
    )

    # SEC-P6-1: restaurant NAME must be ABSENT — build_explanation_input() now
    # populates food_categories (bucket name only), not food_recommendations.
    # Sending specific restaurant names to an external LLM is prohibited.
    assert "Caffe Luna Rosa" not in serialized, (
        "food recommendation name 'Caffe Luna Rosa' must NOT appear in PlanExplanationInput output. "
        "SEC-P6-1: build_explanation_input() must send food_categories, not restaurant names. "
        f"Found in: {serialized}"
    )
    # Category bucket name MUST be present.
    assert "italian_restaurant" in serialized, (
        "food category bucket 'italian_restaurant' must appear in PlanExplanationInput output"
    )


# ── AC-LLM-SEC-P6-2: build_explanation_input() never populates opponent_notes ─────


def test_build_explanation_input_strips_opponent_notes() -> None:
    """SEC-P6-2: build_explanation_input() produces PlanExplanationInput with
    empty opponent_notes — serialized output does not contain any sentinel note text.

    The route previously attached notes via `exp_input.opponent_notes = ...` after
    build_explanation_input() returned. That line is now removed. This test verifies
    the builder itself never populates opponent_notes.
    """
    from datetime import datetime, timezone
    from unittest.mock import MagicMock

    _SENTINEL_NOTE_BODY = "OPPONENT_NOTE_LEAK_SENTINEL_xyz123"

    # Build mock objects (same pattern as AC-LLM-8)
    from playfuel_api.models.enums import FoodBucket, GapStatus, PickupBucket, ScenarioKind

    mock_food_strategy = MagicMock()
    mock_food_strategy.bucket = FoodBucket.quick_pickup

    mock_pickup_strategy = MagicMock()
    mock_pickup_strategy.bucket = PickupBucket.wait_until_end

    mock_scenario = MagicMock()
    mock_scenario.scenario = ScenarioKind.normal
    mock_scenario.duration_min = 120
    mock_scenario.gap_status = GapStatus.ok
    mock_scenario.food_strategy = mock_food_strategy
    mock_scenario.pickup_strategy = mock_pickup_strategy

    mock_plan = MagicMock()
    mock_plan.scenario_plans = [mock_scenario]
    mock_plan.bag_fallback_only = False

    mock_match = MagicMock()
    mock_match.scheduled_start = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
    mock_match.round_label = "QF"
    mock_match.format = "singles"
    mock_match.opponent_player_id = None

    # Call build_explanation_input (does NOT receive notes — they were attached
    # after-the-fact in the route, which is the code we removed)
    result = build_explanation_input(
        plan=mock_plan,
        match=mock_match,
        next_match=None,
        snapshot=None,
        food_options_list=[],
        venue_name="Test Venue",
    )

    # Verify opponent_notes is empty by default
    assert result.opponent_notes == [], (
        f"build_explanation_input must not populate opponent_notes. Got: {result.opponent_notes!r}"
    )

    # Positive-absence check: serialize and confirm sentinel string is absent
    serialized = result.model_dump_json()
    assert _SENTINEL_NOTE_BODY not in serialized, (
        f"Sentinel note body '{_SENTINEL_NOTE_BODY}' must not appear in PlanExplanationInput. "
        f"Found in: {serialized}"
    )
