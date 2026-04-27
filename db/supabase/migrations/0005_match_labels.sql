-- 0005_match_labels.sql
-- Adds optional human-readable labels for match round, opponent, and court.
-- Resolves OQ-API-1(a). All columns nullable; no backfill required.
--
-- Applied after 0004_auth_trigger.sql.
-- Idempotent: ADD COLUMN IF NOT EXISTS guards against re-runs.

ALTER TABLE public.matches
  ADD COLUMN IF NOT EXISTS round_label    text,
  ADD COLUMN IF NOT EXISTS opponent_label text,
  ADD COLUMN IF NOT EXISTS court_label    text;

COMMENT ON COLUMN public.matches.round_label    IS 'Human-readable round label, e.g. "QF", "R16". Nullable.';
COMMENT ON COLUMN public.matches.opponent_label IS 'Human-readable opponent display name. Nullable.';
COMMENT ON COLUMN public.matches.court_label    IS 'Human-readable court designation, e.g. "Court 7". Nullable.';
