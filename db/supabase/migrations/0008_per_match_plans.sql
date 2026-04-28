-- 0008_per_match_plans.sql
-- Adds match_id FK to plans so each plan can be anchored to a specific match.
-- Also adds a unique partial index to enforce one plan per (match_id, match_type) pair.
-- See NUTRITION_FIRST_IA_V1.md §E and §H.1.
--
-- PM VERIFICATION NOTE (2026-04-27):
--   plans.match_id did NOT exist before this migration — verified by reading
--   0002_tables.sql before scribing. This migration MUST ADD THE COLUMN first,
--   then create the index. An index-only migration would fail.
--
-- plans.match_type was added as nullable text in 0007_doubles_support.sql.
-- It is still nullable; null = legacy row = treat as 'singles'.
-- The unique index uses WHERE to exclude null match_ids (legacy / pre-0008 rows).

ALTER TABLE public.plans
  ADD COLUMN IF NOT EXISTS match_id uuid
    REFERENCES public.matches (id) ON DELETE CASCADE;

COMMENT ON COLUMN public.plans.match_id IS
  'FK to the specific match this plan was generated for. '
  'NULL on legacy rows (pre-0008, generated per-tournament not per-match). '
  'See NUTRITION_FIRST_IA_V1.md §E.';

-- One plan per (match, match_type). WHERE excludes legacy null-match_id rows
-- so the index does not reject the old tournament-level plan rows.
CREATE UNIQUE INDEX IF NOT EXISTS plans_match_id_match_type_uq
  ON public.plans (match_id, match_type)
  WHERE match_id IS NOT NULL;
