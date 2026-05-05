-- =============================================================================
-- PlayFuel Migration 0021: Tournament Accommodations
-- =============================================================================
-- Purpose: Add optional accommodation location to tournaments table.
--   accommodation_lat / accommodation_lng: haversine drive-time source.
--   accommodation_address: human-readable display string.
--   accommodation_kind: copy-variation hint ('home' | 'hotel').
--
-- All four columns are nullable. No NOT NULL, no DEFAULT.
-- Existing rows get NULL across all four columns — zero row-level impact.
-- Column types mirror venue_lat/venue_lng (numeric(9, 6)) per 0002_tables.sql.
--
-- Coord-pair constraint mirrors 0012_tournament_location.sql pattern:
--   both NULL (no accommodation) or both NOT NULL (accommodation set).
--
-- accommodation_kind is nullable independently of coords — a NULL kind
--   defaults to 'home' in copy layer (see ACCOMMODATIONS_V1.md §G). No DB-level DEFAULT.
--
-- Prerequisites: 0020_tournament_preferred_language.sql
-- =============================================================================

ALTER TABLE public.tournaments
    ADD COLUMN IF NOT EXISTS accommodation_lat     numeric(9, 6),
    ADD COLUMN IF NOT EXISTS accommodation_lng     numeric(9, 6),
    ADD COLUMN IF NOT EXISTS accommodation_address text,
    ADD COLUMN IF NOT EXISTS accommodation_kind    text
        CHECK (accommodation_kind IN ('home', 'hotel') OR accommodation_kind IS NULL);

-- Coord-pair constraint: both null (no accommodation) or both set.
-- Mirrors tournaments_coords_pair from migration 0012.
ALTER TABLE public.tournaments
    ADD CONSTRAINT tournaments_accommodation_coords_pair CHECK (
        (accommodation_lat IS NULL AND accommodation_lng IS NULL)
        OR (accommodation_lat IS NOT NULL AND accommodation_lng IS NOT NULL)
    );

COMMENT ON COLUMN public.tournaments.accommodation_lat IS
    'Latitude of parent accommodation (hotel or home). '
    'Null = no accommodation set; plan behaves as venue-local. '
    'Pair constraint: accommodation_lat and accommodation_lng must both be set or both null.';

COMMENT ON COLUMN public.tournaments.accommodation_lng IS
    'Longitude of parent accommodation. Pair-constrained with accommodation_lat.';

COMMENT ON COLUMN public.tournaments.accommodation_address IS
    'Human-readable address of accommodation (from MapKit MKPlacemark). '
    'Nullable independently of coords — stored for display only, not for routing.';

COMMENT ON COLUMN public.tournaments.accommodation_kind IS
    'Accommodation type for copy-variation: ''home'' or ''hotel''. '
    'Null treated as ''home'' in display layer. '
    'Plan math is identical for both kinds — only coordinates matter.';
