-- 0009_plans_upsert_constraint.sql
-- The OQ-IA-9 hotfix changed routes/plans.py to upsert with
-- on_conflict='match_id,match_type'. Postgres rejects that against the
-- partial unique index from 0008 (WHERE match_id IS NOT NULL) — ON CONFLICT
-- requires a non-partial unique constraint or index.
--
-- This migration drops the partial index and replaces it with a plain unique
-- index on the same columns. Postgres treats NULLs as distinct in unique
-- indexes by default, so multiple legacy rows with NULL match_id still
-- coexist — same semantics as the partial index, just satisfies ON CONFLICT.

DROP INDEX IF EXISTS public.plans_match_id_match_type_uq;

CREATE UNIQUE INDEX IF NOT EXISTS plans_match_id_match_type_uq
  ON public.plans (match_id, match_type);
