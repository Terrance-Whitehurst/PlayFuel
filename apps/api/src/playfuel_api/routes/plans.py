"""Plan generation and retrieval — /v1/tournaments/{tid}/plans.

Auth required on all endpoints. Ownership enforced by RLS (one-hop).

Generate flow (POST /v1/tournaments/{tid}/plans/generate):
    1. Load matches for tournament ordered by display_order / scheduled_start.
    2. Load tournament for venue coords (lat/lng).
    3. Fetch or read weather from cache (async, Open-Meteo; None if no coords).
    4. Call generate_match_scenarios(match_1, match_2) → list[ScenarioPlan].
    5. Build timeline from matches + scenarios.
    6. Call build_plan_envelope(tid, scenarios, weather_block, timeline) → Plan.
    7. Persist plan_json (camelCase JSONB via model_dump(by_alias=True)) to plans table.
    8. Return GeneratePlanResponse (HTTP 200 always — see OQ-14 / §G).

Endpoints:
    POST   /v1/tournaments/{tid}/plans/generate   generate and persist plan
    GET    /v1/tournaments/{tid}/plans            list plans
    GET    /v1/tournaments/{tid}/plans/{pid}      fetch single plan
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client
from playfuel_api.models.api import GeneratePlanResponse, WeatherBlock
from playfuel_api.models.db import MatchRow, WeatherSnapshotRow
from playfuel_api.rules.food import assemble_food_options
from playfuel_api.rules.plan import build_plan_envelope, build_timeline
from playfuel_api.rules.scenarios import generate_match_scenarios
from playfuel_api.services.llm import build_explanation_input, get_llm_provider
from playfuel_api.services.llm_safety import sanitize_or_fallback
from playfuel_api.services.places import find_nearby_food
from playfuel_api.settings import get_settings
from playfuel_api.weather import get_or_fetch_weather
from playfuel_api.weather.service import WeatherService

router = APIRouter(prefix="/v1/tournaments", tags=["plans"])

_PLANS_TABLE = "plans"
_MATCHES_TABLE = "matches"
_WEATHER_TABLE = "weather_snapshots"


@router.post(
    "/{tid}/plans/generate",
    summary="Generate tournament day plan",
    response_model=GeneratePlanResponse,
    response_model_by_alias=True,
)
async def generate_plan(
    tid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> GeneratePlanResponse:
    """Load matches + weather, run rules engine, persist plan_json, return Plan.

    HTTP response is always 200 regardless of gap_status (§G / OQ-14).
    OVERRUN_MESSAGE is embedded in ScenarioPlan.overrun_warning when applicable.
    weather and timeline blocks added in Phase 4 (Task #7 / OQ-API-2).
    """
    # 1. Load matches ordered by display_order, then scheduled_start.
    matches_result = (
        client.table(_MATCHES_TABLE)
        .select("*")
        .eq("tournament_id", str(tid))
        .order("display_order")
        .order("scheduled_start")
        .execute()
    )
    if not matches_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matches found for tournament — add matches before generating a plan",
        )

    match_rows = [MatchRow(**m) for m in matches_result.data]
    match = match_rows[0]
    next_match = match_rows[1] if len(match_rows) > 1 else None

    # 2. Load tournament venue coords + name for weather fetch and LLM input.
    tournament_result = (
        client.table("tournaments")
        .select("venue_lat, venue_lng, venue_name")
        .eq("id", str(tid))
        .limit(1)
        .execute()
    )
    venue_lat: Optional[float] = None
    venue_lng: Optional[float] = None
    venue_name: str = ""
    if tournament_result.data:
        raw_lat = tournament_result.data[0].get("venue_lat")
        raw_lng = tournament_result.data[0].get("venue_lng")
        if raw_lat is not None:
            venue_lat = float(raw_lat)
        if raw_lng is not None:
            venue_lng = float(raw_lng)
        venue_name = tournament_result.data[0].get("venue_name") or ""

    # 3. Read-through weather cache (returns None if no coords or fetch fails).
    #    WeatherService is created per-request; aclose() in finally ensures cleanup.
    settings = get_settings()
    weather_service = WeatherService(base_url=settings.open_meteo_base_url)
    snapshot: Optional[WeatherSnapshotRow] = None
    try:
        snapshot = await get_or_fetch_weather(
            client,
            tid,
            lat=venue_lat,
            lng=venue_lng,
            weather_service=weather_service,
            ttl_seconds=settings.weather_cache_ttl_sec,
        )
    finally:
        await weather_service.aclose()

    # 4. Build weather_flags dict and WeatherBlock for plan response.
    weather_flags: Optional[dict[str, bool]] = None
    weather_block: Optional[WeatherBlock] = None
    if snapshot is not None:
        weather_flags = {
            "flag_hot": snapshot.flag_hot,
            "flag_very_hot": snapshot.flag_very_hot,
            "flag_humid": snapshot.flag_humid,
            "flag_cold": snapshot.flag_cold,
            "flag_windy": snapshot.flag_windy,
            "flag_rain_risk": snapshot.flag_rain_risk,
            "flag_extreme_heat_risk": snapshot.flag_extreme_heat_risk,
        }
        # Compute is_stale: snapshot is stale if its fetched_at is older than TTL.
        age_sec = (
            datetime.now(tz=timezone.utc) - snapshot.fetched_at
        ).total_seconds()
        is_stale = age_sec > settings.weather_cache_ttl_sec
        weather_block = WeatherBlock(
            temp_f=snapshot.temp_f,
            humidity_pct=snapshot.humidity_pct,
            condition=snapshot.condition,
            flag_hot=snapshot.flag_hot,
            flag_very_hot=snapshot.flag_very_hot,
            flag_humid=snapshot.flag_humid,
            flag_cold=snapshot.flag_cold,
            flag_windy=snapshot.flag_windy,
            flag_rain_risk=snapshot.flag_rain_risk,
            flag_extreme_heat_risk=snapshot.flag_extreme_heat_risk,
            is_stale=is_stale,
            fetched_at=snapshot.fetched_at,
            provider=snapshot.provider,
        )

    # 5. Rules engine — pure Python, no LLM (§10 / Phase 6 deferred).
    scenarios = generate_match_scenarios(match, next_match)

    # 6. Build timeline from all match rows + scenarios.
    timeline = build_timeline(match_rows, scenarios)

    # 7. Phase 5: food / places lookup (non-critical — never raises).
    raw_places = find_nearby_food(
        venue_lat if venue_lat is not None else 0.0,
        venue_lng if venue_lng is not None else 0.0,
    ) if (venue_lat is not None and venue_lng is not None) else []

    # Collect unique food buckets from all scenarios.
    food_buckets: list[str] = sorted({
        s.food_strategy.bucket.value
        for s in scenarios
        if s.food_strategy is not None
    })
    food_options, bag_fallback_only = assemble_food_options(raw_places, food_buckets)

    # 8. Assemble plan envelope (Phase 4: weather_block + timeline; Phase 5: food).
    plan = build_plan_envelope(
        tid,
        scenarios,
        weather_flags=weather_flags,
        weather_block=weather_block,
        timeline=timeline,
        food_options=food_options,
        bag_fallback_only=bag_fallback_only,
    )

    # 9. LLM explanation layer (Phase 6 / Task #9) — TemplateProvider by default.
    #    Never raises: sanitize_or_fallback() falls back to TemplateProvider on any violation.
    try:
        exp_input = build_explanation_input(
            plan=plan,
            match=match,
            next_match=next_match,
            snapshot=snapshot,
            food_options_list=food_options,
            venue_name=venue_name,
        )
        raw_explanation = get_llm_provider().explain_plan(exp_input)
        explanation = sanitize_or_fallback(raw_explanation, exp_input)
        plan.llm_summary = explanation
    except Exception:  # noqa: BLE001
        # LLM is non-critical — never fail the plan on explanation errors.
        import logging
        logging.getLogger(__name__).warning(
            "LLM explanation failed; plan will be returned without llmSummary.",
            exc_info=True,
        )

    # 10. Persist — camelCase JSONB per iOS contract (models/api.py alias_generator=to_camel).
    plan_dict = plan.model_dump(by_alias=True, mode="json")
    llm_summary_dict = (
        plan.llm_summary.model_dump(by_alias=True, mode="json")
        if plan.llm_summary is not None else None
    )
    client.table(_PLANS_TABLE).insert({
        "id": str(plan.plan_id),
        "tournament_id": str(plan.tournament_id),
        "plan_json": plan_dict,
        "llm_summary": llm_summary_dict,
        "rules_constants_version": plan.rules_constants_version,
        "warnings": plan.warnings,
        "schedule_confidence": plan.schedule_confidence.value,
    }).execute()

    return GeneratePlanResponse(plan=plan)


@router.get("/{tid}/plans", summary="List plans")
def list_plans(
    tid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> list[dict[str, Any]]:
    """List all plans for a tournament (RLS-filtered, newest first)."""
    result = (
        client.table(_PLANS_TABLE)
        .select("*")
        .eq("tournament_id", str(tid))
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.get("/{tid}/plans/{pid}", summary="Get plan")
def get_plan(
    tid: UUID,
    pid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> dict[str, Any]:
    """Fetch a single plan by ID (RLS enforces one-hop ownership)."""
    result = (
        client.table(_PLANS_TABLE)
        .select("*")
        .eq("id", str(pid))
        .eq("tournament_id", str(tid))
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    return result.data[0]
