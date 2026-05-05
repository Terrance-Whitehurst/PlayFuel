-- Phase B international rollout: add canonical metric weather columns.
-- Open-Meteo now called with celsius/kmh. Both metric (canonical) and
-- computed imperial (legacy backward-compat) are stored. Old iOS clients
-- reading tempF/windMph keep working; new iOS reads tempC/windKph.
--
-- temp_f / wind_mph are NOT renamed — the column names are now cosmetically
-- wrong (they store computed values, not raw sensor reads), but renaming
-- would require a data migration. A future cleanup migration will rename
-- or drop them once all iOS clients have migrated past Phase B.

ALTER TABLE public.weather_snapshots
  ADD COLUMN IF NOT EXISTS temp_c   numeric(5, 1),
  ADD COLUMN IF NOT EXISTS wind_kmh numeric(5, 1);

COMMENT ON COLUMN public.weather_snapshots.temp_f   IS
  'Legacy imperial — computed from temp_c via (temp_c * 9/5) + 32. Retained for backward compat. Will be dropped in a future cleanup migration.';
COMMENT ON COLUMN public.weather_snapshots.wind_mph IS
  'Legacy imperial — computed from wind_kmh via wind_kmh / 1.609. Retained for backward compat. Will be dropped in a future cleanup migration.';
COMMENT ON COLUMN public.weather_snapshots.temp_c   IS
  'Temperature in °C — canonical metric value from Open-Meteo (Phase B+). NULL on pre-Phase-B rows; compute as (temp_f - 32) * 5/9 for those.';
COMMENT ON COLUMN public.weather_snapshots.wind_kmh IS
  'Wind speed in km/h — canonical metric value from Open-Meteo (Phase B+). NULL on pre-Phase-B rows; compute as wind_mph * 1.609 for those.';
