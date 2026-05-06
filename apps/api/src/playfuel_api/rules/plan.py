"""Plan envelope assembly, schedule-confidence derivation, and timeline construction.

build_plan_envelope() wraps a list[ScenarioPlan] into the top-level Plan
object, setting schedule_confidence, warnings, and heat_emergency_text.

derive_schedule_confidence() implements the rule from db/supabase/README:
    low    — any scenario.gap_status in {overrun, no_next_match}
    medium — any scenario.gap_status == tight  (only if no low-priority statuses)
    high   — otherwise (all scenarios are ok)

Heat emergency text (§E.2 / §H.2):
    Attached to plan when weather_flags['flag_extreme_heat_risk'] is True.
    HEAT_EMERGENCY_TEXT is imported from hard_coded_strings — never re-typed here.
    v1.1 wording (OQ-11 revised 2026-04-27); pending legal sign-off (OQ-06).

build_timeline() constructs a chronological list[TimelineEventOut] from
match rows + scenarios. Deterministic per call; UUIDs are fresh each request
(clients must not persist timeline event IDs across plan regenerations).

plan_json persistence:
    Callers must call plan.model_dump(by_alias=True, mode='json') before INSERT
    so the stored JSONB uses camelCase keys consistent with iOS contract.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from playfuel_api.models.api import FoodOption, Plan, ScenarioPlan, TimelineEventOut, WeatherBlock
from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import GapStatus, ScheduleConfidence, TimelineEventKind
from playfuel_api.rules.constants import ARRIVE_SNACK_MIN, RULES_CONSTANTS_VERSION
from playfuel_api.rules.distance import estimate_drive_minutes
from playfuel_api.rules.duration_format import friendly_duration
from playfuel_api.rules.hard_coded_strings import (
    DEPARTURE_DETAIL_TEMPLATE,
    DEPARTURE_HEAT_ADDENDUM,
    DEPARTURE_TITLE_HOME,
    DEPARTURE_TITLE_HOTEL,
    HEAT_EMERGENCY_TEXT,
    LONG_DRIVE_WARNING_TEMPLATE,
    heat_emergency_text as _get_heat_emergency_text,
)

# Optional import to avoid circular at module level — imported inline inside function
_next_action_mod = None


def derive_schedule_confidence(scenarios: list[ScenarioPlan]) -> ScheduleConfidence:
    """Derive schedule_confidence from gap_status values across all scenarios.

    Priority is checked low → medium → high (first match wins).

    Rule (db/supabase/README):
        low    if any gap_status in {overrun, no_next_match}
        medium if any gap_status == tight
        high   otherwise
    """
    statuses = {s.gap_status for s in scenarios}
    if statuses & {GapStatus.overrun, GapStatus.no_next_match}:
        return ScheduleConfidence.low
    if GapStatus.tight in statuses:
        return ScheduleConfidence.medium
    return ScheduleConfidence.high


def build_timeline(
    matches: list[MatchRow],
    scenarios: list[ScenarioPlan],
    *,
    accommodation_lat: Optional[float] = None,
    accommodation_lng: Optional[float] = None,
    venue_lat: Optional[float] = None,
    venue_lng: Optional[float] = None,
    accommodation_kind: Optional[str] = None,  # 'home' | 'hotel' | None
    weather_flags: Optional[dict[str, bool]] = None,
) -> list[TimelineEventOut]:
    """Build a chronological timeline of events for the plan.

    Deterministic per-request: same input → same shape, but UUIDs are
    fresh per call (clients should not persist timeline event IDs across
    plan regenerations).

    v1 emits one `match` event per match (using its scheduled_start) and
    one `matchEnd` event per match using the *normal* scenario's estimated
    end. Future versions will splice meal/warmUp/wakeUp events.

    v1.1 (doubles-spec): emits a `partnerCoordination` event at T−60m before
    the first doubles match when any match in the list has format == 'doubles'.
    See DOUBLES_SPEC_V1.md §C.1.

    v1.2 (accommodations): emits a `departure` event at
    match_start - ARRIVE_SNACK_MIN - drive_minutes for the first match when
    accommodation coords are set. See ACCOMMODATIONS_V1.md §E.2.

    Args:
        matches:           Match rows for the plan type (singles or doubles group),
                           ordered by display_order.
        scenarios:         Output of generate_match_scenarios() for the first match.
        accommodation_lat: Latitude of accommodation; None = venue-local (no departure event).
        accommodation_lng: Longitude of accommodation; None = venue-local.
        venue_lat:         Latitude of tournament venue (for haversine drive-time).
        venue_lng:         Longitude of tournament venue.
        accommodation_kind: 'home' | 'hotel' | None. None defaults to 'home' copy.
        weather_flags:     Flags from classify_weather(); used for heat-addendum threshold.

    Returns:
        list[TimelineEventOut] — ordered chronologically by time.

    REGRESSION INVARIANT: when accommodation_lat is None, estimate_drive_minutes() returns 0
    and no departure event is emitted. Output is byte-for-byte identical to pre-feature
    behavior. All new params are keyword-only with Optional defaults (backward-compatible).
    """
    events: list[TimelineEventOut] = []

    # Pick the "normal" scenario as the canonical timing source for matchEnd.
    normal = next(
        (s for s in scenarios if s.scenario.value == "normal"), None
    )

    # Doubles-spec §C.1: emit partnerCoordination at T−60m for doubles matches.
    is_doubles = any(m.format == "doubles" for m in matches)

    # Accommodations v1.2: emit departure event for first match when accommodation set.
    # drive_minutes == 0 when accommodation_lat is None (sentinel) or same location.
    # In both cases the block below is skipped — regression-safe.
    _drive_minutes: int = 0
    if venue_lat is not None and venue_lng is not None:
        _drive_minutes = estimate_drive_minutes(
            accommodation_lat, accommodation_lng, venue_lat, venue_lng
        )

    if _drive_minutes > 0 and matches:
        first_match = matches[0]
        arrive_by_dt = first_match.scheduled_start - timedelta(minutes=ARRIVE_SNACK_MIN)
        departure_dt = arrive_by_dt - timedelta(minutes=_drive_minutes)

        # Title: hotel vs home (None defaults to home, per §G T-11)
        title = (
            DEPARTURE_TITLE_HOTEL
            if accommodation_kind == "hotel"
            else DEPARTURE_TITLE_HOME
        )

        # Detail: base template (DR_37: no wall-clock or ISO datetime in detail strings)
        detail = DEPARTURE_DETAIL_TEMPLATE.format(
            drive_minutes=_drive_minutes,
        )

        # Long-drive warning appended when drive >= 90 min (OQ-ACC-5 resolution)
        if _drive_minutes >= 90:
            detail += LONG_DRIVE_WARNING_TEMPLATE.format(drive_minutes=_drive_minutes)

        # Heat addendum when drive >= 45 min AND extreme heat flag set
        if _drive_minutes >= 45 and weather_flags and weather_flags.get("flag_extreme_heat_risk"):
            detail += DEPARTURE_HEAT_ADDENDUM

        events.append(
            TimelineEventOut(
                id=str(uuid.uuid4()),
                time=departure_dt.isoformat(),
                title=title,
                detail=detail,
                kind=TimelineEventKind.departure,
            )
        )

    for idx, match in enumerate(matches, start=1):
        # Doubles only: partner coordination reminder at T−60m (first match only).
        if is_doubles and idx == 1:
            partner_time = match.scheduled_start - timedelta(minutes=60)
            events.append(
                TimelineEventOut(
                    id=str(uuid.uuid4()),
                    time=partner_time.isoformat(),
                    title="Confirm with your doubles partner",
                    detail=(
                        "Agree on warm-up time, court arrival, and pre-match strategy "
                        "with your partner."
                    ),
                    kind=TimelineEventKind.partnerCoordination,
                )
            )

        events.append(
            TimelineEventOut(
                id=str(uuid.uuid4()),
                time=match.scheduled_start.isoformat(),
                title=f"Match {idx}",
                detail="Scheduled start",
                kind=TimelineEventKind.match,
            )
        )

        # matchEnd event using normal duration scenario (first match only for v1).
        if idx == 1 and normal is not None:
            end_dt = match.scheduled_start + timedelta(minutes=normal.duration_min)
            events.append(
                TimelineEventOut(
                    id=str(uuid.uuid4()),
                    time=end_dt.isoformat(),
                    title=f"Match {idx} estimated end",
                    detail=(
                        f"Based on normal duration ({friendly_duration(normal.duration_min)}). "
                        "Actual time may vary."
                    ),
                    kind=TimelineEventKind.matchEnd,
                )
            )

    # Sort chronologically — partnerCoordination fires before match, so this ensures
    # deterministic ordering even if matches are passed in display_order order.
    return sorted(events, key=lambda e: e.time)


def build_plan_envelope(
    tournament_id: uuid.UUID,
    scenarios: list[ScenarioPlan],
    *,
    weather_flags: Optional[dict[str, bool]] = None,
    weather_block: Optional[WeatherBlock] = None,
    timeline: Optional[list[TimelineEventOut]] = None,
    food_options: Optional[list[FoodOption]] = None,
    bag_fallback_only: bool = False,
    match_type: str = "singles",
    match_id: Optional[uuid.UUID] = None,
    scheduled_start: Optional[str] = None,
    is_done: bool = False,               # match-done-state-cards spec §C
    venue_country: Optional[str] = None, # Phase C-infrastructure: country-specific emergency number
    places_unavailable: bool = False,    # True when Google Places API key is set but provider failed
) -> Plan:
    """Assemble the top-level Plan envelope from engine output.

    Args:
        tournament_id:    UUID of the tournament being planned.
        scenarios:        Output of generate_match_scenarios() — all three ScenarioKinds.
        weather_flags:    Optional output of classify_weather(); triggers HEAT_EMERGENCY_TEXT
                          when flag_extreme_heat_risk is True (§E.2).
        weather_block:    Optional WeatherBlock for plan response (Phase 4 OQ-API-2).
        timeline:         Optional list[TimelineEventOut] for plan response (Phase 4 OQ-API-2).
        food_options:     Optional list[FoodOption] from Phase 5 Places integration.
        bag_fallback_only: True when all buckets are bag_only (Phase 5).
        scheduled_start:  ISO 8601 UTC string from match.scheduled_start (feat/match-card-time).
                          Forwarded to Plan so iOS MatchChip can render device-local clock time.

    Returns:
        Plan — ready for HTTP response. Persist JSONB via
        plan.model_dump(by_alias=True, mode='json') to match camelCase iOS contract.
    """
    confidence = derive_schedule_confidence(scenarios)

    # §G.4: aggregate top-level warnings from scenario children (de-duplicated, ordered).
    seen: set[str] = set()
    plan_warnings: list[str] = []
    for scenario in scenarios:
        for w in scenario.warnings:
            if w not in seen:
                plan_warnings.append(w)
                seen.add(w)

    # §E.2 / §H.2: heat emergency text — attached when extreme_heat_risk is True.
    # v1.1 wording; pending legal sign-off (OQ-06 / OQ-11).
    # Phase C-infrastructure: uses venue_country to select the country-appropriate
    # emergency number. heat_emergency_text(None) == HEAT_EMERGENCY_TEXT byte-identical.
    heat_text: Optional[str] = None
    if weather_flags and weather_flags.get("flag_extreme_heat_risk"):
        heat_text = _get_heat_emergency_text(venue_country)

    return Plan(
        plan_id=uuid.uuid4(),
        tournament_id=tournament_id,
        generated_at=datetime.now(tz=timezone.utc),
        rules_constants_version=RULES_CONSTANTS_VERSION,
        schedule_confidence=confidence,
        heat_emergency_text=heat_text,
        warnings=plan_warnings,
        scenario_plans=scenarios,
        weather=weather_block,
        timeline=timeline or [],
        food_options=food_options,
        bag_fallback_only=bag_fallback_only,
        match_type=match_type,
        match_id=match_id,
        scheduled_start=scheduled_start,
        is_done=is_done,               # match-done-state-cards spec §C
        places_unavailable=places_unavailable,  # OQ-FOOD-EMPTY-1: signal iOS empty-state
    )
