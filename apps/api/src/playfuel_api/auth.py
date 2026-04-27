"""Auth dependency — verify Supabase JWT (HS256) and extract user_id.

Design:
  bearer_scheme is a module-level singleton so FastAPI can cache the
  HTTPBearer call once per request even when both verify_supabase_jwt
  and authed_client (db.py) appear in the same dependency graph.

Token contract (Supabase JWTs):
  alg:  HS256
  aud:  "authenticated"
  sub:  Supabase user UUID (string)
  The sub claim is extracted and returned as a UUID.

Raises:
  HTTP 401 — no Authorization header (auto_error=False, raised by guard)
  HTTP 401 — expired or otherwise invalid token
"""
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from playfuel_api.settings import Settings, get_settings

# Module-level singleton — shared with db.py so FastAPI caches it once per request.
# auto_error=False so we can return 401 (not FastAPI's default 403) when the header is missing.
bearer_scheme = HTTPBearer(auto_error=False)


def verify_supabase_jwt(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> UUID:
    """Verify the Supabase JWT and return the caller's user_id (sub claim).

    Args:
        creds:    Injected by FastAPI from the Authorization header.
        settings: App settings (provides supabase_jwt_secret).

    Returns:
        UUID — the Supabase user id extracted from the 'sub' claim.

    Raises:
        HTTPException(401) if the token is expired or otherwise invalid.
        HTTPException(401) if no Bearer token is present (raised by guard at top of function).
    """
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = creds.credentials
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sub is not a valid UUID",
            headers={"WWW-Authenticate": "Bearer"},
        )
