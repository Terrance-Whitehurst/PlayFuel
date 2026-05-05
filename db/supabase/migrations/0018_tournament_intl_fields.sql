-- 0018_tournament_intl_fields.sql
-- Phase A international rollout: persist user-selected time_zone end-to-end
-- and capture ISO 3166-1 alpha-2 country code for the venue.

ALTER TABLE public.tournaments
  ADD COLUMN IF NOT EXISTS time_zone     text,
  ADD COLUMN IF NOT EXISTS venue_country text;

COMMENT ON COLUMN public.tournaments.time_zone     IS 'IANA tz identifier (e.g. America/Mexico_City). Optional; client-supplied.';
COMMENT ON COLUMN public.tournaments.venue_country IS 'ISO 3166-1 alpha-2 country code (e.g. US, MX, CA). Optional; auto-populated from MKPlacemark on iOS when available.';
