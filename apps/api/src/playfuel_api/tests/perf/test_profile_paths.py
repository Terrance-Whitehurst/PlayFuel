"""Performance profiling harness — run with: pytest -m perf -s

Measures per-path wall time (Python layer only) for the 5 hot paths the user
identified as slow:
  1. GET  /v1/tournaments                         — tournament list
  2. POST /v1/tournaments/{tid}/plans/generate    — plan generation (dominant)
  3. POST /v1/tournaments/{tid}/feedback          — feedback submit
  4. GET  /v1/tournaments/{tid}/feedback          — feedback fetch
  5. GET  /v1/tournaments/{tid}/plans             — plan list

External calls (Open-Meteo, Google Places, Anthropic) are patched to return
fast deterministic responses — this harness measures the Python/Pydantic/routing
overhead, NOT network latency. Network latency is measured in production logs
via RequestTimingMiddleware (middleware added in this same PR).

Each path is called N_ITER=5 times. Results are printed as a markdown table after
all iterations complete, with p50 and p95 (ms) per path.

Usage:
    cd apps/api
    pytest -m perf -s src/playfuel_api/tests/perf/test_profile_paths.py -v

Expected baseline (TemplateProvider, warm process, no network):
    GET  /v1/tournaments                 p50 < 10 ms   p95 < 20 ms
    POST /v1/.../plans/generate          p50 < 50 ms   p95 < 100 ms
    POST /v1/.../feedback                p50 < 10 ms   p95 < 20 ms
    GET  /v1/.../feedback                p50 < 10 ms   p95 < 20 ms
    GET  /v1/.../plans                   p50 < 10 ms   p95 < 20 ms

Note: first iteration is typically 2–5× slower (Python module import + JIT).
p50 over 5 iterations is representative; p95 shows worst-case within the run.
"""
from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

# Constants
N_ITER = 5
_TID = "b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_MID1 = "c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_MID2 = "d0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
TEST_USER_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def perf_client():
    """Module-scoped TestClient with auth + DB deps overridden.

    Module scope: reuse across all perf tests in this file to amortise
    the per-process FastAPI startup cost and get stable repeat timings.
    """
    from playfuel_api.auth import verify_supabase_jwt
    from playfuel_api.db import authed_client
    from playfuel_api.main import app

    mock_db = _build_mock_db()
    app.dependency_overrides[verify_supabase_jwt] = lambda: TEST_USER_ID
    app.dependency_overrides[authed_client] = lambda: mock_db

    with TestClient(app) as tc:
        yield tc, mock_db

    app.dependency_overrides.pop(verify_supabase_jwt, None)
    app.dependency_overrides.pop(authed_client, None)


