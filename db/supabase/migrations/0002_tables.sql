-- =============================================================================
-- PlayFuel Migration 0002: Tables, Indexes, and updated_at Triggers
-- =============================================================================
-- Prerequisites: 0001_extensions_and_enums.sql must be applied first.
--
-- Conventions:
--   • Every table:  id uuid pk, created_at timestamptz, updated_at timestamptz
--   • Every FK:     ON DELETE CASCADE with justification comment
--   • Every FK:     explicit index (required for RLS subquery performance)
--   • Every JSONB:  comment on column pointing to RULES_CONSTANTS_V1 section
--   • updated_at:   bumped automatically by the shared set_updated_at() trigger
--
-- Table creation order respects FK dependency:
--   1. users
--   2. player_profiles
--   3. tournaments
--   4. matches
--   5. match_scenarios
--   6. weather_snapshots
--   7. food_options
--   8. plans
--   9. feedback
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Shared updated_at trigger function
-- One function; one trigger per table. Do NOT duplicate this body per table.
-- ---------------------------------------------------------------------------
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;


-- ===========================================================================
-- TABLE: users
-- ===========================================================================
-- Thin shadow of auth.users. Never duplicates email, name, or password.
-- id is a foreign key into auth.users so Supabase Auth is the source of truth
-- for identity.  See PRD.md §11 (data minimisation).
-- The handle_new_user() trigger in 0004_auth_trigger.sql auto-populates this
-- table on every new sign-in; rows here are read-only at the application layer.
-- ---------------------------------------------------------------------------
create table if not exists public.users (
  -- id mirrors auth.users.id — NOT gen_random_uuid(); it is set by the trigger
  id          uuid primary key references auth.users (id)
                on delete cascade,   -- cascade: deleting the auth user wipes app data (PRD §11 deletion flow)
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create trigger set_updated_at_users
  before update on public.users
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: player_profiles
-- ===========================================================================
-- Parent-owned player record. Stores age range / birth year only — never
-- exact birthdate. Dietary, hydration, and injury notes are optional.
-- See PRD.md §11; USER_STORIES.md US-02.
-- ---------------------------------------------------------------------------
create table if not exists public.player_profiles (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references public.users (id)
                     on delete cascade,  -- cascade: removing the user removes all their player profiles
  display_name     text not null,
  -- birth_year and age_bracket are alternatives; collect whichever the parent provides.
  -- Do NOT collect exact birthdate (PRD §11).
  birth_year       int check (
                     birth_year is null
                     or (birth_year >= 2005 and birth_year <= extract(year from current_date)::int)
                   ),
  age_bracket      text,   -- e.g. "10U", "12U", "14U", "16U", "18U"
  dietary_notes    text,   -- optional (PRD §11)
  hydration_notes  text,   -- optional
  injury_notes     text,   -- optional; no medical advice stored — parent freeform notes only
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index idx_player_profiles_user_id on public.player_profiles (user_id);

create trigger set_updated_at_player_profiles
  before update on public.player_profiles
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: tournaments
-- ===========================================================================
-- One tournament per tournament-day use case. Stores venue location (lat/lng)
-- for weather + places API calls; does NOT store live player location history.
-- See PRD.md §11; USER_STORIES.md US-03.
-- ---------------------------------------------------------------------------
create table if not exists public.tournaments (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users (id)
                    on delete cascade,  -- cascade: removing the user removes all tournaments and children
  name            text not null,
  venue_name      text,
  venue_address   text,
  venue_city      text,
  venue_region    text,    -- state / province
  venue_postal    text,
  -- Lat/lng stored for weather and food-options API calls only.
  -- NOT used for live tracking (PRD §11).
  venue_lat       numeric(9, 6),
  venue_lng       numeric(9, 6),
  start_date      date not null,
  end_date        date,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index idx_tournaments_user_id on public.tournaments (user_id);

create trigger set_updated_at_tournaments
  before update on public.tournaments
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: matches
-- ===========================================================================
-- A single match within a tournament. display_order controls ordering on the
-- timeline. estimated_duration_minutes is optional — the rules engine falls
-- back to SCENARIO_DURATIONS_MIN constants when null.
-- actual_end_at is nullable and populated post-match for future analytics.
-- See USER_STORIES.md US-04; RULES_CONSTANTS_V1.md §A.
-- ---------------------------------------------------------------------------
create table if not exists public.matches (
  id                          uuid primary key default gen_random_uuid(),
  tournament_id               uuid not null references public.tournaments (id)
                                on delete cascade,  -- cascade: deleting a tournament removes all its matches
  scheduled_start             timestamptz not null,
  estimated_duration_minutes  int,    -- null → rules engine uses SCENARIO_DURATIONS_MIN defaults
  actual_end_at               timestamptz,  -- nullable; populated post-match
  surface                     text,   -- e.g. "hard", "clay", "grass"
  format                      text,   -- e.g. "singles", "doubles"
  age_bracket                 text,   -- e.g. "14U", "16U"
  display_order               int,    -- 1-indexed ordering within the tournament
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);

create index idx_matches_tournament_id on public.matches (tournament_id);

create trigger set_updated_at_matches
  before update on public.matches
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: match_scenarios
-- ===========================================================================
-- One row per (match, scenario_kind) tuple. Generated by the rules engine
-- (POST /tournaments/{id}/plans/generate) and stored for retrieval.
--
-- gap_minutes: null when gap_status = 'no_next_match'
-- food_bucket: null when gap_status IN ('overrun', 'no_next_match') — clamped
--              to 'bag_only' on overrun; null on no_next_match
-- rewarm_up_minutes: null when gap_minutes < 60 (RULES_CONSTANTS_V1.md §D.2)
--                    or when gap_status = 'overrun' / 'no_next_match'
-- overrun_warning: null unless gap_status = 'overrun'
--
-- See RULES_CONSTANTS_V1.md §G for full negative-gap contract.
-- ---------------------------------------------------------------------------
create table if not exists public.match_scenarios (
  id               uuid primary key default gen_random_uuid(),
  match_id         uuid not null references public.matches (id)
                     on delete cascade,  -- cascade: deleting a match removes its computed scenarios
  scenario_kind    scenario_kind not null,
  duration_minutes int not null,
  estimated_end_at timestamptz not null,
  gap_minutes      int,          -- null when no next match
  gap_status       gap_status not null,
  food_bucket      food_bucket,  -- null on 'no_next_match'; 'bag_only' on 'overrun'
  pickup_bucket    pickup_bucket, -- null on 'no_next_match'; 'bring_portable' on 'overrun'
  rewarm_up_minutes int,         -- null when gap_minutes < 60 or gap_status in ('overrun','no_next_match')
  overrun_warning  jsonb,        -- null unless gap_status = 'overrun'
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

comment on column public.match_scenarios.overrun_warning is
  'Null unless gap_status = ''overrun''. Shape per RULES_CONSTANTS_V1.md §G.3: '
  '{code: "MATCH_OVERRUN", severity: "high", minutes_over: int, message: str}';

create index idx_match_scenarios_match_id on public.match_scenarios (match_id);

create trigger set_updated_at_match_scenarios
  before update on public.match_scenarios
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: weather_snapshots
-- ===========================================================================
-- Point-in-time weather reading for the tournament venue. Derived boolean
-- flags are stored denormalised so that historical records remain accurate
-- even if §E thresholds change in a future RULES_CONSTANTS version.
-- See RULES_CONSTANTS_V1.md §E; USER_STORIES.md US-07.
-- ---------------------------------------------------------------------------
create table if not exists public.weather_snapshots (
  id                       uuid primary key default gen_random_uuid(),
  tournament_id            uuid not null references public.tournaments (id)
                             on delete cascade,  -- cascade: deleting a tournament removes weather history
  temp_f                   numeric(5, 1) not null,
  humidity_pct             numeric(4, 1) not null,
  wind_mph                 numeric(5, 1),
  precipitation_probability numeric(4, 1),    -- 0–100 percent
  condition                weather_condition not null,
  -- Derived flags — source thresholds in RULES_CONSTANTS_V1.md §E.1
  flag_hot                 boolean not null default false,  -- temp_f >= 85
  flag_very_hot            boolean not null default false,  -- temp_f >= 90
  flag_humid               boolean not null default false,  -- humidity_pct >= 65
  flag_cold                boolean not null default false,  -- temp_f <= 50
  flag_windy               boolean not null default false,  -- wind_mph >= 15
  flag_rain_risk           boolean not null default false,  -- precipitation_probability >= 40
  -- Derived composite flag — source: RULES_CONSTANTS_V1.md §E.2
  -- extreme_heat_risk = very_hot OR (hot AND humid)
  flag_extreme_heat_risk   boolean not null default false,
  fetched_at               timestamptz not null default now(),
  provider                 text not null,  -- e.g. 'weatherkit', 'openweather'
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create index idx_weather_snapshots_tournament_id on public.weather_snapshots (tournament_id);

create trigger set_updated_at_weather_snapshots
  before update on public.weather_snapshots
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: food_options
-- ===========================================================================
-- Nearby food options fetched from the Places API (Phase 5).
-- recommended_order is a JSONB object; template_id references the registry
-- in RULES_CONSTANTS_V1.md §F.3 (e.g. 'fast_casual_bowl').
-- See USER_STORIES.md US-08.
-- ---------------------------------------------------------------------------
create table if not exists public.food_options (
  id               uuid primary key default gen_random_uuid(),
  tournament_id    uuid not null references public.tournaments (id)
                     on delete cascade,  -- cascade: deleting a tournament removes its food options cache
  place_name       text not null,
  place_id         text,       -- provider-assigned ID (Google Places / Yelp)
  distance_m       int,        -- distance from venue in metres
  category         text,       -- food category label
  template_id      text,       -- references RULES_CONSTANTS_V1.md §F.3 template registry
  recommended_order jsonb,     -- see comment below
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

comment on column public.food_options.recommended_order is
  'Recommended order template object per RULES_CONSTANTS_V1.md §F.3. '
  'Shape: {text: str, template_id: str}. '
  'Example: {text: "Chicken rice bowl with light beans, mild toppings, sauce on the side", '
  'template_id: "fast_casual_bowl"}';

create index idx_food_options_tournament_id on public.food_options (tournament_id);

create trigger set_updated_at_food_options
  before update on public.food_options
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: plans
-- ===========================================================================
-- Generated plan envelope. plan_json contains the full structured output from
-- the rules engine. llm_summary stores the LLM's parent-friendly explanation
-- (Phase 6). Both are stored separately (PRD.md §4 — rules engine first).
--
-- rules_constants_version: must match RULES_CONSTANTS_VERSION in constants.py.
--   Stored here so we know which version generated each plan row.
--
-- warnings: aggregated warning codes from all scenario plans.
--   See RULES_CONSTANTS_V1.md §G.4.
--
-- schedule_confidence: derived by FastAPI before INSERT.
--   Rule (resolves OQ-G per RULES_CONSTANTS_V1.md §I):
--     'low'    if any scenario.gap_status IN ('overrun', 'no_next_match')
--     'medium' if any scenario.gap_status = 'tight'
--     'high'   otherwise
-- ---------------------------------------------------------------------------
create table if not exists public.plans (
  id                       uuid primary key default gen_random_uuid(),
  tournament_id            uuid not null references public.tournaments (id)
                             on delete cascade,  -- cascade: deleting a tournament removes all its plans
  plan_json                jsonb not null,
  llm_summary              text,   -- null until Phase 6 LLM layer is wired
  rules_constants_version  text not null,  -- e.g. '1.0.0' — from RULES_CONSTANTS_VERSION
  warnings                 jsonb not null default '[]'::jsonb,
  schedule_confidence      schedule_confidence not null default 'high',
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

comment on column public.plans.plan_json is
  'Full structured plan envelope from the rules engine. '
  'Top-level shape per RULES_CONSTANTS_V1.md §G.4: '
  '{plan_id, tournament_id, generated_at, warnings[], scenario_plans[]}. '
  'Each scenario_plan matches §G.2 (normal) or §G.3 (overrun) or §G.5 (no_next_match).';

comment on column public.plans.warnings is
  'Aggregated warning codes from all scenario_plans. '
  'Per RULES_CONSTANTS_V1.md §G.4. Each element is a warning code string, e.g. "MATCH_OVERRUN".';

create index idx_plans_tournament_id on public.plans (tournament_id);

create trigger set_updated_at_plans
  before update on public.plans
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: feedback
-- ===========================================================================
-- Post-tournament feedback linked to a specific plan (Phase 7).
-- No direct user_id column — ownership is resolved via plan → tournament.
-- RLS policy joins feedback → plans → tournaments to enforce ownership.
-- On delete: cascade from plan; if the plan is deleted, feedback is deleted.
-- If feedback must survive plan deletion, change to ON DELETE SET NULL and
-- add a nullable plan_id — revisit in Phase 7.
-- ---------------------------------------------------------------------------
create table if not exists public.feedback (
  id          uuid primary key default gen_random_uuid(),
  plan_id     uuid not null references public.plans (id)
                on delete cascade,  -- cascade: deleting a plan removes its feedback
  rating      int check (rating between 1 and 5),
  what_worked text,
  what_didnt  text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index idx_feedback_plan_id on public.feedback (plan_id);

create trigger set_updated_at_feedback
  before update on public.feedback
  for each row execute function set_updated_at();
