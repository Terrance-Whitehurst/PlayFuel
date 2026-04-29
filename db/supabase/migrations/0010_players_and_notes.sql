-- =============================================================================
-- PlayFuel Migration 0010: Players and Player Notes (Scouting)
-- =============================================================================
-- Prerequisites: 0001–0009 must be applied first.
-- Idempotent: all statements use IF NOT EXISTS / DO $$ guards.
--
-- Creates:
--   public.players         — parent's roster of tracked opponents
--   public.player_notes    — append-only per-parent observation log
--   player_note_source     — enum for note provenance
-- Alters:
--   public.matches         — adds opponent_player_id FK (nullable)
-- RLS:
--   8 new policies (4 per new table) + ALTER TABLE enable RLS for both
--
-- Privacy: see PLAYER_SCOUTING_V1.md §A (data minimisation — no contact columns).
-- FK target: public.users(id) — mirrors player_profiles, tournaments pattern.
--   (public.users is the shadow table; NOT auth.users directly.)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Enum: player_note_source
-- Values: secondhand, observed, post_match
-- Verified no collision with enums in 0001_extensions_and_enums.sql:
--   scenario_kind, gap_status, schedule_confidence, food_bucket,
--   pickup_bucket, weather_condition — none clash.
-- ---------------------------------------------------------------------------
do $$ begin
  create type player_note_source as enum ('secondhand', 'observed', 'post_match');
exception when duplicate_object then null;
end $$;


-- ===========================================================================
-- TABLE: players
-- ===========================================================================
-- Parent's roster of opponent players they have tracked or will track.
-- Data minimisation: NO email, phone, photo, home address, or physical
-- description columns — see PLAYER_SCOUTING_V1.md §A.1.
-- updated_at bumped by set_updated_at() trigger (same function as 0002).
-- FK: public.users(id) — mirrors player_profiles, tournaments pattern.
-- ---------------------------------------------------------------------------
create table if not exists public.players (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references public.users (id)
                    on delete cascade,
  display_name    text not null,
  club            text,
  city            text,
  notes_summary   text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

comment on column public.players.notes_summary is
  'Parent-curated 1-line headline for this player. Persisted (not derived) in v1.';

create index if not exists players_user_id_idx on public.players (user_id);

drop trigger if exists set_players_updated_at on public.players;
create trigger set_players_updated_at
  before update on public.players
  for each row execute function set_updated_at();


-- ===========================================================================
-- TABLE: player_notes
-- ===========================================================================
-- Append-only log of observations about an opponent player.
-- source enum: 'secondhand' (heard from others), 'observed' (during a match),
--              'post_match' (reflection after playing them).
-- body capped at 2000 chars via CHECK constraint.
-- match_id nullable FK — links the note to a specific match when known;
--   ON DELETE SET NULL so the note survives match deletion.
-- user_id denormalised for direct RLS checks (avoids join).
-- No updated_at — notes are immutable after creation.
-- ---------------------------------------------------------------------------
create table if not exists public.player_notes (
  id          uuid primary key default gen_random_uuid(),
  player_id   uuid not null references public.players (id)
                on delete cascade,
  user_id     uuid not null references public.users (id)
                on delete cascade,
  source      player_note_source not null,
  body        text not null check (char_length(body) <= 2000),
  match_id    uuid references public.matches (id)
                on delete set null,
  created_at  timestamptz not null default now()
);

comment on column public.player_notes.source is
  'Provenance: secondhand = heard from others; observed = watched during match; '
  'post_match = after playing them.';

create index if not exists player_notes_player_id_idx on public.player_notes (player_id);
create index if not exists player_notes_user_id_idx   on public.player_notes (user_id);


-- ===========================================================================
-- TABLE: matches (additive ALTER)
-- ===========================================================================
-- Adds opponent_player_id FK referencing the new players table.
-- Nullable; backward-compat. Existing opponent_label text column stays.
-- ON DELETE SET NULL: if the scouted player is deleted, the match record
--   retains its opponent_label text but loses the player FK link.
-- ---------------------------------------------------------------------------
alter table public.matches
  add column if not exists opponent_player_id uuid
    references public.players (id) on delete set null;

comment on column public.matches.opponent_player_id is
  'Optional FK to players.id — links this match to a scouted opponent. '
  'SET NULL on player delete. Complements opponent_label (text). '
  'See PLAYER_SCOUTING_V1.md §B.';


-- ===========================================================================
-- RLS: players
-- Ownership predicate: (select auth.uid()) = user_id
-- Mirrors player_profiles policies from 0003_rls.sql exactly.
-- ===========================================================================
alter table public.players enable row level security;

create policy "players_select_own"
  on public.players
  for select
  using ((select auth.uid()) = user_id);

create policy "players_insert_own"
  on public.players
  for insert
  with check ((select auth.uid()) = user_id);

create policy "players_update_own"
  on public.players
  for update
  using  ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "players_delete_own"
  on public.players
  for delete
  using ((select auth.uid()) = user_id);


-- ===========================================================================
-- RLS: player_notes
-- Ownership predicate: EXISTS through players table.
-- Mirrors matches one-hop pattern from 0003_rls.sql.
-- ===========================================================================
alter table public.player_notes enable row level security;

create policy "player_notes_select_own"
  on public.player_notes
  for select
  using (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  );

create policy "player_notes_insert_own"
  on public.player_notes
  for insert
  with check (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  );

create policy "player_notes_update_own"
  on public.player_notes
  for update
  using (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  );

create policy "player_notes_delete_own"
  on public.player_notes
  for delete
  using (
    exists (
      select 1 from public.players p
      where p.id = player_notes.player_id
        and p.user_id = (select auth.uid())
    )
  );
