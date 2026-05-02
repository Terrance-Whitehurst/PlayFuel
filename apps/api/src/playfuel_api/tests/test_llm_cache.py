"""LLM explanation cache unit tests — Opt-B perf PR.

Tests:
    1. test_cache_key_excludes_opponent_notes  — SEC-P6-2 invariant: same key regardless of notes.
    2. test_cache_hit_skips_llm_call           — route uses cached explanation, skips LLM provider.
    3. test_cache_miss_writes_through          — LLM called on miss, result upserted to cache.
    4. test_cache_expired_treated_as_miss      — expired row returns None from _read_llm_cache.

All tests use mock Supabase client and mock LLM provider — no real network calls.
Route-level tests follow the existing conftest.py mock_db pattern (table dispatch via side_effect).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID


# ─── Shared fixtures ─────────────────────────────────────────────────────────

_TID = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_MID = "c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"


def _minimal_match() -> dict:
    """Single-match fixture — 9 AM singles match, no second match."""
    return {
        "id": _MID,
        "tournament_id": _TID,
        "scheduled_start": "2026-05-15T14:00:00+00:00",
        "estimated_duration_minutes": None,
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "age_bracket": "14U",
        "display_order": 1,
        "round_label": "R16",
        "opponent_label": None,
        "court_label": None,
        "opponent_player_id": None,
        "doubles_format": None,
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }


def _future_expires() -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(days=7)).isoformat()


def _cached_explanation_row() -> dict:
    """A valid PlanExplanation row stored in llm_explanation_cache."""
    return {
        "response_json": {
            "summary": "Cached summary from prior run.",
            "scenarioExplanations": {
                "short": "Short scenario.",
                "normal": "Normal scenario.",
                "long": "Long scenario.",
            },
            "weatherNote": None,
            "foodNote": None,
            "safetyNote": "Consult a professional for medical concerns.",
            "provider": "template",
            "model": None,
            "generatedAt": "2026-05-01T00:00:00+00:00",
        },
        "expires_at": _future_expires(),
    }


def _build_mock_db_for_cache_hit() -> MagicMock:
    """Return a mock_db configured for a single-match generate_plan request
    where the LLM cache returns a hit.

    Table dispatch:
      matches              → one match row
      tournaments          → venue with lat/lng
      llm_explanation_cache → hit (valid non-expired row)
      plans                → upsert succeeds
    """
    mock_db = MagicMock()

    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = [
        _minimal_match()
    ]

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"venue_lat": 32.776664, "venue_lng": -96.796988, "venue_name": "Test Club"}
    ]

    cache_chain = MagicMock()
    # _read_llm_cache: .table().select().eq().limit().execute().data
    cache_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        _cached_explanation_row()
    ]

    plans_chain = MagicMock()
    plans_chain.upsert.return_value.execute.return_value.data = [{}]

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "llm_explanation_cache": cache_chain,
            "plans": plans_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch
    return mock_db


def _build_mock_db_for_cache_miss() -> tuple[MagicMock, MagicMock]:
    """Return (mock_db, cache_chain) configured for a cache-miss scenario.

    cache_chain.select returns empty data (miss).
    cache_chain.upsert is a spy — assert it was called after the test.
    """
    mock_db = MagicMock()

    matches_chain = MagicMock()
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = [
        _minimal_match()
    ]

    tournaments_chain = MagicMock()
    tournaments_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"venue_lat": 32.776664, "venue_lng": -96.796988, "venue_name": "Test Club"}
    ]

    cache_chain = MagicMock()
    # Miss: select returns empty list
    cache_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    # Write: upsert returns success
    cache_chain.upsert.return_value.execute.return_value.data = [{}]

    plans_chain = MagicMock()
    plans_chain.upsert.return_value.execute.return_value.data = [{}]

    def _dispatch(name: str) -> MagicMock:
        return {
            "matches": matches_chain,
            "tournaments": tournaments_chain,
            "llm_explanation_cache": cache_chain,
            "plans": plans_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch
    return mock_db, cache_chain


# ─── Test 1: Cache key excludes opponent_notes (SEC-P6-2 invariant) ──────────

def test_cache_key_excludes_opponent_notes():
    """Cache key is identical regardless of opponent_notes content.

    SEC-P6-2 invariant: routes/plans.build_explanation_input() NEVER populates
    opponent_notes — tactical text must not be serialised to a third-party API.
    The cache key computation explicitly excludes opponent_notes so PII cannot
    contribute to the hash even if the production contract is violated.

    This test constructs two PlanExplanationInputs that differ ONLY in
    opponent_notes and asserts their cache keys are identical.
    """
    from playfuel_api.models.api import OpponentNoteForLLM, PlanExplanationInput
    from playfuel_api.routes.plans import _llm_cache_key

    base_kwargs: dict = {
        "venue_name": "Delray Beach Tennis Center",
        "match_start_iso": "2026-05-15T14:00:00+00:00",
        "user_disclaimer": "Consult a qualified professional for injury concerns.",
    }

    inp_no_notes = PlanExplanationInput(**base_kwargs, opponent_notes=[])
    inp_with_notes = PlanExplanationInput(
        **base_kwargs,
        opponent_notes=[
            OpponentNoteForLLM(
                source="observed",
                age_days=3,
                body_paraphrasable="Strong topspin backhand; struggles returning wide serves.",
            ),
            OpponentNoteForLLM(
                source="post_match",
                age_days=10,
                body_paraphrasable="Tends to push at 4–4 in the third set.",
            ),
        ],
    )

    key_no_notes = _llm_cache_key(inp_no_notes)
    key_with_notes = _llm_cache_key(inp_with_notes)

    assert key_no_notes == key_with_notes, (
        "Cache key must not incorporate opponent_notes. "
        "SEC-P6-2: tactical PII must never contribute to a shared cache key. "
        f"key_no_notes={key_no_notes!r}, key_with_notes={key_with_notes!r}"
    )


# ─── Test 2: Cache hit — LLM provider is NOT called ─────────────────────────

def test_cache_hit_skips_llm_call(client_with_auth, mock_db):
    """POST plans/generate returns cached explanation without calling the LLM provider.

    When llm_explanation_cache has a valid (non-expired) row for the plan input,
    routes/plans.py short-circuits the LLM call and returns the cached PlanExplanation.

    This test:
      1. Configures mock_db.table("llm_explanation_cache") to return a cache hit.
      2. Patches get_llm_provider to return a spy (tracks whether explain_plan is called).
      3. Asserts the spy's explain_plan() was NOT invoked.
      4. Asserts the response carries the cached provider='template' value.
    """
    # Reconfigure mock_db with the cache-hit table dispatch
    cache_mock_db = _build_mock_db_for_cache_hit()
    # client_with_auth injects mock_db via authed_client override — we need to
    # replace the DB used inside the route. Re-override the dependency for this test.
    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    # Inline override: replace mock_db with our cache-aware version.
    # conftest's client_with_auth already sets overrides; we update authed_client here.
    original_override = app.dependency_overrides.get(authed_client)
    app.dependency_overrides[authed_client] = lambda: cache_mock_db

    try:
        # Spy on the LLM provider
        spy_provider = MagicMock()
        spy_provider.explain_plan = MagicMock(
            return_value=None,
            side_effect=AssertionError(
                "explain_plan() must NOT be called when cache has a valid hit"
            ),
        )

        with (
            patch(
                "playfuel_api.routes.plans.get_or_fetch_weather",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "playfuel_api.routes.plans.find_nearby_food",
                return_value=[],
            ),
            patch(
                "playfuel_api.routes.plans.get_llm_provider",
                return_value=spy_provider,
            ),
        ):
            resp = client_with_auth.post(f"/v1/tournaments/{_TID}/plans/generate")

    finally:
        # Restore the original override (conftest's mock_db)
        if original_override is not None:
            app.dependency_overrides[authed_client] = original_override
        else:
            app.dependency_overrides.pop(authed_client, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "singlesPlans" in body
    plans = body["singlesPlans"]
    assert len(plans) == 1
    # llmSummary must be populated from the cache (provider="template")
    assert plans[0]["llmSummary"] is not None, "llmSummary must come from cache"
    assert plans[0]["llmSummary"]["provider"] == "template"
    assert plans[0]["llmSummary"]["summary"] == "Cached summary from prior run."
    # The spy was never called (no AssertionError raised above means explain_plan not invoked)
    spy_provider.explain_plan.assert_not_called()


# ─── Test 3: Cache miss — LLM called and result written to cache ─────────────

def test_cache_miss_writes_through(client_with_auth, mock_db):
    """POST plans/generate calls the LLM provider on a cache miss and writes the result.

    When llm_explanation_cache has no row (or returns empty data), the route:
      1. Calls llm_provider.explain_plan().
      2. Passes the result through sanitize_or_fallback().
      3. Writes the explanation to llm_explanation_cache via upsert.

    This test:
      1. Configures mock_db.table("llm_explanation_cache").select to return [].
      2. Uses TemplateProvider (deterministic) as the LLM provider.
      3. Asserts cache_chain.upsert was called exactly once with the explanation.
    """
    cache_mock_db, cache_chain = _build_mock_db_for_cache_miss()

    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app
    from playfuel_api.services.llm import TemplateProvider

    original_override = app.dependency_overrides.get(authed_client)
    app.dependency_overrides[authed_client] = lambda: cache_mock_db

    try:
        with (
            patch(
                "playfuel_api.routes.plans.get_or_fetch_weather",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "playfuel_api.routes.plans.find_nearby_food",
                return_value=[],
            ),
            patch(
                "playfuel_api.routes.plans.get_llm_provider",
                return_value=TemplateProvider(),
            ),
        ):
            resp = client_with_auth.post(f"/v1/tournaments/{_TID}/plans/generate")
    finally:
        if original_override is not None:
            app.dependency_overrides[authed_client] = original_override
        else:
            app.dependency_overrides.pop(authed_client, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    plans = body.get("singlesPlans", [])
    assert len(plans) == 1, "Expected 1 singles plan"

    # LLM result should be in the response (provider=template since no key)
    assert plans[0]["llmSummary"] is not None, "llmSummary must be populated on cache miss"

    # Cache write: upsert on llm_explanation_cache must have been called once
    cache_chain.upsert.assert_called_once()
    call_kwargs = cache_chain.upsert.call_args
    # First positional arg is the payload dict; on_conflict keyword arg
    upsert_payload = call_kwargs[0][0]  # first positional arg
    assert "cache_key" in upsert_payload, "upsert payload must include cache_key"
    assert "response_json" in upsert_payload, "upsert payload must include response_json"
    assert "expires_at" in upsert_payload, "upsert payload must include expires_at"
    # Verify on_conflict was specified correctly
    assert call_kwargs[1].get("on_conflict") == "cache_key", (
        "upsert must use on_conflict='cache_key' for idempotent writes"
    )


# ─── Test 4: Expired cache row treated as miss ───────────────────────────────

def test_cache_expired_treated_as_miss():
    """_read_llm_cache returns None when the cached row's expires_at is in the past.

    This test directly invokes _read_llm_cache with a mock client that returns
    a row with expires_at set 1 hour in the past. The function must return None,
    not a PlanExplanation — signalling a miss so the route falls through to the LLM.
    """
    from playfuel_api.models.api import PlanExplanationInput
    from playfuel_api.routes.plans import _read_llm_cache

    # Build an expired row
    past_expires = (datetime.now(tz=timezone.utc) - timedelta(hours=1)).isoformat()
    expired_row = {
        "response_json": {
            "summary": "This summary is stale.",
            "scenarioExplanations": {"normal": "Normal."},
            "safetyNote": "Consult a professional.",
            "provider": "template",
            "model": None,
            "generatedAt": "2026-04-01T00:00:00+00:00",
        },
        "expires_at": past_expires,
    }

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        expired_row
    ]

    # Minimal exp_input for cache key computation
    exp_input = PlanExplanationInput(
        venue_name="Test Club",
        match_start_iso="2026-05-15T14:00:00+00:00",
        user_disclaimer="Consult a professional.",
    )

    result = _read_llm_cache(mock_client, exp_input)

    assert result is None, (
        "_read_llm_cache must return None for an expired cache row. "
        f"Got: {result!r} — expired rows must be treated as misses."
    )