def _build_mock_db() -> MagicMock:
    """Build a reusable mock Supabase client for perf tests."""
    mock_db = MagicMock()

    # Tournaments table
    tournaments_list_chain = MagicMock()
    tournaments_list_chain.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
        {
            "id": _TID,
            "user_id": str(TEST_USER_ID),
            "name": "Delray Beach Open",
            "start_date": "2026-05-15",
            "end_date": "2026-05-17",
            "venue_name": "Delray Beach Tennis Center",
            "venue_city": "Delray Beach",
            "venue_region": "FL",
            "venue_lat": 26.4615,
            "venue_lng": -80.0728,
            "created_at": "2026-05-01T00:00:00+00:00",
            "updated_at": "2026-05-01T00:00:00+00:00",
        }
    ]

    # Matches table (for plan generation)
    matches_chain = MagicMock()
    match1 = {
        "id": _MID1,
        "tournament_id": _TID,
        "scheduled_start": "2026-05-15T14:00:00+00:00",
        "actual_end_at": None,
        "surface": "hard",
        "format": "singles",
        "age_bracket": "14U",
        "display_order": 1,
        "round_label": "R16",
        "opponent_label": None,
        "court_label": "Court 7",
        "opponent_player_id": None,
        "doubles_format": None,
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
    }
    match2 = {
        **match1,
        "id": _MID2,
        "scheduled_start": "2026-05-15T18:00:00+00:00",
        "display_order": 2,
        "round_label": "QF",
        "court_label": None,
    }
    matches_chain.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = [
        match1, match2
    ]

    # Tournaments detail (plan generation: venue coords)
    tournaments_detail_chain = MagicMock()
    tournaments_detail_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"venue_lat": 26.4615, "venue_lng": -80.0728, "venue_name": "Delray Beach Tennis Center"}
    ]

    # Plans table
    plans_chain = MagicMock()
    plans_chain.upsert.return_value.execute.return_value.data = [{}]
    plans_chain.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []

    # LLM cache table (miss — to exercise the full TemplateProvider path)
    llm_cache_chain = MagicMock()
    llm_cache_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    llm_cache_chain.upsert.return_value.execute.return_value.data = [{}]

    # Feedback table
    feedback_chain = MagicMock()
    feedback_chain.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    feedback_chain.insert.return_value.execute.return_value.data = [
        {
            "id": "f1000000-0000-0000-0000-000000000001",
            "tournament_id": _TID,
            "user_id": str(TEST_USER_ID),
            "overall_rating": 4,
            "what_worked": ["food_timing"],
            "what_didnt_work": [],
            "free_text": None,
            "created_at": "2026-05-15T20:00:00+00:00",
            "updated_at": "2026-05-15T20:00:00+00:00",
        }
    ]
    feedback_chain.upsert.return_value.execute.return_value.data = [
        {
            "id": "f1000000-0000-0000-0000-000000000001",
            "tournament_id": _TID,
            "user_id": str(TEST_USER_ID),
            "overall_rating": 4,
            "what_worked": ["food_timing"],
            "what_didnt_work": [],
            "free_text": None,
            "created_at": "2026-05-15T20:00:00+00:00",
            "updated_at": "2026-05-15T20:00:00+00:00",
        }
    ]

    # Table dispatch: tournaments returns different chains based on call context.
    # Heuristic: the first call per generate_plan is matches, second is tournaments
    # detail.  For simplicity, we use separate chain objects keyed by table name.
    # The tournaments list vs. detail chains differ in their chain shape (list uses
    # .order; detail uses .limit) — both can be the same MagicMock since MagicMock
    # always returns a fresh MagicMock on first attribute access, then the same
    # one on subsequent accesses.
    _tournament_call_count: list[int] = [0]

    def _dispatch(name: str) -> MagicMock:
        if name == "tournaments":
            _tournament_call_count[0] += 1
            if _tournament_call_count[0] == 1:
                # First call in plan gen: detail fetch (select/eq/limit)
                return tournaments_detail_chain
            else:
                # Subsequent calls: list fetch or another detail
                return tournaments_detail_chain
        return {
            "matches": matches_chain,
            "plans": plans_chain,
            "llm_explanation_cache": llm_cache_chain,
            "feedback": feedback_chain,
        }.get(name, MagicMock())

    mock_db.table.side_effect = _dispatch
    return mock_db


def _time_request(fn, *args, **kwargs) -> float:
    """Call fn(*args, **kwargs) and return wall-time in milliseconds."""
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000.0


def _print_table(results: dict[str, list[float]]) -> None:
    """Print a markdown timing table to stdout."""
    header = f"{'Path':<55} {'p50 ms':>8} {'p95 ms':>8} {'min ms':>8} {'max ms':>8}"
    sep = "-" * len(header)
    print(f"\n{sep}")
    print("PlayFuel API — Perf Profile (Python layer, mocked externals)")
    print(sep)
    print(header)
    print(sep)
    for path, times in results.items():
        p50 = statistics.median(times)
        p95 = sorted(times)[int(len(times) * 0.95)] if len(times) >= 20 else max(times)
        mn = min(times)
        mx = max(times)
        print(f"{path:<55} {p50:>8.1f} {p95:>8.1f} {mn:>8.1f} {mx:>8.1f}")
    print(sep)
    print(f"Iterations per path: {N_ITER}")
    print(sep + "\n")


