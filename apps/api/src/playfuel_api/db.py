"""Per-request Supabase client wired with the caller's JWT for RLS enforcement.

Design:
  authed_client() is a FastAPI dependency that creates a fresh supabase-py
  SyncClient on every request and immediately overrides the PostgREST
  Authorization header with the caller's JWT (not the anon key).

  This means Postgres RLS policies that rely on (select auth.uid()) will see
  the correct user_id for every query, enforcing row ownership automatically
  without any manual WHERE user_id = ... clauses in route handlers.

  The anon key is still used to initialise the client (it sets the apikey
  header required by Supabase's PostgREST gateway) — the JWT is then layered
  on top via client.postgrest.auth().

  bearer_scheme is imported from auth.py so FastAPI uses the same singleton
  and caches the HTTPBearer call once per request.

  The service role key is intentionally NOT used here — bypassing RLS is
  prohibited for all MVP protected routes (see README.md Key Design Decisions).
"""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from supabase import Client, create_client

from playfuel_api.auth import bearer_scheme
from playfuel_api.settings import Settings, get_settings


def authed_client(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Client:
    """Return a per-request Supabase SyncClient authenticated with the caller's JWT.

    The client is initialised with the anon key (required by Supabase gateway)
    and then has its PostgREST Authorization header overridden to use the user's
    JWT so Postgres RLS policies can enforce row ownership.

    Args:
        creds:    Injected by FastAPI; the raw Bearer token from the request.
        settings: App settings providing supabase_url and supabase_anon_key.

    Returns:
        supabase.Client — ready for table() / from_() PostgREST queries.
    """
    client: Client = create_client(settings.supabase_url, settings.supabase_anon_key)
    # Override the PostgREST Authorization header with the user's JWT.
    # postgrest-py BaseClient.auth() sets: Authorization: Bearer <token>
    # Postgres RLS then uses auth.uid() from the validated JWT sub claim.
    client.postgrest.auth(creds.credentials)
    return client
