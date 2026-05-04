-- =============================================================================
-- PlayFuel Migration 0017: Add is_done + done_at to matches
-- =============================================================================
-- Adds parent-visible match completion toggle to the matches table.
-- is_done is the user-facing toggle (parent marks a match done).
-- done_at records when is_done was first set to true (audit/sort only).
-- actual_end_at (existing) is preserved for future analytics (when the match
-- physically ended, not when the parent tapped "done").
-- Spec: specs/match-done-state-cards.md §C
-- =============================================================================

alter table public.matches
  add column if not exists is_done   boolean     not null default false,
  add column if not exists done_at   timestamptz null;

comment on column public.matches.is_done is
  'Parent-visible completion toggle. True when the parent has marked this match done. '
  'Does not correspond to actual match end time — see actual_end_at for that.';

comment on column public.matches.done_at is
  'Timestamp when is_done was first set to true. Cleared when is_done is set back to false. '
  'Nullable — null when is_done is false.';
