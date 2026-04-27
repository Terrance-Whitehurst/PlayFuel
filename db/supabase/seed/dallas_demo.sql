-- =============================================================================
-- PlayFuel Seed: Dallas Demo
-- =============================================================================
-- Purpose: Insert the canonical Dallas Junior Open end-to-end test fixture.
--          Used for local development and integration testing.
--
-- Fixed UUIDs (document these — referenced in tests and README):
--   Demo user:        a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
--   Demo tournament:  b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
--   Match 1 (9 AM):   c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
--   Match 2 (1 PM):   d0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
--   Weather snapshot: e0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
--
-- Scenario: Dallas Junior Open, May 15 2026
--   Match 1: 9:00 AM (CDT = UTC-5)
--   Match 2: 1:00 PM (estimated)
--   Gap:     240 minutes
--   Weather: 88°F / 72% humidity → hot=true, humid=true, extreme_heat_risk=true
--
-- Expected rules-engine output (per RULES_CONSTANTS_V1.md §B.4):
--   Short  (75 min)  → gap=165 → light_meal  / wait_until_end
--   Normal (120 min) → gap=120 → quick_pickup / wait_until_end
--   Long   (180 min) → gap= 60 → portable    / pickup_during_match
--
-- Run with:
--   psql -f seed/dallas_demo.sql
-- Or via Supabase local stack:
--   supabase db reset  (runs migrations then seed automatically)
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Step 1: Create the demo auth user
-- In Supabase local dev, auth.users is accessible with superuser privileges.
-- In production, users are created via Supabase Auth API (Sign in with Apple).
-- ON CONFLICT DO NOTHING makes this idempotent for repeated seed runs.
-- ---------------------------------------------------------------------------
insert into auth.users (
  id,
  email,
  role,
  aud,
  created_at,
  updated_at,
  email_confirmed_at,
  raw_app_meta_data,
  raw_user_meta_data,
  is_super_admin,
  encrypted_password
)
values (
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'demo@playfuel.app',
  'authenticated',
  'authenticated',
  now(),
  now(),
  now(),
  '{"provider": "email", "providers": ["email"]}'::jsonb,
  '{}'::jsonb,
  false,
  ''  -- no password for demo; auth via Apple in real usage
)
on conflict (id) do nothing;

-- The on_auth_user_created trigger fires automatically and creates the
-- public.users row. If the trigger already ran (re-seed), the ON CONFLICT
-- DO NOTHING in handle_new_user() prevents a duplicate.

-- Safety net: explicit insert in case seed runs before trigger is applied
-- (e.g. during schema-reset testing sequences).
insert into public.users (id, created_at, updated_at)
values ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', now(), now())
on conflict (id) do nothing;


-- ---------------------------------------------------------------------------
-- Step 2: Tournament — Dallas Junior Open
-- ---------------------------------------------------------------------------
insert into public.tournaments (
  id,
  user_id,
  name,
  venue_name,
  venue_address,
  venue_city,
  venue_region,
  venue_postal,
  venue_lat,
  venue_lng,
  start_date,
  end_date
)
values (
  'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'Dallas Junior Open',
  'XYZ Tennis Center',
  '1234 Tennis Blvd',
  'Dallas',
  'TX',
  '75201',
  32.776664,    -- Dallas, TX approximate lat
  -96.796988,   -- Dallas, TX approximate lng
  '2026-05-15',
  '2026-05-17'
)
on conflict (id) do nothing;


-- ---------------------------------------------------------------------------
-- Step 3: Match 1 — 9:00 AM CDT (UTC-05:00)
-- display_order=1; this is the match being planned for.
-- ---------------------------------------------------------------------------
insert into public.matches (
  id,
  tournament_id,
  scheduled_start,
  estimated_duration_minutes,
  actual_end_at,
  surface,
  format,
  age_bracket,
  display_order,
  round_label,
  court_label
)
values (
  'c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  '2026-05-15 09:00:00-05:00',  -- 9:00 AM CDT
  null,                          -- no override; rules engine uses SCENARIO_DURATIONS_MIN
  null,
  'hard',
  'singles',
  '14U',
  1,
  'R16',       -- round label: Round of 16
  'Court 7'    -- court label
)
on conflict (id) do nothing;


-- ---------------------------------------------------------------------------
-- Step 4: Match 2 — 1:00 PM CDT (estimated next match)
-- display_order=2; used by rules engine to calculate gap_minutes.
-- ---------------------------------------------------------------------------
insert into public.matches (
  id,
  tournament_id,
  scheduled_start,
  estimated_duration_minutes,
  actual_end_at,
  surface,
  format,
  age_bracket,
  display_order,
  round_label
)
values (
  'd0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  '2026-05-15 13:00:00-05:00',  -- 1:00 PM CDT
  null,
  null,
  'hard',
  'singles',
  '14U',
  2,
  'QF'         -- round label: Quarterfinal
)
on conflict (id) do nothing;


-- ---------------------------------------------------------------------------
-- Step 5: Weather snapshot — 88°F / 72% humidity
-- Derived flags pre-computed from RULES_CONSTANTS_V1.md §E.1:
--   flag_hot = true   (88 >= 85)
--   flag_very_hot = false (88 < 90)
--   flag_humid = true  (72 >= 65)
--   flag_cold = false
--   flag_windy = false
--   flag_rain_risk = false
--   flag_extreme_heat_risk = true (hot AND humid per §E.2)
-- ---------------------------------------------------------------------------
insert into public.weather_snapshots (
  id,
  tournament_id,
  temp_f,
  humidity_pct,
  wind_mph,
  precipitation_probability,
  condition,
  flag_hot,
  flag_very_hot,
  flag_humid,
  flag_cold,
  flag_windy,
  flag_rain_risk,
  flag_extreme_heat_risk,
  fetched_at,
  provider
)
values (
  'e0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
  88.0,
  72.0,
  8.0,
  5.0,
  'clear',
  true,   -- flag_hot:  88 >= 85 ✓
  false,  -- flag_very_hot: 88 < 90
  true,   -- flag_humid: 72 >= 65 ✓
  false,  -- flag_cold
  false,  -- flag_windy: 8 < 15
  false,  -- flag_rain_risk: 5 < 40
  true,   -- flag_extreme_heat_risk: hot AND humid ✓  (per §E.2)
  now(),
  'seed'  -- synthetic; replace with 'weatherkit' or 'openweather' in real data
)
on conflict (id) do nothing;


-- ---------------------------------------------------------------------------
-- Verification queries (comment out after confirming seed applied correctly)
-- ---------------------------------------------------------------------------
-- select 'users' as tbl, count(*) from public.users
--   where id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
-- union all
-- select 'tournaments', count(*) from public.tournaments
--   where id = 'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
-- union all
-- select 'matches', count(*) from public.matches
--   where tournament_id = 'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
-- union all
-- select 'weather_snapshots', count(*) from public.weather_snapshots
--   where tournament_id = 'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
-- Expected: each row = 1, matches = 2.
