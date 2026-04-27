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

from playfuel_api.models.api import Plan, ScenarioPlan, TimelineEventOut, WeatherBlock
from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import GapStatus, ScheduleConfidence, TimelineEventKind
from playfuel_api.rules.constants import RULES_CONSTANTS_VERSION
from playfuel_api.rules.hard_coded_strings import HEAT_EMERGENCY_TEXT


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


def _fmt_time(dt: datetime) -> str:
    """Format a datetime as 'H:MM AM/PM' with no leading zero on the hour."""
    h = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{h}:{dt.minute:02d} {ampm}"


def build_timeline(
    matches: list[MatchRow],
    scenarios: list[ScenarioPlan],
) -> list[TimelineEventOut]:
    """Build a chronological timeline of events for the plan.

    Deterministic per-request: same input → same shape, but UUIDs are
    fresh per call (clients should not persist timeline event IDs across
    plan regenerations).

    v1 emits one `match` event per match (using its scheduled_start) and
    one `matchEnd` event per match using the *normal* scenario's estimated
    end. Future versions will splice meal/warmUp/wakeUp events.

    Args:
        matches:   All match rows for the tournament, ordered by display_order.
        scenarios: Output of generate_match_scenarios() for the first match.

    Returns:
        list[TimelineEventOut] — ordered chronologically by time.
    """
    events: list[TimelineEventOut] = []

    # Pick the "normal" scenario as the canonical timing source for matchEnd.
    normal = next(
        (s for s in scenarios if s.scenario.value == "normal"), None
    )

    for idx, match in enumerate(matches, start=1):
        events.append(
            TimelineEventOut(
                id=str(uuid.uuid4()),
                time=match.scheduled_start.isoformat(),
                title=f"Match {idx}",
                detail=f"Scheduled start ({_fmt_time(match.scheduled_start)})",
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
                        f"Based on normal duration ({normal.duration_min} min). "
                        "Actual time may vary."
                    ),
                    kind=TimelineEventKind.matchEnd,
                )
            )

    return events


def build_plan_envelope(
    tournament_id: uuid.UUID,
    scenarios: list[ScenarioPlan],
    *,
    weather_flags: Optional[dict[str, bool]] = None,
    weather_block: Optional[WeatherBlock] = None,
    timeline: Optional[list[TimelineEventOut]] = None,
) -> Plan:
    """Assemble the top-level Plan envelope from engine output.

    Args:
        tournament_id: UUID of the tournament being planned.
        scenarios:     Output of generate_match_scenarios() — all three ScenarioKinds.
        weather_flags: Optional output of classify_weather(); triggers HEAT_EMERGENCY_TEXT
                       when flag_extreme_heat_risk is True (§E.2).
        weather_block: Optional WeatherBlock for plan response (Phase 4 OQ-API-2).
        timeline:      Optional list[TimelineEventOut] for plan response (Phase 4 OQ-API-2).

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
    # v1.1 HEAT_EMERGENCY_TEXT — pending legal sign-off (OQ-06 / OQ-11).
    heat_text: Optional[str] = None
    if weather_flags and weather_flags.get("flag_extreme_heat_risk"):
        heat_text = HEAT_EMERGENCY_TEXT

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
        food_options=None,  # stays None until Task #8 (Places API integration)
    )
