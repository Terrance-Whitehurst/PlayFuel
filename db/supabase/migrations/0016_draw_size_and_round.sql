-- 0016_draw_size_and_round.sql
-- Adds tournament draw size and numeric match round.
--
-- draw_size: 32 | 64 | 128 | 256 — determines the bracket depth and
--   which round values are valid for child matches.
-- round: number of players still alive at this stage (32=R32, 16=R16,
--   8=QF, 4=SF, 2=Final). NOT a round number; NOT a display string.
--
-- NOT NULL DEFAULT chosen over nullable:
--   draw_size DEFAULT 32 — R32 is the most common junior draw.
--   round     DEFAULT 32 — earliest round in R32; reasonable placeholder
--   for existing test data rows. Document that pre-migration rows are
--   placeholder values, not real user-entered data.
--
-- Cross-table CHECK (round <= draw_size) is NOT enforced in DB — it
-- requires a subquery joining matches → tournaments. Enforced in API
-- layer only (routes/matches.py create_match handler).
--
-- Prerequisites: 0015_llm_explanation_cache.sql
-- Idempotent: IF NOT EXISTS guards against re-runs.

ALTER TABLE public.tournaments
  ADD COLUMN IF NOT EXISTS draw_size smallint NOT NULL DEFAULT 32
    CONSTRAINT chk_draw_size CHECK (draw_size IN (32, 64, 128, 256));

ALTER TABLE public.matches
  ADD COLUMN IF NOT EXISTS round smallint NOT NULL DEFAULT 32
    CONSTRAINT chk_round CHECK (round IN (2, 4, 8, 16, 32, 64, 128, 256));

COMMENT ON COLUMN public.tournaments.draw_size IS
  'Bracket size: 32 | 64 | 128 | 256. See draw-size-spec.md §2.';

COMMENT ON COLUMN public.matches.round IS
  'Players still alive: 32=R32, 16=R16, 8=QF, 4=SF, 2=Final. Must be <= parent tournament.draw_size. Enforced in API.';
