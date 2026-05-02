"""Plan generation and retrieval — /v1/tournaments/{tid}/plans.

Auth required on all endpoints. Ownership enforced by RLS (one-hop).

Generate flow (POST /v1/tournaments/{tid}/plans/generate):
    1. Load matches for tournament ordered by display_order / scheduled_start.
       0 matches → 200 with empty {singlesPlans: [], doublesPlans: []} (not 404).
    2. Load tournament for venue coords (lat/lng).
    3. Fetch or read weather from cache (async, Open-Meteo; None if no coords).
    4. For EACH match: run scenarios → timeline → food → plan envelope → LLM → persist.
    5. Derive NextAction deterministically via rules/next_action.py.
    6. Persist one plan row per (match_id, match_type) via UPSERT on
       conflict(match_id, match_type) — idempotent re-generate (OQ-IA-9 fix).
    7. Return GeneratePlanResponse {singlesPlans, doublesPlans} arrays.

NUTRITION_FIRST_IA_V1.md §E: one Plan per match (was one per match-type group).

Endpoints:
    POST   /v1/tournaments/{tid}/plans/generate   generate and persist plan
    GET    /v1/tournaments/{tid}/plans            list plans
    GET    /v1/tournaments/{tid}/plans/{pid}      fetch single plan
"""
from __future__ import annotations

import logging
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
from playfuel_api.rules.next_action import derive_next_action
from playfuel_api.rules.plan import build_plan_envelope, build_timeline
from playfuel_api.rules.scenarios import generate_match_scenarios
from playfuel_api.services.llm import build_explanation_input, get_llm_provider
from playfuel_api.services.llm_safety import sanitize_or_fallback
from playfuel_api.services.places import find_nearby_food
from playfuel_api.settings import get_settings
from playfuel_api.weather import get_or_fetch_weather
from playfuel_api.weather.service import WeatherService

router = APIRouter(prefix="/v1/tournaments", tags=["plans"])

