"""Plan envelope assembly and schedule-confidence derivation.

build_plan_envelope() wraps a list[ScenarioPlan] into the top-level Plan
object, setting schedule_confidence, warnings, and heat_emergency_text.

derive_schedule_confidence() implements the rule from db/supabase/README:
    low    — any scenario.gap_status in {overrun, no_next_match}
    medium — any scenario.gap_status == tight  (only if no low-priority statuses)
    high   — otherwise (all scenarios are ok)

Heat emergency text (§E.2 / §H.2):
    Attached to plan when weather_flags['flag_extreme_heat_risk'] is True.
    HEAT_EMERGENCY_TEXT is imported from hard_coded_strings — never re-typed here.
    ⚠️ DRAFT — OQ-11 pre-launch blocker (attorney review pending).

plan_json persistence:
    Callers must call plan.model_dump(by_alias=True, mode='json') before INSERT
    so the stored JSONB uses camelCase keys consistent with iOS contract.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from playfuel_api.models.api import Plan, ScenarioPlan
from playfuel_api.models.enums import GapStatus, ScheduleConfidence
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


def build_plan_envelope(
    tournament_id: uuid.UUID,
    scenarios: list[ScenarioPlan],
    *,
    weather_flags: Optional[dict[str, bool]] = None,
) -> Plan:
    """Assemble the top-level Plan envelope from engine output.

    Args:
        tournament_id: UUID of the tournament being planned.
        scenarios:     Output of generate_match_scenarios() — all three ScenarioKinds.
        weather_flags: Optional output of classify_weather(); triggers HEAT_EMERGENCY_TEXT
                       when flag_extreme_heat_risk is True (§E.2).

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
    # ⚠️ HEAT_EMERGENCY_TEXT is DRAFT — OQ-11 pre-launch blocker.
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
    )
