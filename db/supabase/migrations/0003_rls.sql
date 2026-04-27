-- =============================================================================
-- PlayFuel Migration 0003: Row Level Security Policies
-- =============================================================================
-- Prerequisites: 0001 + 0002 must be applied first.
--
-- Security model: auth.uid() = user_id on every user-owned table.
-- For direct-ownership tables (users, player_profiles, tournaments):
--   predicate is  (select auth.uid()) = user_id
-- For child tables one hop away (matches, weather_snapshots, food_options, plans):
--   predicate is  exists (select 1 from tournaments t
--                         where t.id = <table>.tournament_id
--                           and t.user_id = (select auth.uid()))
-- For two-hop tables (match_scenarios → matches → tournaments;
--                      feedback → plans → tournaments):
--   predicate uses an explicit join — no nested views.
--
-- (select auth.uid()) pattern — used everywhere instead of bare auth.uid() —
-- is the Supabase-recommended form for query planner caching.
--
-- Every table has exactly 4 policies: SELECT, INSERT, UPDATE, DELETE.
-- "FOR ALL" policies are intentionally avoided for auditability.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Enable RLS on all tables
-- ---------------------------------------------------------------------------
alter table public.users               enable row level security;
alter table public.player_profiles     enable row level security;
alter table public.tournaments         enable row level security;
alter table public.matches             enable row level security;
alter table public.match_scenarios     enable row level security;
alter table public.weather_snapshots   enable row level security;
alter table public.food_options        enable row level security;
alter table public.plans               enable row level security;
alter table public.feedback            enable row level security;


-- ===========================================================================
-- TABLE: users
-- Ownership predicate: (select auth.uid()) = id
-- Security claim: A user can only read and modify their own shadow row.
-- ===========================================================================
create policy "users_select_own"
  on public.users
  for select
  using ((select auth.uid()) = id);

create policy "users_insert_own"
  on public.users
  for insert
  with check ((select auth.uid()) = id);

create policy "users_update_own"
  on public.users
  for update
  using  ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

create policy "users_delete_own"
  on public.users
  for delete
  using ((select auth.uid()) = id);


-- ===========================================================================
-- TABLE: player_profiles
-- Ownership predicate: (select auth.uid()) = user_id
-- Security claim: A parent can only read, create, edit, and delete
--                 their own player profiles.
-- ===========================================================================
create policy "player_profiles_select_own"
  on public.player_profiles
  for select
  using ((select auth.uid()) = user_id);

create policy "player_profiles_insert_own"
  on public.player_profiles
  for insert
  with check ((select auth.uid()) = user_id);

create policy "player_profiles_update_own"
  on public.player_profiles
  for update
  using  ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "player_profiles_delete_own"
  on public.player_profiles
  for delete
  using ((select auth.uid()) = user_id);


-- ===========================================================================
-- TABLE: tournaments
-- Ownership predicate: (select auth.uid()) = user_id
-- Security claim: A parent can only read, create, edit, and delete
--                 their own tournaments.
-- ===========================================================================
create policy "tournaments_select_own"
  on public.tournaments
  for select
  using ((select auth.uid()) = user_id);

create policy "tournaments_insert_own"
  on public.tournaments
  for insert
  with check ((select auth.uid()) = user_id);

create policy "tournaments_update_own"
  on public.tournaments
  for update
  using  ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "tournaments_delete_own"
  on public.tournaments
  for delete
  using ((select auth.uid()) = user_id);


-- ===========================================================================
-- TABLE: matches
-- Ownership: one hop via tournament_id → tournaments.user_id
-- Security claim: A parent can only access matches that belong to their
--                 own tournaments.
-- Index on matches.tournament_id (from 0002) makes the subquery fast.
-- ===========================================================================
create policy "matches_select_own"
  on public.matches
  for select
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = matches.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "matches_insert_own"
  on public.matches
  for insert
  with check (
    exists (
      select 1 from public.tournaments t
      where t.id = matches.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "matches_update_own"
  on public.matches
  for update
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = matches.tournament_id
        and t.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.tournaments t
      where t.id = matches.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "matches_delete_own"
  on public.matches
  for delete
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = matches.tournament_id
        and t.user_id = (select auth.uid())
    )
  );


