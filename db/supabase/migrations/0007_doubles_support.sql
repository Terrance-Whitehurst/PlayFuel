-- 0007_doubles_support.sql
-- Adds doubles format support to matches and match_type column to plans.
--
-- IMPORTANT: matches.format (added in 0002_tables.sql) is ALREADY used as match type
-- ('singles' | 'doubles'). Do NOT add a redundant match_type column to matches.
-- See DOUBLES_SPEC_V1.md §A.2 (OQ-DBL-3) for resolution rationale.
--
-- Both statements are idempotent (IF NOT EXISTS / DEFAULT).

ALTER TABLE public.matches
  ADD COLUMN IF NOT EXISTS doubles_format text;
COMMENT ON COLUMN public.matches.doubles_format IS
  'Doubles match format. NULL when format != ''doubles''. '
  'Valid values: ''best_of_3'', ''pro_set_8''. See DOUBLES_SPEC_V1.md §A.';

ALTER TABLE public.plans
  ADD COLUMN IF NOT EXISTS match_type text;
COMMENT ON COLUMN public.plans.match_type IS
  'Match type this plan was generated for. NULL = legacy row (treat as ''singles''). '
  'Valid values: ''singles'', ''doubles''. See DOUBLES_SPEC_V1.md §D.3.';
