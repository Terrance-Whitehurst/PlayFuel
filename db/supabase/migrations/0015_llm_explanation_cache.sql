-- =============================================================================
-- PlayFuel Migration 0015: llm_explanation_cache
-- =============================================================================
-- Purpose:
--   Create the llm_explanation_cache table used by Opt-B in the perf PR.
--   routes/plans.py references this table via _LLM_CACHE_TABLE = "llm_explanation_cache".
--   Without this table, cache writes silently fail (swallowed in try/except) and
--   reads always miss — functionally harmless but wastes LLM API calls.
--
-- Rationale:
--   Plan generation calls the Anthropic API for each match (~1–2 s per call).
--   Most re-generations for the same tournament + match inputs are identical:
--   same venue, same schedule, same weather band, same food categories.
--   A 7-day TTL cache keyed on SHA-256(PII-stripped PlanExplanationInput) captures
--   the majority of re-generations at near-zero cost.
--
--   Cache key design:
--     SHA-256(json.dumps(exp_input.model_dump(exclude={"opponent_notes"}), sort_keys=True))
--     Opponent notes explicitly excluded (SEC-P6-2: PII must not enter cache key).
--     Two plans for the same tournament+schedule+weather will share a cache entry.
--
-- RLS posture (matches 0014 for tournament_places_cache — SP-3 pattern):
--   Deny-all for authenticated + anon roles.
--   Only the FastAPI process (service-role key, bypasses RLS) reads/writes.
--   Users never need direct PostgREST access to this table.
--
-- Prerequisites: 0014_tighten_places_cache_rls.sql
-- Zero data-loss: new table creation only.
-- =============================================================================

-- Step 1: Create the table ---------------------------------------------------
CREATE TABLE IF NOT EXISTS public.llm_explanation_cache (
    -- Surrogate key is the SHA-256 hex digest of the PII-stripped plan input.
    cache_key   text        PRIMARY KEY,

    -- Full PlanExplanation JSON (camelCase, matching PlanExplanation.model_dump(by_alias=True)).
    response_json jsonb     NOT NULL,

    -- Which model/provider generated this entry (for observability + invalidation).
    model       text,

    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);

COMMENT ON TABLE public.llm_explanation_cache IS
  'LLM explanation cache keyed on SHA-256(PII-stripped PlanExplanationInput). '
  'TTL 7 days. Service-role only (deny-all RLS for authenticated + anon). '
  'See routes/plans.py _LLM_CACHE_TABLE, Opt-B perf optimisation.';

COMMENT ON COLUMN public.llm_explanation_cache.cache_key IS
  'SHA-256 hex digest of PlanExplanationInput serialised without opponent_notes '
  '(SEC-P6-2: PII must not contribute to a shared cache key). '
  'Computed by routes/plans._llm_cache_key().';

COMMENT ON COLUMN public.llm_explanation_cache.response_json IS
  'PlanExplanation JSON (camelCase). Deserialised via PlanExplanation.model_validate().';

COMMENT ON COLUMN public.llm_explanation_cache.expires_at IS
  'UTC expiry timestamp (created_at + 7 days by default). '
  'Rows past this time are treated as cache-miss by _read_llm_cache() '
  'and eventually replaced by the next successful LLM call.';

-- Step 2: Index on expires_at for efficient TTL sweeps -----------------------
CREATE INDEX IF NOT EXISTS llm_explanation_cache_expires_at_idx
    ON public.llm_explanation_cache (expires_at);

-- Step 3: Enable RLS ---------------------------------------------------------
ALTER TABLE public.llm_explanation_cache ENABLE ROW LEVEL SECURITY;

-- Step 4: Deny-all policies for authenticated + anon roles -------------------
-- USING (false) / WITH CHECK (false) short-circuits all row evaluation.
-- Service role bypasses RLS entirely, so the FastAPI process continues to work.

-- authenticated role
CREATE POLICY "deny_authenticated_select_llm_cache"
    ON public.llm_explanation_cache FOR SELECT
    TO authenticated
    USING (false);

CREATE POLICY "deny_authenticated_insert_llm_cache"
    ON public.llm_explanation_cache FOR INSERT
    TO authenticated
    WITH CHECK (false);

CREATE POLICY "deny_authenticated_update_llm_cache"
    ON public.llm_explanation_cache FOR UPDATE
    TO authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY "deny_authenticated_delete_llm_cache"
    ON public.llm_explanation_cache FOR DELETE
    TO authenticated
    USING (false);

-- anon role (belt-and-suspenders)
CREATE POLICY "deny_anon_select_llm_cache"
    ON public.llm_explanation_cache FOR SELECT
    TO anon
    USING (false);

CREATE POLICY "deny_anon_insert_llm_cache"
    ON public.llm_explanation_cache FOR INSERT
    TO anon
    WITH CHECK (false);

CREATE POLICY "deny_anon_update_llm_cache"
    ON public.llm_explanation_cache FOR UPDATE
    TO anon
    USING (false)
    WITH CHECK (false);

CREATE POLICY "deny_anon_delete_llm_cache"
    ON public.llm_explanation_cache FOR DELETE
    TO anon
    USING (false);

-- =============================================================================
-- Post-migration verification (for review / manual smoke):
--   \d public.llm_explanation_cache   -- should show 5 columns + index
--   SELECT * FROM pg_policies WHERE tablename = 'llm_explanation_cache';
--     -- should show 8 deny-all policies (4 authenticated + 4 anon)
--
--   As an authenticated user via PostgREST:
--     SELECT * FROM llm_explanation_cache;
--     -- should return 0 rows (policy USING(false) filters everything)
--
--   Via service role:
--     INSERT INTO llm_explanation_cache (cache_key, response_json, expires_at)
--     VALUES ('test', '{}', now() + interval '7 days');
--     -- should succeed (service role bypasses RLS)
-- =============================================================================
