-- =============================================================================
-- PlayFuel Migration 0012: tournament_location
-- =============================================================================
-- Purpose:
--   1. Add venue_place_id to tournaments (nullable; stable place ID from
--      Google Places or other provider; MapKit results carry none).
--   2. Add CHECK constraint enforcing coordinates come as a pair (both NULL
--      or both NOT NULL).
--   3. Add tournament_places_cache table for food-rec result caching.
--      Cache keyed by (tournament_id, place_type) with a fetched_at timestamp.
--      TTL is enforced at the Python layer (PLACES_CACHE_TTL_SEC = 86400 / 24h).
--      Rationale: 24h is long enough to avoid redundant API calls for repeated
--      plan regeneration on the same tournament day, while staying fresh enough
--      that new nearby restaurants appear within a day.
--
-- Prerequisites: 0011_match_evaluations.sql
-- All additions nullable / backward-compatible — zero row-level impact on
-- existing tournaments.
-- =============================================================================

-- Part 1: venue_place_id ---------------------------------------------------
ALTER TABLE public.tournaments
  ADD COLUMN IF NOT EXISTS venue_place_id TEXT;

-- Part 2: coords-as-pair constraint ----------------------------------------
-- Existing rows with (venue_lat IS NULL AND venue_lng IS NULL) satisfy this.
-- Existing rows with both set (e.g. Dallas demo) also satisfy this.
ALTER TABLE public.tournaments
  ADD CONSTRAINT tournaments_coords_pair CHECK (
    (venue_lat IS NULL AND venue_lng IS NULL)
    OR (venue_lat IS NOT NULL AND venue_lng IS NOT NULL)
  );

-- Part 3: tournament_places_cache ------------------------------------------
-- Caches serialised list[RawPlace] (JSONB) per (tournament_id, place_type).
-- The unique constraint on (tournament_id, place_type) enables upsert.
-- ON DELETE CASCADE ensures cache rows are cleaned up when a tournament is
-- deleted (follows the pattern of all other FK tables).
CREATE TABLE IF NOT EXISTS public.tournament_places_cache (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tournament_id  UUID        NOT NULL
                               REFERENCES public.tournaments(id) ON DELETE CASCADE,
  place_type     TEXT        NOT NULL,   -- 'food' (extensible for future types)
  payload        JSONB       NOT NULL,   -- serialised list[RawPlace] from provider
  fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tournament_id, place_type)
);

COMMENT ON COLUMN public.tournament_places_cache.payload IS
  'Serialised list[RawPlace] JSONB. Schema: [{name, types, distance_meters, '
  'drive_time_minutes, place_id, provider, lat, lng}, ...]. '
  'TTL enforced at API layer (PLACES_CACHE_TTL_SEC=86400).';

CREATE INDEX IF NOT EXISTS idx_tournament_places_cache_tournament_id
  ON public.tournament_places_cache(tournament_id);

-- updated_at trigger (matches pattern of every other table in this schema)
CREATE TRIGGER set_updated_at_tournament_places_cache
  BEFORE UPDATE ON public.tournament_places_cache
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Part 4: RLS for tournament_places_cache ----------------------------------
-- Users access their own tournament's cache only (ownership verified via
-- tournaments.user_id = auth.uid()).
-- Service role bypasses RLS entirely (used by the API for cache reads/writes).
-- Direct SELECT/INSERT from anon or authenticated roles without ownership is
-- denied.
ALTER TABLE public.tournament_places_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "owner_select_places_cache"
  ON public.tournament_places_cache FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.tournaments t
       WHERE t.id = tournament_id
         AND t.user_id = (SELECT auth.uid())
    )
  );

CREATE POLICY "owner_insert_places_cache"
  ON public.tournament_places_cache FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.tournaments t
       WHERE t.id = tournament_id
         AND t.user_id = (SELECT auth.uid())
    )
  );

CREATE POLICY "owner_update_places_cache"
  ON public.tournament_places_cache FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM public.tournaments t
       WHERE t.id = tournament_id
         AND t.user_id = (SELECT auth.uid())
    )
  );

CREATE POLICY "owner_delete_places_cache"
  ON public.tournament_places_cache FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM public.tournaments t
       WHERE t.id = tournament_id
         AND t.user_id = (SELECT auth.uid())
    )
  );
