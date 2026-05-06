-- Phase C-infrastructure: persist user-selected language preference end-to-end.
-- Enables server-side LLM system-prompt selection per INTERNATIONAL_SCOPE_V1.md §L.
-- Tier-1 values enforced at the API boundary via Pydantic Literal["en","es"];
-- no DB-level CHECK constraint required (API is the gate).

ALTER TABLE public.tournaments
    ADD COLUMN IF NOT EXISTS preferred_language text;

COMMENT ON COLUMN public.tournaments.preferred_language IS
    'ISO 639-1 language code for LLM plan explanations. '
    'Tier-1 allowlist: ''en'' (English, default) and ''es'' (Spanish). '
    'NULL = English default. Validated to Pydantic Literal["en","es"] at API boundary '
    '(INTL-SEC-5: never interpolated into LLM prompt — used as a dict key only). '
    'Phase C-translations delivers the ''es'' system prompt via Planning vendor.';