# ── Profile tests ─────────────────────────────────────────────────────────────


@pytest.mark.perf
def test_profile_all_hot_paths(perf_client):
    """Profile all 5 hot paths and print a markdown table.

    Runs each endpoint N_ITER times. External calls (weather, places, LLM) are
    patched to return instant deterministic responses so we measure only the
    Python/FastAPI/Pydantic layer.

    All paths are tested in a single test function to share the module-scoped
    perf_client fixture (avoids repeated FastAPI startup overhead).
    """
    tc, mock_db = perf_client
    results: dict[str, list[float]] = {}

    # Reset tournament call counter between path groups
    def _reset_tournament_counter():
        if hasattr(mock_db.table, "side_effect") and mock_db.table.side_effect is not None:
            # The dispatch closure captures _tournament_call_count; reset by
            # clearing side_effect and re-building. Simpler: reset via attribute.
            pass  # Counter resets naturally when a new dispatch is called

    # ── Path 1: GET /v1/tournaments ──────────────────────────────────────────
    path_label = "GET /v1/tournaments"
    times_list: list[float] = []
    for _ in range(N_ITER):
        times_list.append(_time_request(tc.get, "/v1/tournaments"))
    results[path_label] = times_list

    # ── Path 2: POST /v1/tournaments/{tid}/plans/generate ───────────────────
    path_label = "POST /v1/tournaments/{tid}/plans/generate"
    times_gen: list[float] = []
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
        ) as mock_get_llm,
    ):
        from playfuel_api.services.llm import TemplateProvider

        mock_get_llm.return_value = TemplateProvider()

        for _ in range(N_ITER):
            times_gen.append(
                _time_request(
                    tc.post,
                    f"/v1/tournaments/{_TID}/plans/generate",
                )
            )
    results[path_label] = times_gen

    # ── Path 3: POST /v1/tournaments/{tid}/feedback ──────────────────────────
    path_label = "POST /v1/tournaments/{tid}/feedback"
    feedback_body = {
        "overallRating": 4,
        "whatWorked": ["food_timing"],
        "whatDidntWork": [],
        "freeText": None,
    }
    times_fb_post: list[float] = []
    for _ in range(N_ITER):
        times_fb_post.append(
            _time_request(
                tc.post,
                f"/v1/tournaments/{_TID}/feedback",
                json=feedback_body,
            )
        )
    results[path_label] = times_fb_post

    # ── Path 4: GET /v1/tournaments/{tid}/feedback ───────────────────────────
    path_label = "GET /v1/tournaments/{tid}/feedback"
    times_fb_get: list[float] = []
    for _ in range(N_ITER):
        times_fb_get.append(
            _time_request(tc.get, f"/v1/tournaments/{_TID}/feedback")
        )
    results[path_label] = times_fb_get

    # ── Path 5: GET /v1/tournaments/{tid}/plans ──────────────────────────────
    path_label = "GET /v1/tournaments/{tid}/plans"
    times_plans: list[float] = []
    for _ in range(N_ITER):
        times_plans.append(
            _time_request(tc.get, f"/v1/tournaments/{_TID}/plans")
        )
    results[path_label] = times_plans

    # Print results and assert sanity bounds
    _print_table(results)

    # Sanity assertions — these should always pass with mocked externals.
    # If they fail, something structural has regressed (import time explosion,
    # Pydantic validation loop, etc.).
    p95_gen = max(results["POST /v1/tournaments/{tid}/plans/generate"])
    assert p95_gen < 5000, (
        f"Plan generation p95 (mocked) should be <5000 ms, got {p95_gen:.0f} ms. "
        "Possible regression: blocking operation added to the hot path."
    )
    p95_list = max(results["GET /v1/tournaments"])
    assert p95_list < 1000, (
        f"Tournament list p95 (mocked) should be <1000 ms, got {p95_list:.0f} ms."
    )
