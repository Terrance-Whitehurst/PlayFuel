"""
API request / response Pydantic models.

JSON KEY CONVENTION — camelCase
================================
iOS Swift property names are camelCase (e.g. `durationMin`, `gapStatus`).
Neither ScenarioPlan.swift nor Plan.swift define explicit CodingKeys, so Swift's
JSONDecoder expects the key names to match the property names exactly.

We therefore use `alias_generator=to_camel` so Pydantic serialises with camelCase
keys when `model.model_dump(by_alias=True)` / `response_model_by_alias=True` is
used. Pydantic field names (Python side) stay snake_case for readability.

DEVIATION from RULES_CONSTANTS_V1 §G JSON shapes (which show snake_case keys):
The §G examples use snake_case, but the iOS target uses camelCase property names
directly. camelCase output eliminates the need for `keyDecodingStrategy =
.convertFromSnakeCase` in the Phase 3 Task #6 iOS wiring. Flagged in README.md.

Enum VALUES remain snake_case (e.g. "no_next_match", "bag_only") — the
alias_generator only applies to field names, not enum string values. The iOS
GapStatus / FoodBucket etc. enums have matching raw values.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from playfuel_api.models.enums import (
    FoodBucket,
    GapStatus,
    PickupBucket,
    ScenarioKind,
    ScheduleConfidence,
)

# Shared config: camelCase aliases, populate by either snake_case or camelCase name.
_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ─── Rules engine input ───────────────────────────────────────────────────────


class MatchInput(BaseModel):
    """Minimal match data consumed by generate_match_scenarios(). No alias needed."""
    match_id: UUID
    tournament_id: UUID
    scheduled_start: datetime  # timezone-aware recommended; UTC assumed if naive


# ─── ScenarioPlan sub-objects ─────────────────────────────────────────────────


class FoodStrategy(BaseModel):
    """Food bucket + display text for a given gap — §B.2."""
    model_config = _CAMEL
    bucket: FoodBucket
    text: str


class PickupStrategy(BaseModel):
    """Parent pickup strategy — §B.3. bucket is None for no_next_match (§G.5)."""
    model_config = _CAMEL
    bucket: Optional[PickupBucket] = None
    text: str


class RewarmUp(BaseModel):
    """Re-warm-up window relative to next match start — §D.2.
    start_offset_min is negative (e.g. -30 = 30 min before next match).
    Null when gap_minutes < 60 or gap_status == overrun (§G.3).
    """
    model_config = _CAMEL
    start_offset_min: int   # alias: startOffsetMin
    duration_min: int       # alias: durationMin


class OverrunWarning(BaseModel):
    """Attached to ScenarioPlan when gap_status == overrun — §G.3 / §H.1."""
    model_config = _CAMEL
    code: str        # always "MATCH_OVERRUN"
    severity: str    # always "high"
    minutes_over: int  # alias: minutesOver
    message: str     # verbatim OVERRUN_MESSAGE from §H.1


# ─── ScenarioPlan ────────────────────────────────────────────────────────────


class ScenarioPlan(BaseModel):
    """Single match-duration scenario — §G.2 (normal) / §G.3 (overrun) / §G.5 (no_next_match).

    Cross-checked against apps/ios/PlayFuel/Sources/PlayFuel/Models/ScenarioPlan.swift:
      scenario         → scenario: String
      durationMin      → durationMin: Int         (alias of duration_min)
      estimatedEnd     → estimatedEnd: String      (alias of estimated_end)
      gapMinutes       → gapMinutes: Int?          (alias of gap_minutes)
      gapStatus        → gapStatus: GapStatus      (alias of gap_status)
      foodStrategy     → foodStrategy: FoodStrategy? (alias of food_strategy)
      pickupStrategy   → pickupStrategy: PickupStrategy (alias of pickup_strategy)
      rewarmUp         → rewarmUp: RewarmUp?       (alias of rewarm_up)
      overrunWarning   → overrunWarning: OverrunWarning? (alias of overrun_warning)
      warnings         → warnings: [String]
    iOS also has `id: UUID` (client-side generated, not in server schema — not returned).
    """
    model_config = _CAMEL

    scenario: ScenarioKind
    duration_min: int
    estimated_end: str        # e.g. "10:15 AM" — human-readable
    gap_minutes: Optional[int] = None
    gap_status: GapStatus
    food_strategy: Optional[FoodStrategy] = None
    pickup_strategy: PickupStrategy
    rewarm_up: Optional[RewarmUp] = None
    overrun_warning: Optional[OverrunWarning] = None
    warnings: list[str] = []


# ─── Plan (top-level envelope) ────────────────────────────────────────────────


class Plan(BaseModel):
    """Full tournament-day plan envelope — §G.4.

    Cross-checked against apps/ios/PlayFuel/Sources/PlayFuel/Models/Plan.swift:
      planId                → planId: String         (alias of plan_id — iOS expects String not UUID)
      tournamentId          → tournamentId: UUID      (alias of tournament_id)
      generatedAt           → generatedAt: String     (alias of generated_at — ISO 8601)
      warnings              → warnings: [String]
      scenarioPlans         → scenarioPlans: [ScenarioPlan] (alias of scenario_plans)

    Fields NOT in iOS Plan.swift (Phase 3 extras, iOS will ignore them):
      rulesConstantsVersion — for forward-compat version pinning
      scheduleConfidence    — for iOS to display plan reliability indicator
      heatEmergencyText     — verbatim §B HEAT_EMERGENCY_TEXT when extreme_heat_risk
    """
    model_config = _CAMEL

    plan_id: UUID              # alias: planId (iOS decodes as String — UUID.uuidString serialised)
    tournament_id: UUID        # alias: tournamentId
    generated_at: datetime     # alias: generatedAt
    rules_constants_version: str  # alias: rulesConstantsVersion
    schedule_confidence: ScheduleConfidence  # alias: scheduleConfidence
    heat_emergency_text: Optional[str] = None  # alias: heatEmergencyText
    warnings: list[str] = []
    scenario_plans: list[ScenarioPlan]  # alias: scenarioPlans


# ─── Request / response wrappers ─────────────────────────────────────────────


class GeneratePlanResponse(BaseModel):
    """HTTP 200 response from POST /v1/tournaments/{tid}/plans/generate."""
    model_config = _CAMEL
    plan: Plan
