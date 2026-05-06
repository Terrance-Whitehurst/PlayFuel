"""
Pydantic mirrors of public.* Postgres tables.

Column names and types must reconcile with db/supabase/migrations/0002_tables.sql.
These are used to deserialise Supabase PostgREST responses in route handlers.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from playfuel_api.models.enums import (
    FoodBucket,
    GapStatus,
    PickupBucket,
    ScenarioKind,
    ScheduleConfidence,
    WeatherCondition,
)


class UserRow(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime


class PlayerProfileRow(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str
    birth_year: Optional[int] = None
    age_bracket: Optional[str] = None
    dietary_notes: Optional[str] = None
    hydration_notes: Optional[str] = None
    injury_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TournamentRow(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    venue_name: Optional[str] = None
    venue_address: Optional[str] = None
    venue_city: Optional[str] = None
    venue_region: Optional[str] = None
    venue_postal: Optional[str] = None
    venue_lat: Optional[float] = None
    venue_lng: Optional[float] = None
    start_date: date
    end_date: Optional[date] = None
    # Phase A international rollout — migration 0018.
    time_zone: Optional[str] = None       # IANA tz identifier
    venue_country: Optional[str] = None   # ISO 3166-1 alpha-2
    # Phase C-infrastructure — migration 0020.
    preferred_language: Optional[str] = None  # 'en' | 'es'; None = English default
    # Accommodations — migration 0021.
    # All four nullable; tournament is fully functional with no accommodation set.
    # accommodation_lat and accommodation_lng are pair-constrained (both or neither).
    accommodation_lat: Optional[float] = None
    accommodation_lng: Optional[float] = None
    accommodation_address: Optional[str] = None
    accommodation_kind: Optional[str] = None  # 'home' | 'hotel' | None
    created_at: datetime
    updated_at: datetime


class MatchRow(BaseModel):
    id: UUID
    tournament_id: UUID
    scheduled_start: datetime
    actual_end_at: Optional[datetime] = None
    surface: Optional[str] = None
    format: Optional[str] = None
    age_bracket: Optional[str] = None
    display_order: Optional[int] = None
    # OQ-API-1(a) — migration 0005_match_labels.sql
    round_label: Optional[str] = None
    opponent_label: Optional[str] = None
    court_label: Optional[str] = None
    # Doubles-spec extension — migration 0007_doubles_support.sql
    doubles_format: Optional[str] = None  # 'best_of_3' | 'pro_set_8'; null when format != 'doubles'
    # Player scouting extension — migration 0010_players_and_notes.sql
    opponent_player_id: Optional[UUID] = None  # FK to players.id; null when no scouted opponent
    # match-done-state-cards spec §C — migration 0017_match_done_state.sql
    is_done: bool = False
    done_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WeatherSnapshotRow(BaseModel):
    id: UUID
    tournament_id: UUID
    temp_f: float                      # legacy imperial — computed from temp_c on new rows
    humidity_pct: float
    temp_c: Optional[float] = None     # °C canonical (Phase B+); None on pre-Phase-B rows
    wind_kmh: Optional[float] = None   # km/h canonical (Phase B+); None on pre-Phase-B rows
    wind_mph: Optional[float] = None
    precipitation_probability: Optional[float] = None
    condition: WeatherCondition
    flag_hot: bool
    flag_very_hot: bool
    flag_humid: bool
    flag_cold: bool
    flag_windy: bool
    flag_rain_risk: bool
    flag_extreme_heat_risk: bool
    fetched_at: datetime
    provider: str
    created_at: datetime
    updated_at: datetime


class MatchScenarioRow(BaseModel):
    id: UUID
    match_id: UUID
    scenario_kind: ScenarioKind
    duration_minutes: int
    estimated_end_at: datetime
    gap_minutes: Optional[int] = None
    gap_status: GapStatus
    food_bucket: Optional[FoodBucket] = None
    pickup_bucket: Optional[PickupBucket] = None
    rewarm_up_minutes: Optional[int] = None
    overrun_warning: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


# ─── Player scouting (migration 0010) ────────────────────────────────────────


class PlayerRow(BaseModel):
    """Mirror of public.players row."""
    id: UUID
    user_id: UUID
    display_name: str
    club: Optional[str] = None
    city: Optional[str] = None
    notes_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PlayerNoteRow(BaseModel):
    """Mirror of public.player_notes row."""
    id: UUID
    player_id: UUID
    user_id: UUID
    source: str          # player_note_source enum value
    body: str
    match_id: Optional[UUID] = None
    created_at: datetime


class MatchEvaluationRow(BaseModel):
    """Mirror of public.match_evaluations row. See POST_MATCH_EVAL_V1.md §B."""
    id: UUID
    match_id: UUID
    user_id: UUID
    result: str           # match_eval_result enum value
    score_text: Optional[str] = None
    effort_rating: Optional[int] = None
    focus_rating: Optional[int] = None
    went_well: list[str] = []
    to_improve: list[str] = []
    opponent_observations: Optional[str] = None
    key_moments: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PlanRow(BaseModel):
    id: UUID
    tournament_id: UUID
    plan_json: dict[str, Any]
    llm_summary: Optional[dict[str, Any]] = None
    rules_constants_version: str
    warnings: list[str]
    schedule_confidence: ScheduleConfidence
    # Doubles-spec extension — migration 0007_doubles_support.sql
    match_type: Optional[str] = None  # 'singles' | 'doubles'; null = legacy (treat as 'singles')
    # Nutrition-first IA — migration 0008_per_match_plans.sql
    match_id: Optional[UUID] = None   # FK to matches.id; null = legacy per-tournament plan
    created_at: datetime
    updated_at: datetime
