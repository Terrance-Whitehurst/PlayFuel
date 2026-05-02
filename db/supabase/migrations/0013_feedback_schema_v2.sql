-- =============================================================================
-- PlayFuel Migration 0013: Feedback Schema v2 (Phase 7)
-- =============================================================================
-- Prerequisites: 0001–0012 must be applied first.
-- Idempotent: all column additions use IF NOT EXISTS; constraint/policy drops
--             use IF EXISTS.
--
-- What this migration does:
--   1. Safety guard — aborts if the table has rows (production safeguard;
--      the table is expected to be empty at migration time).
--   2. Drops old columns (what_worked text, what_didnt text, rating int)
--      that were placeholders in 0002_tables.sql.
--   3. Makes plan_id nullable (per 0002 comment: "revisit in Phase 7") and
--      changes ON DELETE to SET NULL so feedback survives plan deletion.
--   4. Adds new FK columns: tournament_id + user_id.
--   5. Adds new payload columns: overall_rating smallint, what_worked text[],
--      what_didnt_work text[], free_text text, updated_at.
--   6. Adds UNIQUE(tournament_id, user_id) — one row per parent per tournament;
--      enables UPSERT semantics (second POST updates, not inserts).
--   7. Drops old two-hop RLS policies from 0003_rls.sql.
--   8. Creates new direct user_id RLS policies (mirrors match_evaluations pattern).
--   9. Creates supporting indexes.
--
-- Cascade summary after this migration:
--   public.users DELETE       → feedback (user_id CASCADE)
--   public.tournaments DELETE → feedback (tournament_id CASCADE)
--   public.plans DELETE       → feedback.plan_id SET NULL (feedback row survives)
--
-- See: phase7-feedback-spec.md §B.2 for full column-shape reference.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Step 0: Safety guard — do not run if feedback table has existing rows.
--   In pre-production the table should be empty. If rows exist, something
--   unexpected has happened (data was written before Phase 7 code shipped);
--   abort rather than silently destroying production data.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.feedback LIMIT 1) THEN
    RAISE EXCEPTION
      'Migration 0013 aborted: public.feedback has existing rows. '
      'Inspect and truncate the table manually before re-running.';
  END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Step 1: Drop old placeholder columns (all NULL-able / no constraint deps)
-- ---------------------------------------------------------------------------
ALTER TABLE public.feedback
  DROP COLUMN IF EXISTS what_worked,
  DROP COLUMN IF EXISTS what_didnt,
  DROP COLUMN IF EXISTS rating;

-- ---------------------------------------------------------------------------
-- Step 2: Make plan_id nullable (Phase 7 note in 0002_tables.sql)
--   Drop the existing NOT NULL + CASCADE FK, re-add as nullable + SET NULL.
--   Feedback should survive plan deletion — user feedback is about the
--   tournament experience, not the plan itself.
-- ---------------------------------------------------------------------------
ALTER TABLE public.feedback
  DROP CONSTRAINT IF EXISTS feedback_plan_id_fkey;

ALTER TABLE public.feedback
  ALTER COLUMN plan_id DROP NOT NULL;

ALTER TABLE public.feedback
  ADD CONSTRAINT feedback_plan_id_fkey
    FOREIGN KEY (plan_id)
    REFERENCES public.plans (id)
    ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- Step 3: Add new FK columns (tournament_id, user_id)
