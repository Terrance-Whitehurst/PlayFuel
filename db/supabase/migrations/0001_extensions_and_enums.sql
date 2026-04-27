-- =============================================================================
-- PlayFuel Migration 0001: Extensions and Enums
-- =============================================================================
-- Run this file FIRST — it has no dependencies on other migrations.
-- Idempotent: CREATE EXTENSION uses IF NOT EXISTS; CREATE TYPE is guarded by
-- a DO/EXCEPTION block so re-running is safe.
--
-- All Postgres enum types are centralised here so that 0002_tables.sql can
-- reference them by name and so that adding a new value requires a single,
-- audited change rather than hunting through table DDL.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

-- pgcrypto provides gen_random_uuid() on Postgres < 13.
-- On Postgres 13+ (which Supabase uses) the function is built-in; this is a
-- no-op. Kept for portability.
create extension if not exists pgcrypto;


-- ---------------------------------------------------------------------------
-- scenario_kind
-- Used by:  match_scenarios.scenario_kind
-- Source:   RULES_CONSTANTS_V1.md §A — SCENARIO_DURATIONS_MIN keys
--           short=75 min, normal=120 min, long=180 min
-- ---------------------------------------------------------------------------
do $$ begin
  create type scenario_kind as enum ('short', 'normal', 'long');
exception when duplicate_object then null;
end $$;


-- ---------------------------------------------------------------------------
-- gap_status
-- Used by:  match_scenarios.gap_status
-- Source:   RULES_CONSTANTS_V1.md §G.1 — gap_status enum
--   ok            gap_minutes >= tight_threshold AND next match exists
--   tight         0 <= gap_minutes < tight_threshold
--   overrun       gap_minutes < 0  (match 1 end > match 2 start)
--   no_next_match estimated_next_match_start is null
-- ---------------------------------------------------------------------------
do $$ begin
  create type gap_status as enum ('ok', 'tight', 'overrun', 'no_next_match');
exception when duplicate_object then null;
end $$;


-- ---------------------------------------------------------------------------
-- schedule_confidence
-- Used by:  plans.schedule_confidence
-- Source:   RULES_CONSTANTS_V1.md §I OQ-G (resolved — see derivation rule)
-- Derivation rule (applied by FastAPI layer before INSERT, NOT a DB trigger):
--   'low'    if any scenario in the plan has gap_status IN ('overrun', 'no_next_match')
--   'medium' if any scenario in the plan has gap_status = 'tight'
--   'high'   otherwise
-- Default: 'high'
-- ---------------------------------------------------------------------------
do $$ begin
  create type schedule_confidence as enum ('high', 'medium', 'low');
exception when duplicate_object then null;
end $$;


-- ---------------------------------------------------------------------------
-- food_bucket
-- Used by:  match_scenarios.food_bucket
-- Source:   RULES_CONSTANTS_V1.md §B.2 — Food Strategy Buckets
-- Half-open [lo, hi) intervals:
--   bag_only     [0,   45)
--   portable     [45,  90)
--   quick_pickup [90,  150)
--   light_meal   [150, ∞)
-- ---------------------------------------------------------------------------
do $$ begin
  create type food_bucket as enum ('bag_only', 'portable', 'quick_pickup', 'light_meal');
exception when duplicate_object then null;
end $$;


-- ---------------------------------------------------------------------------
-- pickup_bucket
-- Used by:  match_scenarios.pickup_bucket
-- Source:   RULES_CONSTANTS_V1.md §B.3 — Parent Pickup Strategy Buckets
-- Half-open [lo, hi) intervals:
--   bring_portable       [0,   60)
--   pickup_during_match  [60,  120)
--   wait_until_end       [120, ∞)
-- ---------------------------------------------------------------------------
do $$ begin
  create type pickup_bucket as enum ('bring_portable', 'pickup_during_match', 'wait_until_end');
exception when duplicate_object then null;
end $$;


-- ---------------------------------------------------------------------------
-- weather_condition
-- Used by:  weather_snapshots.condition
-- Values: Engineering3 proposal — confirm with product if 'partly_cloudy',
--         'fog', or 'haze' are needed. Track as a new OQ if changed.
-- ---------------------------------------------------------------------------
do $$ begin
  create type weather_condition as enum ('clear', 'cloudy', 'rain', 'storm', 'snow');
exception when duplicate_object then null;
end $$;
