-- =============================================================================
-- PlayFuel Migration 0004: Auth Trigger (Sign in with Apple)
-- =============================================================================
-- Prerequisites: 0001 + 0002 + 0003 must be applied first.
--
-- This migration wires Supabase Auth to the public schema:
--   1. handle_new_user() — SECURITY DEFINER function that inserts a shadow row
--      into public.users when auth.users gets a new record.
--   2. on_auth_user_created — trigger on auth.users that calls handle_new_user().
--
-- SECURITY DEFINER + set search_path note:
--   The trigger fires in the auth schema context. Without SECURITY DEFINER,
--   the auth role cannot insert into public.users. This is the most common
--   Supabase footgun. The explicit set search_path prevents search_path
--   injection attacks on the function body.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- handle_new_user()
-- ---------------------------------------------------------------------------
-- Called automatically when a new row is inserted into auth.users.
-- Triggered by all Supabase Auth providers, including Sign in with Apple.
-- Uses ON CONFLICT DO NOTHING as a safety net against duplicate-trigger edge
-- cases (e.g. local dev seed re-runs).
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  insert into public.users (id, created_at, updated_at)
  values (new.id, now(), now())
  on conflict (id) do nothing;

  return new;
end;
$$;


-- ---------------------------------------------------------------------------
-- on_auth_user_created
-- Fires AFTER INSERT on auth.users so that the auth row is committed and
-- auth.uid() resolves correctly during the function body.
-- ---------------------------------------------------------------------------
-- Drop existing trigger first (idempotent re-run safety)
drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();


-- =============================================================================
-- Sign in with Apple — environment variable reference
-- =============================================================================
-- The following env vars must be set in Supabase Auth provider config.
-- Placeholder names only — real values live in .env (never committed).
-- See auth/sign-in-with-apple.md for full setup steps.
--
--   APPLE_SERVICE_ID       — e.g. com.playfuel.app.auth
--   APPLE_TEAM_ID          — 10-character Apple Developer Team ID
--   APPLE_KEY_ID           — Key ID from the .p8 private key
--   APPLE_PRIVATE_KEY_PATH — Path to the .p8 file (local only; use env in prod)
--   APPLE_REDIRECT_URL     — https://<project-ref>.supabase.co/auth/v1/callback
--
-- These are configured in the Supabase Dashboard under:
--   Authentication → Providers → Apple
-- NOT via SQL — this comment block is for documentation only.
-- =============================================================================
