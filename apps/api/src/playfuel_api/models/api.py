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
    TimelineEventKind,
    WeatherCondition,
)

# Shared config: camelCase aliases, populate by either snake_case or camelCase name.
_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ─── Rules engine input ───────────────────────────────────────────────────────


class MatchInput(BaseModel):
    """Minimal match data consumed by generate_match_scenarios(). No alias needed."""
    match_id: UUID
    tournament_id: UUID
    scheduled_start: datetime  # timezone-aware recommended; UTC assumed if naive
    # OQ-API-1(a) label fields — optional; rules engine ignores them
    round_label: Optional[str] = None
    opponent_label: Optional[str] = None
    court_label: Optional[str] = None


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


# ─── Phase 4 weather block — OQ-API-2 widening ─────────────────────────────────


class WeatherBlock(BaseModel):
    """Classified weather attached to plan response — §E.1/§E.2.

    is_stale=True signals iOS that the cache fallback was used (provider error).
    All seven flag fields are passed through so iOS EmergencyBanner logic
    mirrors the backend classification exactly.
    """
    model_config = _CAMEL

    temp_f: float
    humidity_pct: float
    condition: WeatherCondition
    flag_hot: bool
    flag_very_hot: bool
    flag_humid: bool
    flag_cold: bool
    flag_windy: bool
    flag_rain_risk: bool
    flag_extreme_heat_risk: bool
    is_stale: bool = False           # True when cache fallback was used (provider error)
    fetched_at: datetime
    provider: str


# ─── Phase 4 timeline block — OQ-API-2 / OQ-TRIAGE-1 ───────────────────────────


class TimelineEventOut(BaseModel):
    """Single timeline event in the plan response.

    Field names mirror iOS TimelineEvent.swift exactly (OQ-TRIAGE-1 resolution):
      id     → UUID v4 string (fresh per request; clients must not persist)
      time   → ISO 8601 timestamp string
      title  → short label for the event
      detail → guidance text (non-optional; emit empty string rather than null)
      kind   → TimelineEventKind enum value (camelCase string)
    """
    model_config = _CAMEL

    id: str
    time: str          # ISO 8601 timestamp (e.g. "2026-04-27T09:00:00+00:00")
    title: str
    detail: str        # iOS contract: non-optional; use "" rather than null
    kind: TimelineEventKind


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
    # ─ Phase 4 additions (OQ-API-2 incremental widening) ────────────────────────
    weather: Optional[WeatherBlock] = None        # alias: weather; None when no coords / provider fail
    timeline: list[TimelineEventOut] = []         # alias: timeline; empty list when engine produces none
    # ─ Phase 5 additions (Task #8 / Places integration) ──────────────────────
    food_options: Optional[list["FoodOption"]] = None  # alias: foodOptions
    bag_fallback_only: bool = False                     # alias: bagFallbackOnly
    # ─ Phase 6 additions (Task #9) ─────────────────────────────────────────────
    llm_summary: Optional["PlanExplanation"] = None    # alias: llmSummary; None for pre-Phase-6 plans


# ─── Phase 5 food option model — Task #8 ─────────────────────────────────────


class FoodOption(BaseModel):
    """Single restaurant / food option recommended for the plan window.

    Attached to Plan.food_options when venue coords are available and
    scenarios include at least one non-bag_only bucket.

    Fields:
        name:               Display name of the restaurant.
        category:           Food category (§F.1 enum value).
        drive_time_minutes: Estimated drive from venue (None if unknown).
        recommended_order:  §F.3 verbatim order template string.
        is_draft:           True for OQ-B unconfirmed templates.
        distance_meters:    Straight-line distance from venue (None if unknown).
        place_id:           Provider place ID (for deep-linking, deferred).
        provider:           Source identifier: "google" | "mock".
    """
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    name: str
    category: str
    drive_time_minutes: Optional[int] = None
    recommended_order: str
    is_draft: bool = False
    distance_meters: Optional[int] = None
    place_id: Optional[str] = None
    provider: str



# ─── Phase 6 LLM explanation models — Task #9 ────────────────────────────────────


class ScenarioSummary(BaseModel):
    """Condensed per-scenario data used as input to LLM/TemplateProvider."""
    model_config = _CAMEL

    scenario: str                         # "short" | "normal" | "long"
    duration_min: int
    gap_status: str                       # "ok" | "tight" | "overrun" | "no_next_match"
    food_bucket: Optional[str] = None     # None when no food strategy
    pickup_bucket: str                    # "bring_portable" | "pickup_during_match" | "wait_until_end"


class FoodRecommendationSummary(BaseModel):
    """Condensed food-option data for LLM input (no address / place_id)."""
    model_config = _CAMEL

    name: str
    category: str
    drive_time_minutes: Optional[int] = None
    is_draft: bool = False


class PlanExplanationInput(BaseModel):
    """Frozen structured input to the LLM/TemplateProvider.

    EVERY field that appears in the output prose MUST come from this object.
    Nothing is invented. Disclaimers pass through verbatim.
    Built via build_explanation_input() in services/llm.py.
    """
    venue_name: str
    match_start_iso: str
    match_round_label: Optional[str] = None
    next_match_estimated_iso: Optional[str] = None
    weather_temp_f: Optional[float] = None
    weather_humidity_pct: Optional[int] = None
    weather_flags: list[str] = []
    extreme_heat_risk: bool = False
    scenarios: list[ScenarioSummary] = []
    food_recommendations: list[FoodRecommendationSummary] = []
    bag_fallback_only: bool = False
    heat_emergency_text: Optional[str] = None
    user_disclaimer: str


class PlanExplanation(BaseModel):
    """Structured parent-friendly explanation produced by LLM or TemplateProvider.

    Fields:
        summary:               2–4 sentence parent-friendly intro.
        scenario_explanations: one entry per scenario kind ("short", "normal", "long").
        weather_note:          1–2 sentences on weather; None when no weather data.
        food_note:             1–2 sentences on food picks; None when not applicable.
        safety_note:           Always present. Contains user_disclaimer verbatim.
                               When extreme_heat_risk, heat_emergency_text is prepended verbatim.
        provider:              "template" | "anthropic" | "openai"
        model:                 e.g. "claude-haiku-3-5"; None for template provider.
        generated_at:          UTC timestamp of explanation generation.
    """
    model_config = _CAMEL

    summary: str
    scenario_explanations: dict[str, str]
    weather_note: Optional[str] = None
    food_note: Optional[str] = None
    safety_note: str
    provider: str
    model: Optional[str] = None
    generated_at: datetime

# ─── Request / response wrappers ─────────────────────────────────────────────


class GeneratePlanResponse(BaseModel):
    """HTTP 200 response from POST /v1/tournaments/{tid}/plans/generate."""
    model_config = _CAMEL
    plan: Plan
