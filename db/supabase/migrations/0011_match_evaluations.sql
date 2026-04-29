-- =============================================================================
-- PlayFuel Migration 0011: Post-Match Evaluations
-- =============================================================================
-- Prerequisites: 0001–0010 must be applied first.
-- Idempotent: all statements use IF NOT EXISTS / DO $$ guards.
--
-- Creates:
--   public.match_evaluations — per-match structured post-match write-up
--   match_eval_result        — enum for match outcome
-- Alters: nothing
-- RLS:
--   4 new policies (SELECT/INSERT/UPDATE/DELETE) + ALTER TABLE enable RLS
--
-- Privacy: opponent_observations flows under PRIVACY_V1.md §13 "Notes about
--   other minors" posture — same as player_notes.body.
--   See POST_MATCH_EVAL_V1.md §H.
-- FK target: public.users(id) — mirrors player_profiles, tournaments, players pattern.
--   (public.users is the shadow table; NOT auth.users directly.)
-- UNIQUE on match_id: enforces one evaluation per match (1:1). PATCH overwrites.
-- went_well / to_improve: text[] with NO Postgres array-length constraint.
--   API layer enforces 5-item × 200-char-per-item limits (Pydantic @field_validator).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Enum: match_eval_result
-- Values: won, lost, withdrew, retired
-- Verified no collision with enums in 0001_extensions_and_enums.sql or 0010:
--   scenario_kind, gap_status, schedule_confidence, food_bucket,
--   pickup_bucket, weather_condition, player_note_source — none clash.
-- ---------------------------------------------------------------------------
do $$ begin
  create type match_eval_result as enum ('won', 'lost', 'withdrew', 'retired');
exception when duplicate_object then null;
end $$;


-- ===========================================================================
-- TABLE: match_evaluations
-- ===========================================================================
-- One row per match (UNIQUE on match_id). PATCH overwrites — no version history.
--
-- went_well / to_improve: text[] capped at 5 items via application layer;
--   Postgres DDL has no standard array element-count CHECK — API enforces.
--
-- opponent_observations: parent text about the opponent; feeds the
--   auto-player-note loop in services/post_match_sync.py. Stored raw;
--   sanitised only at LLM-input time via services/scouting.py.
--
-- user_id: denormalised for direct RLS check (avoids join on every row read).
--   Redundant with match→tournament→user_id chain, but faster.
--
-- cascade chain:
--   public.users DELETE → public.matches DELETE (via tournaments) → this CASCADE
--   Separately: match DELETE → match_evaluation CASCADE
-- ---------------------------------------------------------------------------
create table if not exists public.match_evaluations (
  id                      uuid primary key default gen_random_uuid(),
  match_id                uuid not null unique references public.matches (id)
                            on delete cascade,
  user_id                 uuid not null references public.users (id)
                            on delete cascade,
  result                  match_eval_result not null,
  score_text              text check (char_length(score_text) <= 80),
  effort_rating           smallint check (effort_rating between 1 and 5),
  focus_rating            smallint check (focus_rating between 1 and 5),
  went_well               text[] not null default array[]::text[],
  to_improve              text[] not null default array[]::text[],
  opponent_observations   text check (char_length(opponent_observations) <= 500),
  key_moments             text check (char_length(key_moments) <= 500),
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

comment on table public.match_evaluations is
  'Per-match structured post-match write-up. One row per match (UNIQUE on match_id). '
  'See POST_MATCH_EVAL_V1.md.';

comment on column public.match_evaluations.opponent_observations is
  'Parent observations about the opponent; ≤500 chars. '
  'Auto-synced to player_notes with source=post_match when opponent_player_id is set on match. '
  'Stored raw; sanitised before LLM use via services/scouting.py. See POST_MATCH_EVAL_V1.md §D.';

comment on column public.match_evaluations.went_well is
  'Free-text bullet list of positives; up to 5 items (enforced at API layer). '
  'Individual item limit: 200 chars (enforced at API layer via Pydantic @field_validator).';

comment on column public.match_evaluations.to_improve is
  'Free-text growth-areas list; up to 5 items (enforced at API layer). '
  'Labelled "What to Improve" in UI — constructive framing for young athletes.';

create index if not exists match_evaluations_match_id_idx on public.match_evaluations (match_id);
create index if not exists match_evaluations_user_id_idx  on public.match_evaluations (user_id);

drop trigger if exists set_match_evaluations_updated_at on public.match_evaluations;
create trigger set_match_evaluations_updated_at
  before update on public.match_evaluations
  for each row execute function set_updated_at();


-- ===========================================================================
-- RLS: match_evaluations
-- ===========================================================================
-- SELECT / UPDATE / DELETE: simple user_id predicate (denormalised on the row).
-- INSERT / UPDATE: ADDITIONALLY chain-check through match → tournament to
--   prevent cross-user match_id injection (a parent cannot evaluate a match
--   they do not own even if they know the match UUID).
-- Pattern mirrors match_scenarios two-hop RLS from 0003_rls.sql.
-- ===========================================================================
alter table public.match_evaluations enable row level security;

create policy "match_evaluations_select_own"
  on public.match_evaluations
  for select
  using ((select auth.uid()) = user_id);

create policy "match_evaluations_insert_own"
  on public.match_evaluations
  for insert
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1 from public.matches m
      join public.tournaments t on m.tournament_id = t.id
      where m.id = match_evaluations.match_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "match_evaluations_update_own"
  on public.match_evaluations
  for update
  using  ((select auth.uid()) = user_id)
  with check (
    (select auth.uid()) = user_id
    and exists (
      select 1 from public.matches m
      join public.tournaments t on m.tournament_id = t.id
      where m.id = match_evaluations.match_id
        and t.user_id = (select auth.uid())
    )
  );

create policy "match_evaluations_delete_own"
  on public.match_evaluations
  for delete
  using ((select auth.uid()) = user_id);