--   Added nullable first so the statement succeeds on a table without rows,
--   then set NOT NULL after (belt-and-suspenders).
-- ---------------------------------------------------------------------------
ALTER TABLE public.feedback
  ADD COLUMN IF NOT EXISTS tournament_id uuid
    REFERENCES public.tournaments (id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS user_id uuid
    REFERENCES public.users (id) ON DELETE CASCADE;

-- Enforce NOT NULL (safe — table is guaranteed empty by the Step 0 guard)
ALTER TABLE public.feedback
  ALTER COLUMN tournament_id SET NOT NULL,
  ALTER COLUMN user_id       SET NOT NULL;

-- ---------------------------------------------------------------------------
-- Step 4: Add new payload columns
-- ---------------------------------------------------------------------------
ALTER TABLE public.feedback
  ADD COLUMN IF NOT EXISTS overall_rating smallint
    CHECK (overall_rating BETWEEN 1 AND 5),
  ADD COLUMN IF NOT EXISTS what_worked    text[]  NOT NULL DEFAULT ARRAY[]::text[],
  ADD COLUMN IF NOT EXISTS what_didnt_work text[] NOT NULL DEFAULT ARRAY[]::text[],
  ADD COLUMN IF NOT EXISTS free_text      text
    CHECK (char_length(free_text) <= 500);

-- updated_at is already present from 0002_tables.sql (set_updated_at trigger).
-- No change needed.

-- ---------------------------------------------------------------------------
-- Step 5: UNIQUE constraint — one feedback row per (parent × tournament)
--   Enables ON CONFLICT (tournament_id, user_id) DO UPDATE upsert semantics.
--   Second POST → UPDATE + 200; first POST → INSERT + 201.
-- ---------------------------------------------------------------------------
ALTER TABLE public.feedback
  ADD CONSTRAINT feedback_tournament_user_uq
    UNIQUE (tournament_id, user_id);

-- ---------------------------------------------------------------------------
-- Step 6: Drop old two-hop RLS policies from 0003_rls.sql
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "feedback_select_own" ON public.feedback;
DROP POLICY IF EXISTS "feedback_insert_own" ON public.feedback;
DROP POLICY IF EXISTS "feedback_update_own" ON public.feedback;
DROP POLICY IF EXISTS "feedback_delete_own" ON public.feedback;

-- ---------------------------------------------------------------------------
-- Step 7: New direct user_id RLS policies (mirrors match_evaluations pattern)
--   Direct auth.uid() = user_id check is faster than the old two-hop join and
--   consistent with every other table added since migration 0010.
-- ---------------------------------------------------------------------------

-- SELECT: own rows only
CREATE POLICY "feedback_select_own"
  ON public.feedback
  FOR SELECT
  USING ((SELECT auth.uid()) = user_id);

-- INSERT: caller must own the target tournament
CREATE POLICY "feedback_insert_own"
  ON public.feedback
  FOR INSERT
  WITH CHECK (
    (SELECT auth.uid()) = user_id
    AND EXISTS (
      SELECT 1 FROM public.tournaments t
      WHERE t.id = feedback.tournament_id
        AND t.user_id = (SELECT auth.uid())
    )
  );

-- UPDATE: own rows only + tournament ownership re-check
CREATE POLICY "feedback_update_own"
  ON public.feedback
  FOR UPDATE
  USING  ((SELECT auth.uid()) = user_id)
  WITH CHECK (
    (SELECT auth.uid()) = user_id
    AND EXISTS (
      SELECT 1 FROM public.tournaments t
      WHERE t.id = feedback.tournament_id
        AND t.user_id = (SELECT auth.uid())
    )
  );

-- DELETE: own rows only
CREATE POLICY "feedback_delete_own"
  ON public.feedback
  FOR DELETE
  USING ((SELECT auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- Step 8: Supporting indexes
--   idx_feedback_plan_id already exists from 0002_tables.sql — keep it.
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS feedback_tournament_id_idx ON public.feedback (tournament_id);
CREATE INDEX IF NOT EXISTS feedback_user_id_idx       ON public.feedback (user_id);

-- ---------------------------------------------------------------------------
-- Step 9: Comments
-- ---------------------------------------------------------------------------
COMMENT ON TABLE public.feedback IS
  'Post-tournament plan feedback. One row per (parent × tournament). '
  'UPSERT on (tournament_id, user_id) UNIQUE constraint: first POST → 201, '
  'second POST → 200. plan_id is nullable: references the plan active at '
  'submission time; survives plan deletion (ON DELETE SET NULL). '
  'See phase7-feedback-spec.md §B.';

COMMENT ON COLUMN public.feedback.what_worked IS
  'Chip tokens from FEEDBACK_CHIPS_WORKED vocab (rules/feedback.py). '
  'API enforces vocab membership and max 7 items per field. '
  'Token semantics: "what aspect of the plan worked well."';

COMMENT ON COLUMN public.feedback.what_didnt_work IS
  'Chip tokens from FEEDBACK_CHIPS_DIDNT_WORK vocab (rules/feedback.py). '
  'Same token set — context (helped / did not help) conveyed by which array. '
  'API enforces vocab membership and max 7 items per field.';

COMMENT ON COLUMN public.feedback.free_text IS
  'Optional parent free-text comment. ≤500 chars. '
  'Not fed into LLM or plan generation in Phase 7 '
  '(preference loop deferred to Phase 8+).';
