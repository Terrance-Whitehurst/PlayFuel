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
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
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
from playfuel_api.services.places import PlacesUnavailableError, find_nearby_food
from playfuel_api.settings import get_settings
from playfuel_api.weather import get_or_fetch_weather
from playfuel_api.weather.service import WeatherService

router = APIRouter(prefix="/v1/tournaments", tags=["plans"])

logger = logging.getLogger(__name__)

_PLANS_TABLE = "plans"
_MATCHES_TABLE = "matches"
_WEATHER_TABLE = "weather_snapshots"
_LLM_CACHE_TABLE = "llm_explanation_cache"
_LLM_CACHE_TTL_DAYS: int = 7


# ── LLM explanation cache helpers (Opt-B) ───────────────────────────────────────────────────
# Cache key: SHA-256 of the sorted JSON of PlanExplanationInput (PII-stripped).
# SEC-P6-2 invariant: opponent_notes are always empty in exp_input (build_explanation_input
# never populates them), so the cache key is safe to share across requests
# without leaking tactical content.
# RLS: llm_explanation_cache has deny-all policies for authenticated/anon
# (migration 0015). Only service-role API process reads/writes.


def _llm_cache_key(exp_input: "PlanExplanationInput") -> str:  # noqa: F821
    """Compute a deterministic SHA-256 cache key from the PII-stripped plan input.

    opponent_notes are explicitly excluded from the hash (SEC-P6-2 invariant):
      - In production, build_explanation_input() never populates opponent_notes.
      - Explicit exclusion ensures PII cannot leak into the cache key even if
        the production contract is violated.
    """
    import hashlib
    import json

    # Exclude opponent_notes before hashing — PII-safe cache key.
    safe = exp_input.model_dump(exclude={"opponent_notes"})
    return hashlib.sha256(
        json.dumps(safe, default=str, sort_keys=True).encode()
    ).hexdigest()