logger = logging.getLogger(__name__)

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
    """Load matches + weather, run rules engine, persist plan_json, return envelope.

    NUTRITION_FIRST_IA_V1 §E: Generates one Plan per match (not per match-type group).
    Returns GeneratePlanResponse {singlesPlans: [Plan], doublesPlans: [Plan]}.
    Either array may be empty when no matches of that type exist.
    HTTP response is always 200 regardless of gap_status (§G / OQ-14).
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
        # Return empty envelope — 0 matches is valid (parent hasn't added any yet).
        # NUTRITION_FIRST_IA_V1 §H.2 / hotfix: was erroneously 404.
        return GeneratePlanResponse(singles_plans=[], doubles_plans=[])

    match_rows = [MatchRow(**m) for m in matches_result.data]

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
    #    WX-G1: pass target_dt so the cache layer dispatches to fetch_forecast_at()
    #    when the first match is scheduled > 3h in the future.
    settings = get_settings()
    weather_service = WeatherService(base_url=settings.open_meteo_base_url)
    snapshot: Optional[WeatherSnapshotRow] = None
    target_dt: Optional[datetime] = (
        match_rows[0].scheduled_start if match_rows else None
    )
    try:
        snapshot = await get_or_fetch_weather(
            client,
            tid,
            lat=venue_lat,
            lng=venue_lng,
            weather_service=weather_service,
            ttl_seconds=settings.weather_cache_ttl_sec,
            target_dt=target_dt,
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
            # WX-G2: surface wind/precip from snapshot so iOS shows real values.
            wind_mph=snapshot.wind_mph,
            precip_prob=snapshot.precipitation_probability,
        )

    # 5. Phase 5: food / places lookup (non-critical; shared across all matches — same venue).
    #    tournament_id + db_client passed for cache read-through (migration 0012).
    #    When venue coords are absent, skip lookup entirely — bag fallback fires downstream.
    raw_places = find_nearby_food(
        venue_lat,
        venue_lng,
        tournament_id=tid,
        db_client=client,
    ) if (venue_lat is not None and venue_lng is not None) else []

    # 6. Provider is the same for all plans in this request.
    llm_provider = get_llm_provider()
    now_utc = datetime.now(tz=timezone.utc)

    singles_plans: list["Plan"] = []  # noqa: F821
    doubles_plans: list["Plan"] = []  # noqa: F821

    # NUTRITION_FIRST_IA_V1 §E: one Plan per match in the tournament.
    # match_rows is already ordered by display_order ASC, scheduled_start ASC.
    for match_idx, match in enumerate(match_rows):
        match_type_key: str = (match.format or "singles").lower()
        if match_type_key not in ("singles", "doubles"):
            match_type_key = "singles"

        # Doubles format (only meaningful for doubles matches).
        doubles_format_val: Optional[str] = None
        if match_type_key == "doubles":
            doubles_format_val = match.doubles_format

        # The "next match" for scenario gap computation: the globally next match
        # in the ordered list, regardless of type.
        next_match: Optional[MatchRow] = (
            match_rows[match_idx + 1] if match_idx + 1 < len(match_rows) else None
        )

        # 7. Rules engine — generate scenarios for this match.
        scenarios = generate_match_scenarios(
            match,
            next_match,
            match_type=match_type_key,
            doubles_format=doubles_format_val,
        )

        # 8. Build timeline (single-match context; partnerCoordination fires for doubles).
        timeline = build_timeline([match], scenarios)

        # 9. Food options (same raw_places; bucket selection per this match's scenarios).
        food_buckets: list[str] = sorted({
            s.food_strategy.bucket.value
            for s in scenarios
            if s.food_strategy is not None
        })
        food_options, bag_fallback_only = assemble_food_options(raw_places, food_buckets)

        # 10. Assemble plan envelope.
        plan = build_plan_envelope(
            tid,
            scenarios,
            weather_flags=weather_flags,
            weather_block=weather_block,
            timeline=timeline,
            food_options=food_options,
            bag_fallback_only=bag_fallback_only,
            match_type=match_type_key,
            match_id=match.id,
        )

        # 11. Derive NextAction deterministically — rules engine, never LLM.
        extreme_heat = (
            weather_flags.get("flag_extreme_heat_risk", False)
            if weather_flags else False
        )
        try:
            plan.next_action = derive_next_action(
                plan.timeline,
                now=now_utc,
                extreme_heat_risk=extreme_heat,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "derive_next_action failed for match %s; nextAction will be None.",
                str(match.id),
                exc_info=True,
            )

        # 12. LLM explanation layer — TemplateProvider by default.
        #     Non-critical: sanitize_or_fallback() catches all provider errors.
        try:
            exp_input = build_explanation_input(
                plan=plan,
                match=match,
                next_match=next_match,
                snapshot=snapshot,
                food_options_list=food_options,
                venue_name=venue_name,
            )
            # SEC-P6-2: opponent_notes are NOT attached to exp_input.
            # Notes are tactical text that must not be serialised to a third-party LLM.
            # exp_input.opponent_notes stays empty (PlanExplanationInput default: []).
            raw_explanation = llm_provider.explain_plan(exp_input)
            explanation = sanitize_or_fallback(raw_explanation, exp_input)
            plan.llm_summary = explanation
        except Exception:  # noqa: BLE001
            logger.warning(
                "LLM explanation failed for match %s (%s); llmSummary will be null.",
                str(match.id),
                match_type_key,
                exc_info=True,
            )

        # 13. Persist — camelCase JSONB per iOS contract.
        #     OQ-IA-9 fix: upsert (not insert) so re-generate is idempotent.
        #     Conflict target matches migration 0008's partial unique index:
        #       plans_match_id_match_type_uq ON (match_id, match_type)
        #       WHERE match_id IS NOT NULL
        plan_dict = plan.model_dump(by_alias=True, mode="json")
        llm_summary_dict = (
            plan.llm_summary.model_dump(by_alias=True, mode="json")
            if plan.llm_summary is not None else None
        )
        client.table(_PLANS_TABLE).upsert(
            {
                "id": str(plan.plan_id),
                "tournament_id": str(plan.tournament_id),
                "match_id": str(match.id),
                "plan_json": plan_dict,
                "llm_summary": llm_summary_dict,
                "rules_constants_version": plan.rules_constants_version,
                "warnings": plan.warnings,
                "schedule_confidence": plan.schedule_confidence.value,
                "match_type": match_type_key,
            },
            on_conflict="match_id,match_type",
        ).execute()

        if match_type_key == "singles":
            singles_plans.append(plan)
        else:
            doubles_plans.append(plan)

    # Plans are already in display_order / scheduled_start ASC order
    # (match_rows was fetched that way).
    return GeneratePlanResponse(singles_plans=singles_plans, doubles_plans=doubles_plans)


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
