"""Plan generation and retrieval — /v1/tournaments/{tid}/plans.

Auth required on all endpoints. Ownership enforced by RLS (one-hop).

Generate flow (POST /v1/tournaments/{tid}/plans/generate):
    1. Load matches for tournament ordered by display_order / scheduled_start.
    2. Load latest weather_snapshot if available.
    3. Call generate_match_scenarios(match_1, match_2) → list[ScenarioPlan].
    4. Call build_plan_envelope(tid, scenarios, weather_flags=…) → Plan.
    5. Persist plan_json (camelCase JSONB via model_dump(by_alias=True)) to plans table.
    6. Return GeneratePlanResponse (HTTP 200 always — see OQ-14 / §G).

Endpoints:
    POST   /v1/tournaments/{tid}/plans/generate   generate and persist plan
    GET    /v1/tournaments/{tid}/plans            list plans
    GET    /v1/tournaments/{tid}/plans/{pid}      fetch single plan
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from playfuel_api.auth import verify_supabase_jwt
from playfuel_api.db import authed_client
from playfuel_api.models.api import GeneratePlanResponse
from playfuel_api.models.db import MatchRow, WeatherSnapshotRow
from playfuel_api.rules.plan import build_plan_envelope
from playfuel_api.rules.scenarios import generate_match_scenarios

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
def generate_plan(
    tid: UUID,
    _user_id: UUID = Depends(verify_supabase_jwt),
    client: Client = Depends(authed_client),
) -> GeneratePlanResponse:
    """Load matches + weather, run rules engine, persist plan_json, return Plan.

    HTTP response is always 200 regardless of gap_status (§G / OQ-14).
    OVERRUN_MESSAGE is embedded in ScenarioPlan.overrun_warning when applicable.
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

    # 2. Load latest weather snapshot (optional — plan proceeds without it).
    weather_flags: dict[str, bool] | None = None
    weather_result = (
        client.table(_WEATHER_TABLE)
        .select("*")
        .eq("tournament_id", str(tid))
        .order("fetched_at", desc=True)
        .limit(1)
        .execute()
    )
    if weather_result.data:
        ws = WeatherSnapshotRow(**weather_result.data[0])
        weather_flags = {
            "flag_hot": ws.flag_hot,
            "flag_very_hot": ws.flag_very_hot,
            "flag_humid": ws.flag_humid,
            "flag_cold": ws.flag_cold,
            "flag_windy": ws.flag_windy,
            "flag_rain_risk": ws.flag_rain_risk,
            "flag_extreme_heat_risk": ws.flag_extreme_heat_risk,
        }

    # 3. Rules engine — pure Python, no LLM (§10 / Phase 6 deferred).
    scenarios = generate_match_scenarios(match, next_match)

    # 4. Assemble plan envelope.
    plan = build_plan_envelope(tid, scenarios, weather_flags=weather_flags)

    # 5. Persist — camelCase JSONB per iOS contract (models/api.py alias_generator=to_camel).
    plan_dict = plan.model_dump(by_alias=True, mode="json")
    client.table(_PLANS_TABLE).insert({
        "id": str(plan.plan_id),
        "tournament_id": str(plan.tournament_id),
        "plan_json": plan_dict,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Plan not found")
    return result.data[0]