def _read_llm_cache(
    client: Any,
    exp_input: "PlanExplanationInput",  # noqa: F821
) -> "Optional[PlanExplanation]":  # noqa: F821
    """Try to read a cached PlanExplanation. Returns None on miss, expiry, or error.

    Never raises: errors are logged at DEBUG level and swallowed (cache is
    non-critical augmentation — a miss just falls through to the LLM provider).
    """
    try:
        from playfuel_api.models.api import PlanExplanation

        cache_key = _llm_cache_key(exp_input)
        result = (
            client.table(_LLM_CACHE_TABLE)
            .select("response_json, expires_at")
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        # Parse and check TTL
        expires_str = row["expires_at"]
        if isinstance(expires_str, str):
            if expires_str.endswith("Z"):
                expires_str = expires_str[:-1] + "+00:00"
            expires_at = datetime.fromisoformat(expires_str)
            if datetime.now(tz=timezone.utc) > expires_at:
                return None  # Expired — treat as miss
        return PlanExplanation.model_validate(row["response_json"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM cache read error (non-critical): %s", exc)
        return None


def _write_llm_cache(
    client: Any,
    exp_input: "PlanExplanationInput",  # noqa: F821
    explanation: "PlanExplanation",  # noqa: F821
) -> None:
    """Write a PlanExplanation to the cache. Errors are swallowed (non-critical)."""
    try:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=_LLM_CACHE_TTL_DAYS)
        cache_key = _llm_cache_key(exp_input)
        client.table(_LLM_CACHE_TABLE).upsert(
            {
                "cache_key": cache_key,
                "response_json": explanation.model_dump(mode="json", by_alias=True),
                "model": explanation.model or "template",
                "expires_at": expires_at.isoformat(),
            },
            on_conflict="cache_key",
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM cache write error (non-critical): %s", exc)

# ── Per-user rate limiting (SP-2) ──────────────────────────────────────────────
# In-memory sliding-window counters keyed by JWT sub (user_id as str).
# TODO: migrate to Redis when deploying multiple Fly.io instances — in-memory
# state is per-process and will not share across horizontally-scaled replicas.
_RATE_LIMIT_HOURLY: int = 10   # max plan generations per user per rolling hour
_RATE_LIMIT_DAILY: int = 30    # max plan generations per user per rolling 24 h
_hourly_calls: dict[str, deque[datetime]] = defaultdict(deque)
_daily_calls: dict[str, deque[datetime]] = defaultdict(deque)
_rate_limit_lock = Lock()


def _check_rate_limit(user_id: str) -> tuple[bool, int]:
    """Check and record a plan-generation call against per-user rate limits.

    Evicts expired timestamps before checking, keeping memory bounded.
    Records the call only if it is within both windows.

    Args:
        user_id: JWT subject string (UUID) identifying the calling user.

    Returns:
        (is_allowed, retry_after_seconds): if is_allowed is False, retry_after
        is the number of seconds until the earliest slot opens in the binding
        window.  When is_allowed is True, retry_after is 0.

    Thread-safe via _rate_limit_lock.
    """
    now = datetime.now(tz=timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)

    with _rate_limit_lock:
        hour_q = _hourly_calls[user_id]
        while hour_q and hour_q[0] < one_hour_ago:
            hour_q.popleft()

        day_q = _daily_calls[user_id]
        while day_q and day_q[0] < one_day_ago:
            day_q.popleft()

        if len(hour_q) >= _RATE_LIMIT_HOURLY:
            oldest = hour_q[0]
            retry_after = max(1, int((oldest + timedelta(hours=1) - now).total_seconds()) + 1)
            return False, retry_after

        if len(day_q) >= _RATE_LIMIT_DAILY:
            oldest = day_q[0]
            retry_after = max(1, int((oldest + timedelta(days=1) - now).total_seconds()) + 1)
            return False, retry_after

        # Within both windows — record the call.
        hour_q.append(now)
        day_q.append(now)
        return True, 0


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
    # SP-2: per-user rate limit — checked BEFORE any DB or weather calls.
    # Limits: 10 calls/rolling-hour, 30 calls/rolling-day per JWT sub.
    # Returns 429 + Retry-After header (seconds) when either window is full.
    _allowed, _retry_after = _check_rate_limit(str(_user_id))
    if not _allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Plan generation rate limit exceeded. "
                "Please wait before generating another plan."
            ),
            headers={"Retry-After": str(_retry_after)},
        )

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
    # Phase C-infrastructure: also fetch venue_country (emergency number substitution)
    # and preferred_language (LLM system-prompt selection).
    # ACCOMMODATIONS_V1: also fetch accommodation_lat/lng/kind for departure event.
    tournament_result = (
        client.table("tournaments")
        .select(
            "venue_lat, venue_lng, venue_name, venue_country, preferred_language, "
            "accommodation_lat, accommodation_lng, accommodation_kind"
        )
        .eq("id", str(tid))
        .limit(1)
        .execute()
    )
    venue_lat: Optional[float] = None
    venue_lng: Optional[float] = None
    venue_name: str = ""
    venue_country: Optional[str] = None
    preferred_language: Optional[str] = None
    acc_lat: Optional[float] = None
    acc_lng: Optional[float] = None
    acc_kind: Optional[str] = None
    if tournament_result.data:
        raw_lat = tournament_result.data[0].get("venue_lat")
        raw_lng = tournament_result.data[0].get("venue_lng")
        if raw_lat is not None:
            venue_lat = float(raw_lat)
        if raw_lng is not None:
            venue_lng = float(raw_lng)
        venue_name = tournament_result.data[0].get("venue_name") or ""
        venue_country = tournament_result.data[0].get("venue_country")  # None for legacy rows
        preferred_language = tournament_result.data[0].get("preferred_language")  # None = English default
        # Accommodation fields — migration 0021. None when not set (pre-migration rows are safe).
        raw_acc_lat = tournament_result.data[0].get("accommodation_lat")
        raw_acc_lng = tournament_result.data[0].get("accommodation_lng")
        if raw_acc_lat is not None:
            acc_lat = float(raw_acc_lat)
        if raw_acc_lng is not None:
            acc_lng = float(raw_acc_lng)
        acc_kind = tournament_result.data[0].get("accommodation_kind")  # 'home' | 'hotel' | None

    # 3+5 (concurrent). Weather + places fetches are independent of each other.
    #    Run both concurrently via asyncio.gather to save max(wx_ms, places_ms)
    #    instead of paying wx_ms + places_ms in serial. Opt-A perf improvement.
    #
    #    Weather: async via WeatherService + get_or_fetch_weather.
    #    Places:  sync (httpx.post inside GooglePlacesProvider); run in thread pool
    #             via asyncio.to_thread so it doesn't block the event loop.
    #             httpx.Client (sync) is thread-safe per httpx docs.
    settings = get_settings()
    weather_service = WeatherService(base_url=settings.open_meteo_base_url)
    snapshot: Optional[WeatherSnapshotRow] = None
    target_dt: Optional[datetime] = (
        match_rows[0].scheduled_start if match_rows else None
    )

    import asyncio

    async def _fetch_places_async() -> tuple[list, bool]:
        """Run the sync find_nearby_food in a thread pool so it doesn't block.

        Returns:
            (places, places_unavailable) — places_unavailable is True when the
            Google Places API key is set but the provider failed (401/4xx/5xx).
            The caller sets places_unavailable=True on every Plan in the request.
        """
        if venue_lat is None or venue_lng is None:
            logger.warning(
                "plan generated without venue coords — food_options will be empty "
                "(tournament_id=%s)",
                tid,
            )
            return [], False
        try:
            places = await asyncio.to_thread(
                find_nearby_food,
                venue_lat,
                venue_lng,
                tid,
                client,
            )
            return places, False
        except PlacesUnavailableError as exc:
            logger.warning(
                "plan_gen: places_unavailable — Google Places key set but provider failed: %s"
                " (tournament_id=%s) — setting placesUnavailable=true on plan envelope",
                exc, tid,
            )
            return [], True

    _wx_t0 = time.perf_counter()
    _pl_t0 = time.perf_counter()
    try:
        snapshot, (raw_places, places_unavailable) = await asyncio.gather(
            get_or_fetch_weather(
                client,
                tid,
                lat=venue_lat,
                lng=venue_lng,
                weather_service=weather_service,
                ttl_seconds=settings.weather_cache_ttl_sec,
                target_dt=target_dt,
            ),
            _fetch_places_async(),
        )
    finally:
        await weather_service.aclose()
    _wx_ms = int((time.perf_counter() - _wx_t0) * 1000)
    _pl_ms = int((time.perf_counter() - _pl_t0) * 1000)
    logger.info(
        "plan_gen: weather+places parallel fetch complete "
        "weather_ms=%d places_ms=%d (wall) places_count=%d",
        _wx_ms,
        _pl_ms,
        len(raw_places),
    )

    # B.3: Warn once per request when raw_places=0 despite valid venue coords.
    # This fires when the Places provider silently returned [] — common causes:
    #   401 → GOOGLE_PLACES_API_KEY invalid or expired (check Fly secret rotation)
    #   403 → billing not enabled on the Google Cloud project
    #   429 → quota exceeded
    # When this fires, every match in this request will have bag_fallback_only=True
    # and empty food_options (user sees no nearby food locations).
    if not raw_places and venue_lat is not None and venue_lng is not None:
        logger.warning(
            "plan_gen: raw_places=0 despite valid venue coords (%.4f, %.4f) — "
            "Places provider returned empty. Check GOOGLE_PLACES_API_KEY validity, "
            "billing enabled, and quota at console.cloud.google.com. "
            "Rotate key: flyctl secrets set GOOGLE_PLACES_API_KEY=<new-key> --app playfuel-api",
            venue_lat, venue_lng,
        )

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
        # Phase B: derive temp_c and wind_kmh for new rows; compute from legacy
        # imperial for old pre-Phase-B rows (snapshot.temp_c is None on those).
        snap_temp_c: float = (
            snapshot.temp_c
            if snapshot.temp_c is not None
            else (snapshot.temp_f - 32.0) * 5.0 / 9.0
        )
        snap_wind_kmh: Optional[float] = (
            snapshot.wind_kmh
            if snapshot.wind_kmh is not None
            else (snapshot.wind_mph * 1.609 if snapshot.wind_mph is not None else None)
        )
        weather_block = WeatherBlock(
            temp_f=snapshot.temp_f,
            temp_c=snap_temp_c,
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
            wind_kmh=snap_wind_kmh,
            precip_prob=snapshot.precipitation_probability,
        )

    # 6. Provider is the same for all plans in this request.
    # (Food/places result already in raw_places from the parallel gather above.)
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
        # ACCOMMODATIONS_V1: pass accommodation + venue coords so departure event can be emitted.
        # weather_flags_dict passed for heat-addendum threshold check.
        # When acc_lat is None, estimate_drive_minutes() returns 0 — byte-for-byte regression-safe.
        timeline = build_timeline(
            [match],
            scenarios,
            accommodation_lat=acc_lat,
            accommodation_lng=acc_lng,
            venue_lat=venue_lat,
            venue_lng=venue_lng,
            accommodation_kind=acc_kind,
            weather_flags=weather_flags,
        )

        # 9. Food options (same raw_places; bucket selection per this match's scenarios).
        food_buckets: list[str] = sorted({
            s.food_strategy.bucket.value
            for s in scenarios
            if s.food_strategy is not None
        })
        # §G.5 no_next_match last-match fallback: all scenarios have food_strategy=None
        # (no gap timing → no pickup scheduling), but venue food OPTIONS from Google
        # Places are gap-independent.  When food_buckets is empty AND raw_places is
        # non-empty, fall back to quick_pickup so restaurant recommendations still
        # surface on the last match of the day.  The food TIMING text in each
        # ScenarioPlan remains None (semantically correct — no next-match pressure);
        # only the plan-level venue list is populated via the permissive fallback.
        if not food_buckets and raw_places:
            food_buckets = ["quick_pickup"]
        food_options, bag_fallback_only = assemble_food_options(
            raw_places,
            food_buckets,
            venue_lat=venue_lat,
            venue_lng=venue_lng,
        )

        # B.2: Per-match diagnostic log — surfaces food pipeline state for each match.
        # Log: match ID, derived food buckets, number of raw Places results,
        # number of food options assembled, and whether bag fallback fired.
        # When raw_places=0 on every match, the B.3 warning above explains why.
        logger.info(
            "plan_gen: match=%s buckets=%s raw_places=%d food_options=%d bag_fallback=%s",
            str(match.id), food_buckets, len(raw_places), len(food_options), bag_fallback_only,
        )

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
            # feat/match-card-time: ISO 8601 UTC so iOS MatchChip shows device-local time.
            # strftime("%Y-%m-%dT%H:%M:%SZ") is consistent with _fmt_time() in scenarios.py.
            scheduled_start=match.scheduled_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            # match-done-state-cards spec §C: forward parent-toggle done state
            is_done=match.is_done,
            # OQ-FOOD-EMPTY-1: signal iOS empty-state when Google Places key is set
            # but the provider failed (401/4xx/5xx/timeout with no stale cache).
            # False when MockPlacesProvider is active (dev/test) or when Places
            # returned results normally.
            places_unavailable=places_unavailable,
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
        #     Opt-B: check llm_explanation_cache first; on hit skip API call entirely.
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
            _llm_t0 = time.perf_counter()
            cached_explanation = _read_llm_cache(client, exp_input)
            if cached_explanation is not None:
                plan.llm_summary = cached_explanation
                logger.info(
                    "plan_gen: llm cache HIT match=%s provider=%s",
                    str(match.id),
                    cached_explanation.provider,
                )
            else:
                raw_explanation = llm_provider.explain_plan(exp_input)
                explanation = sanitize_or_fallback(raw_explanation, exp_input)
                plan.llm_summary = explanation
                _llm_ms = int((time.perf_counter() - _llm_t0) * 1000)
                logger.info(
                    "plan_gen: llm explain complete match=%s provider=%s duration_ms=%d",
                    str(match.id),
                    explanation.provider if explanation else None,
                    _llm_ms,
                )
                # Write to cache (best-effort; errors swallowed).
                if explanation is not None:
                    _write_llm_cache(client, exp_input, explanation)
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
