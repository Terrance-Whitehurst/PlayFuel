-- =============================================================================
-- PlayFuel Migration 0014: tighten_places_cache_rls
-- =============================================================================
-- Purpose:
--   Replace the ownership-scoped RLS policies on tournament_places_cache with
--   deny-all policies for authenticated + anon roles.
--
-- Rationale (SP-3, Places PR validation):
--   tournament_places_cache is an internal API cache layer — clients never need
--   direct PostgREST access to it.  Users see food recommendations through
--   POST /v1/plans/generate; the cache is an implementation detail.
--
--   The original migration 0012 shipped with ownership-scoped policies that
--   allowed authenticated users to SELECT their own tournament's cache rows.
--   This was flagged as a spec deviation: service-role-only is the correct
--   posture for a cache table.
--
--   With deny-all on authenticated + anon, only the FastAPI process (which uses
--   the service role key, which bypasses RLS entirely) can read/write the cache.
--   No functional change to the app — the API already uses service-role.
--
-- Prerequisites: 0013_feedback_schema_v2.sql
-- Zero data-loss: no rows are deleted; only policy definitions change.
-- =============================================================================

-- Step 1: Drop the 4 existing ownership-scoped policies -------------------
DROP POLICY IF EXISTS "owner_select_places_cache"
  ON public.tournament_places_cache;

DROP POLICY IF EXISTS "owner_insert_places_cache"
  ON public.tournament_places_cache;

DROP POLICY IF EXISTS "owner_update_places_cache"
  ON public.tournament_places_cache;

DROP POLICY IF EXISTS "owner_delete_places_cache"
  ON public.tournament_places_cache;

-- Step 2: Add deny-all policies for authenticated + anon roles ------------
-- USING (false) / WITH CHECK (false) short-circuits every row evaluation.
-- Service role bypasses RLS entirely, so the API continues to work.

CREATE POLICY "deny_authenticated_select_places_cache"
  ON public.tournament_places_cache FOR SELECT
  TO authenticated
  USING (false);

CREATE POLICY "deny_authenticated_insert_places_cache"
  ON public.tournament_places_cache FOR INSERT
  TO authenticated
  WITH CHECK (false);

CREATE POLICY "deny_authenticated_update_places_cache"
  ON public.tournament_places_cache FOR UPDATE
  TO authenticated
  USING (false)
  WITH CHECK (false);

CREATE POLICY "deny_authenticated_delete_places_cache"
  ON public.tournament_places_cache FOR DELETE
  TO authenticated
  USING (false);

-- Anon role also denied (belt-and-suspenders; anon shouldn't reach this table).
CREATE POLICY "deny_anon_select_places_cache"
  ON public.tournament_places_cache FOR SELECT
  TO anon
  USING (false);

CREATE POLICY "deny_anon_insert_places_cache"
  ON public.tournament_places_cache FOR INSERT
  TO anon
  WITH CHECK (false);

CREATE POLICY "deny_anon_update_places_cache"
  ON public.tournament_places_cache FOR UPDATE
  TO anon
  USING (false)
  WITH CHECK (false);

CREATE POLICY "deny_anon_delete_places_cache"
  ON public.tournament_places_cache FOR DELETE
  TO anon
  USING (false);

-- =============================================================================
-- Post-migration verification (for review / manual smoke):
--   After applying, an authenticated user's direct PostgREST SELECT on
--   tournament_places_cache should return 0 rows or a 403, even when their
--   tournament has cached entries.
--   The API's service-role Supabase client bypasses RLS and continues to work.
-- =============================================================================