-- ===========================================================================
-- TABLE: match_scenarios
-- Ownership: two hops — match_scenarios.match_id → matches.tournament_id →
--            tournaments.user_id
-- Security claim: A parent can only access scenarios for their own matches.
-- Indexes on match_scenarios.match_id and matches.tournament_id (from 0002)
-- make the two-hop join fast.
-- ===========================================================================
create policy "match_scenarios_select_own"
  on public.match_scenarios
  for select
  using (
    exists (
      select 1
      from public.matches m
      join public.tournaments t on t.id = m.tournament_id
      where m.id = match_scenarios.match_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "match_scenarios_insert_own"
  on public.match_scenarios
  for insert
  with check (
    exists (
      select 1
      from public.matches m
      join public.tournaments t on t.id = m.tournament_id
      where m.id = match_scenarios.match_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "match_scenarios_update_own"
  on public.match_scenarios
  for update
  using (
    exists (
      select 1
      from public.matches m
      join public.tournaments t on t.id = m.tournament_id
      where m.id = match_scenarios.match_id
        and t.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.matches m
      join public.tournaments t on t.id = m.tournament_id
      where m.id = match_scenarios.match_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "match_scenarios_delete_own"
  on public.match_scenarios
  for delete
  using (
    exists (
      select 1
      from public.matches m
      join public.tournaments t on t.id = m.tournament_id
      where m.id = match_scenarios.match_id
        and t.user_id = (select auth.uid())
    )
  );


-- ===========================================================================
-- TABLE: weather_snapshots
-- Ownership: one hop via tournament_id → tournaments.user_id
-- Security claim: A parent can only access weather snapshots for their
--                 own tournaments.
-- ===========================================================================
create policy "weather_snapshots_select_own"
  on public.weather_snapshots
  for select
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = weather_snapshots.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "weather_snapshots_insert_own"
  on public.weather_snapshots
  for insert
  with check (
    exists (
      select 1 from public.tournaments t
      where t.id = weather_snapshots.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "weather_snapshots_update_own"
  on public.weather_snapshots
  for update
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = weather_snapshots.tournament_id
        and t.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.tournaments t
      where t.id = weather_snapshots.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "weather_snapshots_delete_own"
  on public.weather_snapshots
  for delete
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = weather_snapshots.tournament_id
        and t.user_id = (select auth.uid())
    )
  );


-- ===========================================================================
-- TABLE: food_options
-- Ownership: one hop via tournament_id → tournaments.user_id
-- Security claim: A parent can only access food options for their own
--                 tournaments.
-- ===========================================================================
create policy "food_options_select_own"
  on public.food_options
  for select
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = food_options.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "food_options_insert_own"
  on public.food_options
  for insert
  with check (
    exists (
      select 1 from public.tournaments t
      where t.id = food_options.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "food_options_update_own"
  on public.food_options
  for update
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = food_options.tournament_id
        and t.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.tournaments t
      where t.id = food_options.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "food_options_delete_own"
  on public.food_options
  for delete
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = food_options.tournament_id
        and t.user_id = (select auth.uid())
    )
  );


-- ===========================================================================
-- TABLE: plans
-- Ownership: one hop via tournament_id → tournaments.user_id
-- Security claim: A parent can only access plans for their own tournaments.
-- ===========================================================================
create policy "plans_select_own"
  on public.plans
  for select
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = plans.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "plans_insert_own"
  on public.plans
  for insert
  with check (
    exists (
      select 1 from public.tournaments t
      where t.id = plans.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "plans_update_own"
  on public.plans
  for update
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = plans.tournament_id
        and t.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.tournaments t
      where t.id = plans.tournament_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "plans_delete_own"
  on public.plans
  for delete
  using (
    exists (
      select 1 from public.tournaments t
      where t.id = plans.tournament_id
        and t.user_id = (select auth.uid())
    )
  );


-- ===========================================================================
-- TABLE: feedback
-- Ownership: two hops — feedback.plan_id → plans.tournament_id →
--            tournaments.user_id
-- Security claim: A parent can only access feedback for their own plans.
-- Indexes on feedback.plan_id, plans.tournament_id, tournaments.user_id
-- (all from 0002) make the two-hop join fast.
-- ===========================================================================
create policy "feedback_select_own"
  on public.feedback
  for select
  using (
    exists (
      select 1
      from public.plans p
      join public.tournaments t on t.id = p.tournament_id
      where p.id = feedback.plan_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "feedback_insert_own"
  on public.feedback
  for insert
  with check (
    exists (
      select 1
      from public.plans p
      join public.tournaments t on t.id = p.tournament_id
      where p.id = feedback.plan_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "feedback_update_own"
  on public.feedback
  for update
  using (
    exists (
      select 1
      from public.plans p
      join public.tournaments t on t.id = p.tournament_id
      where p.id = feedback.plan_id
        and t.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1
      from public.plans p
      join public.tournaments t on t.id = p.tournament_id
      where p.id = feedback.plan_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "feedback_delete_own"
  on public.feedback
  for delete
  using (
    exists (
      select 1
      from public.plans p
      join public.tournaments t on t.id = p.tournament_id
      where p.id = feedback.plan_id
        and t.user_id = (select auth.uid())
    )
  );
